from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent.runtime import AgentRuntime
from app.agent.tools import execute_tool
from app.api.chat_routes import router as chat_router
from app.api.deps import get_agent_runtime, get_repository
from app.core.config import Settings
from app.models.domain import ChatMessage, CreateGraphRequest, GraphChatRequest
from app.services.repository import GraphRepository


class FakeAuth:
    def status(self, locale: str = "en") -> dict:
        return {"authenticated": True, "sharing": True, "account": "test@example.com"}

    async def close(self) -> None:
        return None


class FakeClient:
    def __init__(self, responses: list[dict] | None = None):
        self.responses = list(responses or [])
        self.requests: list[dict] = []

    async def list_models(self) -> list[dict]:
        return [{"slug": "gpt-test", "display_name": "GPT Test", "description": ""}]

    async def stream(self, payload: dict, on_event) -> dict:
        self.requests.append(payload)
        if not self.responses:
            return {"output": [{"type": "message", "id": "m-default", "content": [{"type": "output_text", "text": "ok"}]}]}
        return self.responses.pop(0)


def _make_env():
    tmpdir = tempfile.TemporaryDirectory()
    db_path = Path(tmpdir.name) / "test.sqlite3"
    settings = Settings(db_path=db_path)
    repo = GraphRepository(db_path)
    env = repo.create_graph(CreateGraphRequest(title="MySQL", subject="Databases", language="zh-CN"))
    graph_id = env.workspace.graphs[-1].graph_id
    # Seed one topic via proposal so we have a real topic to distill against.
    from app.agent.contracts import GraphOperationDraft, ProposalDraft, ProposalTopicDraft
    from app.services.proposal_service import ProposalService

    graph = repo.graph(graph_id)
    seed_draft = ProposalDraft(
        base_graph_version=graph.version,
        summary="Add MVCC",
        operations=[
            GraphOperationDraft(
                op_id="op-mvcc",
                op="upsert_topic",
                entity_kind="topic",
                topic=ProposalTopicDraft(id="mvcc", title="MVCC", slug="mvcc", description="Multiversion concurrency control"),
            )
        ],
    )
    prepared = ProposalService().prepare(graph, seed_draft, tool="propose_ingest", proposal_id="prop-seed", prompt="seed", model="gpt-test", use_grounding=False)
    repo.apply_proposal(prepared.proposal_envelope)
    return tmpdir, settings, repo, graph_id


