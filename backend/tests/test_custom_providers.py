from __future__ import annotations

import json
import unittest

import httpx

from agent_test_support import install_client


def _anthropic_sse(*events: dict) -> bytes:
    chunks = [f"data: {json.dumps(event)}\n\n" for event in events]
    return "".join(chunks).encode("utf-8")


def _openai_sse(*chunks: dict) -> bytes:
    lines = [f"data: {json.dumps(c)}\n\n" for c in chunks] + ["data: [DONE]\n\n"]
    return "".join(lines).encode("utf-8")


class CustomProvidersTests(unittest.TestCase):
    def test_custom_key_unlocks_workspace_without_chatgpt_and_never_leaks_plaintext(self):
        client, repo, runtime = install_client(self, signed=False)
        # Signed out with no custom provider -> workspace locked
        self.assertEqual(client.get("/api/v1/workspace/current").status_code, 401)
        account = client.get("/api/v1/chatgpt/account").json()
        self.assertFalse(account["ready"])

        # Add an Anthropic provider profile via /api/v1/providers (accessible while signed out)
        secret_key = "sk-ant-api03-super-secret-value-9988"
        save = client.post(
            "/api/v1/providers",
            json={
                "name": "Anthropic Official",
                "kind": "anthropic",
                "base_url": "https://api.anthropic.com/v1",
                "api_key": secret_key,
                "models": ["claude-sonnet-4-5"],
            },
        )
        self.assertEqual(save.status_code, 200, save.text)
        body = save.json()
        self.assertNotIn(secret_key, json.dumps(body))
        self.assertTrue(body["profile"]["has_key"])
        self.assertIn("•••", body["profile"]["key_hint"])

        # Workspace is now unlocked even without ChatGPT OAuth!
        self.assertEqual(client.get("/api/v1/workspace/current").status_code, 200)
        account = client.get("/api/v1/chatgpt/account").json()
        self.assertTrue(account["ready"])
        self.assertTrue(account["has_custom_providers"])
        self.assertEqual(len(account["models"]), 1)
        self.assertEqual(account["models"][0]["providerKind"], "anthropic")
        self.assertTrue(account["models"][0]["supportsWebSearch"])
        self.assertFalse(account["models"][0]["supportsReasoningEffort"])

        # Verify SQLite does NOT contain raw API key anywhere
        with repo._connect() as conn:
            rows = conn.execute("SELECT * FROM custom_providers").fetchall()
            self.assertNotIn(secret_key, json.dumps([dict(r) for r in rows]))

        # Deleting the only provider relocks the workspace
        pid = body["profile"]["id"]
        self.assertEqual(client.delete(f"/api/v1/providers/{pid}").status_code, 200)
        self.assertEqual(client.get("/api/v1/workspace/current").status_code, 401)

    def test_anthropic_streaming_prompt_caching_native_web_search_and_tool_calling(self):
        client, repo, runtime = install_client(self, signed=False)
        captured_requests: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "claude-sonnet-4-5"}, {"id": "claude-haiku-4-5"}]})
            payload = json.loads(request.content.decode("utf-8"))
            captured_requests.append(payload)
            if len(captured_requests) == 1:
                # First step: invoke read_graph tool
                return httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=_anthropic_sse(
                        {"type": "content_block_start", "index": 0, "content_block": {"type": "server_tool_use", "id": "srv_1", "name": "web_search"}},
                        {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "toolu_1", "name": "read_graph"}},
                        {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "{}"}},
                        {"type": "content_block_stop", "index": 1},
                        {"type": "message_stop"},
                    ),
                )
            # Second step: final text answer
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=_anthropic_sse(
                    {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello from Claude!"}},
                    {"type": "content_block_stop", "index": 0},
                    {"type": "message_stop"},
                ),
            )

        runtime.provider_http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            test_res = client.post(
                "/api/v1/providers/test",
                json={"kind": "anthropic", "api_key": "sk-ant-test-123456"},
            )
            self.assertEqual(test_res.status_code, 200, test_res.text)
            self.assertIn("claude-sonnet-4-5", test_res.json()["models"])

            saved = client.post(
                "/api/v1/providers",
                json={"name": "Claude", "kind": "anthropic", "api_key": "sk-ant-test-123456", "models": ["claude-sonnet-4-5"]},
            ).json()
            model_id = f"custom:{saved['profile']['id']}:claude-sonnet-4-5"
            graph_id = repo.current().workspace.active_graph_id

            with client.stream(
                "POST",
                f"/api/v1/graphs/{graph_id}/chat/stream",
                json={"prompt": "Inspect my graph", "model": model_id},
            ) as stream:
                self.assertEqual(stream.status_code, 200)
                raw = stream.read().decode("utf-8")
            events = [json.loads(line) for line in raw.splitlines() if line.strip()]
            session_id = next(e["thread"]["session_id"] for e in events if e.get("type") == "thread_state")

            self.assertEqual(len(captured_requests), 2)
            # Prompt caching enabled on system block
            self.assertEqual(captured_requests[0]["system"][0]["cache_control"], {"type": "ephemeral"})
            # Native Anthropic web search tool attached
            self.assertTrue(any(t.get("type") == "web_search_20250305" for t in captured_requests[0]["tools"]))
            # Final assistant message persisted
            thread = repo.chat_thread(graph_id, session_id)
            self.assertTrue(any(m.role == "assistant" and "Hello from Claude!" in m.content for m in thread.messages))
        finally:
            import asyncio
            asyncio.run(runtime.provider_http.aclose())

    def test_openai_compatible_mid_thread_switch_and_optional_web_search(self):
        client, repo, runtime = install_client(self, signed=True)
        openai_requests: list[dict] = []
        tavily_queries: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if "tavily.com" in str(request.url):
                payload = json.loads(request.content.decode("utf-8"))
                tavily_queries.append(payload["query"])
                return httpx.Response(200, json={"results": [{"title": "Doc", "url": "https://example.com", "content": "Fresh info"}]})
            payload = json.loads(request.content.decode("utf-8"))
            openai_requests.append(payload)
            if len(openai_requests) == 1:
                return httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=_openai_sse(
                        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_ws_1", "function": {"name": "web_search", "arguments": "{\"query\":\"clew "}}]}}]},
                        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "test\"}"}}]}}]},
                    ),
                )
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=_openai_sse(
                    {"choices": [{"delta": {"content": "Answered via OpenAI-compatible + Tavily!"}}]},
                ),
            )

        runtime.provider_http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            # Configure OpenAI-compatible provider + optional Tavily search key
            saved = client.post(
                "/api/v1/providers",
                json={
                    "name": "DeepSeek",
                    "kind": "openai_compatible",
                    "base_url": "https://api.deepseek.com/v1",
                    "api_key": "sk-ds-secret-123456",
                    "models": ["deepseek-chat"],
                },
            ).json()
            ws = client.put("/api/v1/providers/web-search", json={"provider": "tavily", "api_key": "tvly-secret-999999"})
            self.assertEqual(ws.status_code, 200, ws.text)
            self.assertNotIn("tvly-secret-999999", ws.text)

            graph_id = repo.current().workspace.active_graph_id
            # Simulate an existing ChatGPT Responses-API transcript in this session
            thread = repo.chat_thread(graph_id, None)
            runtime.store.save_transcript(
                thread.session_id,
                [{"type": "reasoning", "encrypted_content": "opaque-openai-only-blob"}],
                protocol="openai_responses",
            )

            # Switch mid-thread to DeepSeek
            model_id = f"custom:{saved['profile']['id']}:deepseek-chat"
            with client.stream(
                "POST",
                f"/api/v1/graphs/{graph_id}/chat/stream",
                json={"prompt": "Search the web for clew", "session_id": thread.session_id, "model": model_id},
            ) as stream:
                self.assertEqual(stream.status_code, 200)
                _ = stream.read()

            # Verify opaque OpenAI reasoning item was NOT replayed, Tavily ran, and reply completed
            self.assertEqual(tavily_queries, ["clew test"])
            self.assertNotIn("opaque-openai-only-blob", json.dumps(openai_requests[0]))
            self.assertTrue(any(t["function"]["name"] == "web_search" for t in openai_requests[0]["tools"]))
            updated = repo.chat_thread(graph_id, thread.session_id)
            self.assertTrue(any(m.role == "assistant" and "Tavily" in m.content for m in updated.messages))
        finally:
            import asyncio
            asyncio.run(runtime.provider_http.aclose())