class DistillationAndRevertTests(unittest.TestCase):
    def test_propose_distillation_summary_and_proposal_apply_independently(self) -> None:
        tmpdir, settings, repo, graph_id = _make_env()
        self.addCleanup(tmpdir.cleanup)

        graph = repo.graph(graph_id)
        distill_args = json.dumps({
            "summary": {
                "topic_id": "mvcc",
                "title": "MVCC 学习总结",
                "body": "## 核心理解\nReadView + Undo Log 版本链。\n\n## 延伸线索\n- Purge 线程",
            },
            "proposal": {
                "base_graph_version": graph.version,
                "summary": "补充 Undo Log 前置节点",
                "operations": [
                    {
                        "op_id": "add-undo",
                        "op": "upsert_topic",
                        "entity_kind": "topic",
                        "topic": {"id": "undo-log", "title": "Undo Log", "slug": "undo-log", "description": "回滚日志与版本链"},
                    },
                    {
                        "op_id": "link-undo",
                        "op": "upsert_edge",
                        "entity_kind": "edge",
                        "edge": {"id": "undo-req-mvcc", "source_topic_id": "undo-log", "target_topic_id": "mvcc", "relation": "requires"},
                    },
                ],
            },
        }, ensure_ascii=False)

        client = FakeClient(responses=[
            {"output": [{"type": "function_call", "call_id": "call-distill-1", "name": "propose_distillation", "arguments": distill_args}]},
            {"output": [{"type": "message", "id": "msg-done", "content": [{"type": "output_text", "text": "提炼完成，请审阅。"}]}]},
        ])
        runtime = AgentRuntime(settings, repo, auth=FakeAuth(), client=client)

        async def run_turn():
            session = repo.create_chat_session(graph_id, topic_id="mvcc", title="MVCC")
            sid, run_id = await runtime.start_chat(graph_id, GraphChatRequest(prompt="提炼本轮对话", session_id=session.session_id, selected_topic_id="mvcc"))
            run = runtime.runs.get(run_id)
            if run is not None:
                await run.done
            return sid

        sid = asyncio.run(run_turn())
        thread = repo.chat_thread(graph_id, sid)
        distill_msg = next((m for m in thread.messages if m.distillation is not None), None)
        self.assertIsNotNone(distill_msg)
        assert distill_msg is not None and distill_msg.distillation is not None
        self.assertIsNotNone(distill_msg.distillation.summary)
        self.assertIsNotNone(distill_msg.distillation.proposal)
        self.assertFalse(distill_msg.distillation.summary.applied)
        self.assertFalse(distill_msg.distillation.proposal_applied)

        # Apply summary via repository (and verify idempotency)
        ws1, updated_msg = repo.apply_distillation_summary(graph_id, sid, distill_msg.id)
        self.assertTrue(updated_msg.distillation.summary.applied)
        self.assertIsNotNone(updated_msg.distillation.summary.artifact_id)
        mvcc_topic = next(t for t in repo.graph(graph_id).topics if t.id == "mvcc")
        self.assertEqual(len(mvcc_topic.artifacts), 1)
        self.assertEqual(mvcc_topic.artifacts[0].title, "MVCC 学习总结")

        # Retrying apply_distillation_summary is idempotent
        ws2, _ = repo.apply_distillation_summary(graph_id, sid, distill_msg.id)
        self.assertEqual(ws1.snapshot.id, ws2.snapshot.id)
        self.assertEqual(len(next(t for t in repo.graph(graph_id).topics if t.id == "mvcc").artifacts), 1)

        # Applying the embedded proposal after summary save succeeds and marks distillation.proposal_applied = True
        repo.apply_proposal(updated_msg.distillation.proposal.proposal_envelope)
        reloaded = repo.chat_thread(graph_id, sid)
        reloaded_distill = next(m for m in reloaded.messages if m.id == distill_msg.id)
        self.assertTrue(reloaded_distill.distillation.proposal_applied)
        self.assertTrue(any(t.id == "undo-log" for t in repo.graph(graph_id).topics))

    def test_propose_distillation_rejects_empty_and_invalid_topic(self) -> None:
        tmpdir, settings, repo, graph_id = _make_env()
        self.addCleanup(tmpdir.cleanup)

        client = FakeClient(responses=[
            {"output": [{"type": "function_call", "call_id": "call-empty", "name": "propose_distillation", "arguments": "{}"}]},
            {"output": [{"type": "function_call", "call_id": "call-bad-topic", "name": "propose_distillation", "arguments": json.dumps({"summary": {"topic_id": "missing", "title": "T", "body": "B"}})}]},
            {"output": [{"type": "message", "id": "msg-ok", "content": [{"type": "output_text", "text": "handled"}]}]},
        ])
        runtime = AgentRuntime(settings, repo, auth=FakeAuth(), client=client)

        async def run_turn():
            sid, run_id = await runtime.start_chat(graph_id, GraphChatRequest(prompt="distill"))
            run = runtime.runs.get(run_id)
            if run is not None:
                await run.done
            return sid

        sid = asyncio.run(run_turn())
        thread = repo.chat_thread(graph_id, sid)
        failed = [m for m in thread.messages if m.activity and m.activity.tool == "propose_distillation" and m.activity.status == "failed"]
        self.assertEqual(len(failed), 2)

    def test_chat_revert_truncates_messages_resets_transcript_and_keeps_snapshots(self) -> None:
        tmpdir, settings, repo, graph_id = _make_env()
        self.addCleanup(tmpdir.cleanup)

        client = FakeClient(responses=[
            {"output": [{"type": "message", "id": "a1", "content": [{"type": "output_text", "text": "Reply 1"}]}]},
            {"output": [{"type": "message", "id": "a2", "content": [{"type": "output_text", "text": "Reply 2 (wrong turn)"}]}]},
            {"output": [{"type": "message", "id": "a3", "content": [{"type": "output_text", "text": "Reply 2 (fixed)"}]}]},
        ])
        runtime = AgentRuntime(settings, repo, auth=FakeAuth(), client=client)

        app = FastAPI()
        app.include_router(chat_router)
        app.dependency_overrides[get_agent_runtime] = lambda: runtime
        app.dependency_overrides[get_repository] = lambda: repo
        http = TestClient(app)

        async def send(prompt: str, cid: str, sid: str | None = None):
            session_id, run_id = await runtime.start_chat(graph_id, GraphChatRequest(prompt=prompt, client_message_id=cid, session_id=sid))
            run = runtime.runs.get(run_id)
            if run is not None:
                await run.done
            return session_id

        sid = asyncio.run(send("First question", "u-1"))
        asyncio.run(send("Mistyped second question", "u-2", sid))

        before_snapshot_id = repo.current().snapshot.id
        before_last_event_id = runtime.store.last_event_id(sid)
        self.assertIsNotNone(runtime.store.transcript(sid))

        # Reject reverting an assistant message
        thread_before = repo.chat_thread(graph_id, sid)
        assistant_msg = next(m for m in thread_before.messages if m.role == "assistant")
        bad_resp = http.post(f"/api/v1/graphs/{graph_id}/chat/revert", json={"session_id": sid, "message_id": assistant_msg.id})
        self.assertEqual(bad_resp.status_code, 400)

        # Revert from u-2
        resp = http.post(f"/api/v1/graphs/{graph_id}/chat/revert", json={"session_id": sid, "message_id": "u-2"})
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["reverted_message_id"], "u-2")
        self.assertEqual(payload["reverted_prompt"], "Mistyped second question")
        self.assertEqual([m["id"] for m in payload["thread"]["messages"] if m["role"] == "user"], ["u-1"])
        self.assertGreaterEqual(payload["thread"]["last_event_id"], before_last_event_id)
        self.assertIsNone(runtime.store.transcript(sid))
        # Graph snapshot untouched
        self.assertEqual(repo.current().snapshot.id, before_snapshot_id)

        # Next turn succeeds cleanly and imports only u-1 + Reply 1
        asyncio.run(send("Corrected second question", "u-3", sid))
        last_request = client.requests[-1]
        imported = json.dumps(last_request["input"], ensure_ascii=False)
        self.assertIn("First question", imported)
        self.assertNotIn("Mistyped second question", imported)


if __name__ == "__main__":
    unittest.main()
