from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal
from uuid import uuid4

import httpx

from app.agent.chatgpt_auth import ChatGPTError, CredentialStore, KeyringCredentialStore
from app.services.repository import GraphRepository

ProviderKind = Literal["anthropic", "openai_compatible"]
WebSearchKind = Literal["tavily", "brave"]

ANTHROPIC_DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
ANTHROPIC_API_VERSION = "2023-06-01"
OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"
CUSTOM_MODEL_PREFIX = "custom:"

ANTHROPIC_FALLBACK_MODELS = [
    "claude-sonnet-4-5",
    "claude-opus-4-1",
    "claude-haiku-4-5",
]

PROVIDER_PRESETS: list[dict[str, Any]] = [
    {
        "id": "anthropic",
        "label": "Anthropic (Claude)",
        "kind": "anthropic",
        "base_url": ANTHROPIC_DEFAULT_BASE_URL,
        "default_models": ANTHROPIC_FALLBACK_MODELS,
        "supports_native_web_search": True,
    },
    {
        "id": "openai",
        "label": "OpenAI API",
        "kind": "openai_compatible",
        "base_url": OPENAI_DEFAULT_BASE_URL,
        "default_models": ["gpt-4.1", "gpt-4.1-mini", "o4-mini"],
        "supports_native_web_search": False,
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "kind": "openai_compatible",
        "base_url": "https://openrouter.ai/api/v1",
        "default_models": ["anthropic/claude-sonnet-4.5", "openai/gpt-4.1", "google/gemini-2.5-pro"],
        "supports_native_web_search": False,
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "kind": "openai_compatible",
        "base_url": "https://api.deepseek.com/v1",
        "default_models": ["deepseek-chat", "deepseek-reasoner"],
        "supports_native_web_search": False,
    },
    {
        "id": "gemini",
        "label": "Google Gemini (OpenAI-Compatible)",
        "kind": "openai_compatible",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "default_models": ["gemini-2.5-pro", "gemini-2.5-flash"],
        "supports_native_web_search": False,
    },
    {
        "id": "ollama",
        "label": "Ollama (Local)",
        "kind": "openai_compatible",
        "base_url": "http://127.0.0.1:11434/v1",
        "default_models": ["qwen2.5:14b", "llama3.1:8b"],
        "supports_native_web_search": False,
    },
    {
        "id": "custom",
        "label": "Custom OpenAI-Compatible",
        "kind": "openai_compatible",
        "base_url": "",
        "default_models": [],
        "supports_native_web_search": False,
    },
]


class ProviderKeyringStore(KeyringCredentialStore):
    """OS keychain storage for custom provider and search API keys (no plaintext fallback)."""

    service = "Clew · Custom Providers"

    def __init__(self, account: str = "custom-providers"):
        super().__init__(account=account)


def mask_api_key(api_key: str) -> str:
    cleaned = api_key.strip()
    if not cleaned:
        return ""
    if len(cleaned) <= 8:
        return "•" * len(cleaned)
    return f"{cleaned[:6]}•••{cleaned[-4:]}"


def normalize_base_url(kind: ProviderKind, base_url: str | None) -> str:
    raw = (base_url or "").strip().rstrip("/")
    if not raw:
        return ANTHROPIC_DEFAULT_BASE_URL if kind == "anthropic" else OPENAI_DEFAULT_BASE_URL
    if not (raw.startswith("http://") or raw.startswith("https://")):
        raise ValueError("Base URL must start with http:// or https://")
    return raw


def is_local_base_url(base_url: str) -> bool:
    lower = base_url.lower()
    return (
        lower.startswith("http://127.0.0.1")
        or lower.startswith("http://localhost")
        or lower.startswith("http://[::1]")
    )


def qualify_custom_model(profile_id: str, model_id: str) -> str:
    return f"{CUSTOM_MODEL_PREFIX}{profile_id}:{model_id}"


def parse_custom_model(qualified: str | None) -> tuple[str, str] | None:
    if not qualified or not qualified.startswith(CUSTOM_MODEL_PREFIX):
        return None
    rest = qualified[len(CUSTOM_MODEL_PREFIX):]
    if ":" not in rest:
        return None
    profile_id, model_id = rest.split(":", 1)
    if not profile_id or not model_id:
        return None
    return profile_id, model_id


def slugify_profile_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")[:24]
    return f"{slug or 'provider'}-{uuid4().hex[:6]}"


@dataclass
class ProviderProfile:
    id: str
    name: str
    kind: ProviderKind
    base_url: str
    models: list[str] = field(default_factory=list)
    key_hint: str = ""
    enabled: bool = True

    def to_public_dict(self, has_key: bool) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "base_url": self.base_url,
            "models": list(self.models),
            "key_hint": self.key_hint,
            "has_key": has_key,
            "enabled": self.enabled,
            "supports_native_web_search": self.kind == "anthropic",
        }


@dataclass
class WebSearchProfile:
    provider: WebSearchKind
    key_hint: str = ""
    enabled: bool = True

    def to_public_dict(self, has_key: bool) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "key_hint": self.key_hint,
            "has_key": has_key,
            "enabled": self.enabled and has_key,
        }


class ProviderRegistry:
    """Persists non-secret provider metadata in SQLite and API keys in OS keychain."""

    def __init__(self, repository: GraphRepository, store: CredentialStore):
        self.repository = repository
        self.store = store
        with repository._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS custom_providers (
                    profile_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    models_json TEXT NOT NULL,
                    key_hint TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    sort_order INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS custom_web_search (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    provider TEXT NOT NULL,
                    key_hint TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1
                );
                """
            )

    def _read_secrets(self) -> dict[str, Any]:
        try:
            raw = self.store.read()
        except ChatGPTError:
            return {"providers": {}, "web_search": None}
        if not isinstance(raw, dict):
            return {"providers": {}, "web_search": None}
        providers = raw.get("providers") if isinstance(raw.get("providers"), dict) else {}
        web_search = raw.get("web_search") if isinstance(raw.get("web_search"), str) else None
        return {"providers": dict(providers), "web_search": web_search}

    def _write_secrets(self, secrets_data: dict[str, Any]) -> None:
        providers = secrets_data.get("providers") or {}
        web_search = secrets_data.get("web_search")
        if not providers and not web_search:
            self.store.delete()
        else:
            self.store.write({"providers": providers, "web_search": web_search})

    def list_profiles(self) -> list[ProviderProfile]:
        with self.repository._connect() as conn:
            rows = conn.execute(
                "SELECT profile_id, name, kind, base_url, models_json, key_hint, enabled FROM custom_providers ORDER BY sort_order ASC, rowid ASC"
            ).fetchall()
        profiles: list[ProviderProfile] = []
        for row in rows:
            try:
                models = json.loads(row["models_json"])
                if not isinstance(models, list):
                    models = []
            except json.JSONDecodeError:
                models = []
            profiles.append(
                ProviderProfile(
                    id=row["profile_id"],
                    name=row["name"],
                    kind=row["kind"],
                    base_url=row["base_url"],
                    models=[str(m).strip() for m in models if str(m).strip()],
                    key_hint=row["key_hint"] or "",
                    enabled=bool(row["enabled"]),
                )
            )
        return profiles

    def get_profile(self, profile_id: str) -> ProviderProfile | None:
        return next((p for p in self.list_profiles() if p.id == profile_id), None)

    def get_api_key(self, profile_id: str) -> str | None:
        secrets_data = self._read_secrets()
        key = secrets_data["providers"].get(profile_id)
        return key if isinstance(key, str) and key.strip() else None

    def upsert_profile(
        self,
        *,
        profile_id: str | None,
        name: str,
        kind: ProviderKind,
        base_url: str | None,
        models: list[str],
        api_key: str | None = None,
        enabled: bool = True,
    ) -> ProviderProfile:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("Provider name is required.")
        if kind not in {"anthropic", "openai_compatible"}:
            raise ValueError("Unsupported provider kind.")
        normalized_url = normalize_base_url(kind, base_url)
        cleaned_models = list(dict.fromkeys(m.strip() for m in models if m and m.strip()))
        if not cleaned_models:
            raise ValueError("At least one model ID is required.")

        existing = self.get_profile(profile_id) if profile_id else None
        pid = existing.id if existing else (profile_id.strip() if profile_id and profile_id.strip() else slugify_profile_id(cleaned_name))
        cleaned_key = api_key.strip() if isinstance(api_key, str) else ""

        secrets_data = self._read_secrets()
        existing_key = secrets_data["providers"].get(pid)
        if not cleaned_key and not existing_key and not (kind == "openai_compatible" and is_local_base_url(normalized_url)):
            raise ValueError("API key is required for this provider.")

        if cleaned_key:
            secrets_data["providers"][pid] = cleaned_key
            self._write_secrets(secrets_data)
            key_hint = mask_api_key(cleaned_key)
        else:
            key_hint = existing.key_hint if existing else ("local" if is_local_base_url(normalized_url) else "")

        with self.repository._connect() as conn:
            conn.execute(
                """
                INSERT INTO custom_providers (profile_id, name, kind, base_url, models_json, key_hint, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET
                    name=excluded.name,
                    kind=excluded.kind,
                    base_url=excluded.base_url,
                    models_json=excluded.models_json,
                    key_hint=excluded.key_hint,
                    enabled=excluded.enabled
                """,
                (pid, cleaned_name, kind, normalized_url, json.dumps(cleaned_models, ensure_ascii=False), key_hint, 1 if enabled else 0),
            )
        return ProviderProfile(
            id=pid,
            name=cleaned_name,
            kind=kind,
            base_url=normalized_url,
            models=cleaned_models,
            key_hint=key_hint,
            enabled=enabled,
        )

    def delete_profile(self, profile_id: str) -> bool:
        with self.repository._connect() as conn:
            cursor = conn.execute("DELETE FROM custom_providers WHERE profile_id = ?", (profile_id,))
            deleted = cursor.rowcount > 0
        secrets_data = self._read_secrets()
        if profile_id in secrets_data["providers"]:
            secrets_data["providers"].pop(profile_id, None)
            self._write_secrets(secrets_data)
        return deleted

    def get_web_search(self) -> WebSearchProfile | None:
        with self.repository._connect() as conn:
            row = conn.execute("SELECT provider, key_hint, enabled FROM custom_web_search WHERE id = 1").fetchone()
        if row is None:
            return None
        return WebSearchProfile(provider=row["provider"], key_hint=row["key_hint"] or "", enabled=bool(row["enabled"]))

    def get_web_search_api_key(self) -> str | None:
        secrets_data = self._read_secrets()
        key = secrets_data.get("web_search")
        return key if isinstance(key, str) and key.strip() else None

    def set_web_search(self, *, provider: WebSearchKind, api_key: str | None, enabled: bool = True) -> WebSearchProfile:
        if provider not in {"tavily", "brave"}:
            raise ValueError("Unsupported web search provider.")
        existing = self.get_web_search()
        cleaned_key = api_key.strip() if isinstance(api_key, str) else ""
        secrets_data = self._read_secrets()
        if not cleaned_key and not secrets_data.get("web_search"):
            raise ValueError("Search API key is required.")
        if cleaned_key:
            secrets_data["web_search"] = cleaned_key
            self._write_secrets(secrets_data)
            key_hint = mask_api_key(cleaned_key)
        else:
            key_hint = existing.key_hint if existing else ""
        with self.repository._connect() as conn:
            conn.execute(
                """
                INSERT INTO custom_web_search (id, provider, key_hint, enabled)
                VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    provider=excluded.provider,
                    key_hint=excluded.key_hint,
                    enabled=excluded.enabled
                """,
                (provider, key_hint, 1 if enabled else 0),
            )
        return WebSearchProfile(provider=provider, key_hint=key_hint, enabled=enabled)

    def delete_web_search(self) -> None:
        with self.repository._connect() as conn:
            conn.execute("DELETE FROM custom_web_search WHERE id = 1")
        secrets_data = self._read_secrets()
        if secrets_data.get("web_search"):
            secrets_data["web_search"] = None
            self._write_secrets(secrets_data)

    def has_ready_provider(self) -> bool:
        secrets_data = self._read_secrets()
        for profile in self.list_profiles():
            if not profile.enabled or not profile.models:
                continue
            if secrets_data["providers"].get(profile.id) or (
                profile.kind == "openai_compatible" and is_local_base_url(profile.base_url)
            ):
                return True
        return False

    def has_custom_web_search(self) -> bool:
        cfg = self.get_web_search()
        return bool(cfg and cfg.enabled and self.get_web_search_api_key())

    def public_summary(self) -> dict[str, Any]:
        secrets_data = self._read_secrets()
        profiles = [
            p.to_public_dict(
                has_key=bool(secrets_data["providers"].get(p.id))
                or (p.kind == "openai_compatible" and is_local_base_url(p.base_url))
            )
            for p in self.list_profiles()
        ]
        ws = self.get_web_search()
        ws_has_key = bool(secrets_data.get("web_search"))
        return {
            "profiles": profiles,
            "web_search": ws.to_public_dict(has_key=ws_has_key) if ws else None,
            "presets": PROVIDER_PRESETS,
        }

    def catalog_models(self) -> list[dict[str, Any]]:
        secrets_data = self._read_secrets()
        ws_configured = self.has_custom_web_search()
        catalog: list[dict[str, Any]] = []
        for profile in self.list_profiles():
            if not profile.enabled:
                continue
            has_key = bool(secrets_data["providers"].get(profile.id)) or (
                profile.kind == "openai_compatible" and is_local_base_url(profile.base_url)
            )
            if not has_key:
                continue
            supports_search = profile.kind == "anthropic" or ws_configured
            for model_id in profile.models:
                qualified = qualify_custom_model(profile.id, model_id)
                catalog.append(
                    {
                        "id": qualified,
                        "model": qualified,
                        "displayName": f"{model_id} · {profile.name}",
                        "description": f"{profile.name} ({profile.kind})",
                        "isDefault": False,
                        "providerId": profile.id,
                        "providerName": profile.name,
                        "providerKind": profile.kind,
                        "supportsWebSearch": supports_search,
                        "supportsReasoningEffort": False,
                    }
                )
        return catalog


def _extract_error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        text = response.text.strip()
        return text[:240] if text else f"HTTP {response.status_code}"
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and isinstance(err.get("message"), str):
            return err["message"]
        if isinstance(err, str):
            return err
        if isinstance(body.get("message"), str):
            return body["message"]
        if isinstance(body.get("detail"), str):
            return body["detail"]
    return f"HTTP {response.status_code}"


def _convert_items_to_anthropic(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []

    def append_block(role: str, block: dict[str, Any]) -> None:
        if messages and messages[-1]["role"] == role and isinstance(messages[-1]["content"], list):
            messages[-1]["content"].append(block)
        else:
            messages.append({"role": role, "content": [block]})

    for item in items:
        item_type = item.get("type")
        if item_type == "function_call":
            try:
                tool_input = json.loads(item.get("arguments") or "{}")
                if not isinstance(tool_input, dict):
                    tool_input = {}
            except json.JSONDecodeError:
                tool_input = {}
            append_block(
                "assistant",
                {
                    "type": "tool_use",
                    "id": item["call_id"],
                    "name": item["name"],
                    "input": tool_input,
                },
            )
            continue
        if item_type == "function_call_output":
            append_block(
                "user",
                {
                    "type": "tool_result",
                    "tool_use_id": item["call_id"],
                    "content": str(item.get("output") or ""),
                },
            )
            continue
        if item_type == "message":
            text = "".join(
                part.get("text", "")
                for part in item.get("content", [])
                if isinstance(part, dict) and part.get("type") in {"output_text", "input_text", "text"}
            )
            if text:
                append_block("assistant", {"type": "text", "text": text})
            continue
        role = item.get("role")
        if role in {"user", "developer", "assistant"}:
            mapped_role = "assistant" if role == "assistant" else "user"
            content = item.get("content")
            if isinstance(content, str) and content:
                append_block(mapped_role, {"type": "text", "text": content})
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str) and part["text"]:
                        append_block(mapped_role, {"type": "text", "text": part["text"]})
    return messages


def _convert_items_to_openai_chat(instructions: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": instructions}]
    pending_tool_calls: list[dict[str, Any]] = []

    def flush_tool_calls() -> None:
        nonlocal pending_tool_calls
        if pending_tool_calls:
            messages.append({"role": "assistant", "content": None, "tool_calls": pending_tool_calls})
            pending_tool_calls = []

    for item in items:
        item_type = item.get("type")
        if item_type == "function_call":
            pending_tool_calls.append(
                {
                    "id": item["call_id"],
                    "type": "function",
                    "function": {"name": item["name"], "arguments": item.get("arguments") or "{}"},
                }
            )
            continue
        flush_tool_calls()
        if item_type == "function_call_output":
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": item["call_id"],
                    "content": str(item.get("output") or ""),
                }
            )
            continue
        if item_type == "message":
            text = "".join(
                part.get("text", "")
                for part in item.get("content", [])
                if isinstance(part, dict) and part.get("type") in {"output_text", "input_text", "text"}
            )
            if text:
                messages.append({"role": "assistant", "content": text})
            continue
        role = item.get("role")
        if role in {"user", "developer", "assistant"}:
            mapped_role = "assistant" if role == "assistant" else "user"
            content = item.get("content")
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = "\n\n".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict) and isinstance(part.get("text"), str)
                )
            else:
                text = ""
            if text:
                messages.append({"role": mapped_role, "content": text})
    flush_tool_calls()
    return messages


class AnthropicClient:
    """Native Anthropic Messages API streaming client with prompt caching and native web search."""

    def __init__(self, *, api_key: str, base_url: str = ANTHROPIC_DEFAULT_BASE_URL, http: httpx.AsyncClient | None = None):
        self.api_key = api_key
        self.base_url = normalize_base_url("anthropic", base_url)
        self.http = http

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
            "content-type": "application/json",
            "accept": "application/json",
        }

    async def test_and_list_models(self) -> list[str]:
        async def _run(client: httpx.AsyncClient) -> list[str]:
            try:
                response = await client.get(f"{self.base_url}/models", headers=self._headers())
            except httpx.HTTPError as exc:
                raise ChatGPTError("transport_error", f"Could not reach Anthropic API: {exc}", retryable=True) from exc
            if response.status_code != 200:
                detail = _extract_error_detail(response)
                raise ChatGPTError("provider_auth_failed", f"Anthropic connection failed ({response.status_code}): {detail}", status=response.status_code)
            body = response.json()
            data = body.get("data") if isinstance(body, dict) else None
            models = [str(m.get("id")) for m in data if isinstance(m, dict) and isinstance(m.get("id"), str)] if isinstance(data, list) else []
            return models or list(ANTHROPIC_FALLBACK_MODELS)

        if self.http is not None:
            return await _run(self.http)
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await _run(client)

    async def stream(
        self,
        *,
        model: str,
        instructions: str,
        items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        enable_web_search: bool,
        on_event: Callable[[dict], Awaitable[None]],
    ) -> dict[str, Any]:
        anthropic_tools: list[dict[str, Any]] = [
            {
                "name": tool["name"],
                "description": tool.get("description") or "",
                "input_schema": tool.get("parameters") or {"type": "object", "properties": {}},
            }
            for tool in tools
            if tool.get("type") == "function"
        ]
        if enable_web_search:
            anthropic_tools.append({"type": "web_search_20250305", "name": "web_search", "max_uses": 5})

        body: dict[str, Any] = {
            "model": model,
            "max_tokens": 8192,
            "stream": True,
            "system": [{"type": "text", "text": instructions, "cache_control": {"type": "ephemeral"}}],
            "messages": _convert_items_to_anthropic(items),
        }
        if anthropic_tools:
            body["tools"] = anthropic_tools

        headers = {**self._headers(), "accept": "text/event-stream"}

        async def _run(client: httpx.AsyncClient) -> dict[str, Any]:
            try:
                async with client.stream("POST", f"{self.base_url}/messages", json=body, headers=headers) as response:
                    if response.status_code != 200:
                        await response.aread()
                        detail = _extract_error_detail(response)
                        raise ChatGPTError("provider_request_failed", f"Anthropic error ({response.status_code}): {detail}", status=response.status_code, retryable=response.status_code >= 500)
                    return await self._consume_sse(response, on_event)
            except httpx.HTTPError as exc:
                raise ChatGPTError("transport_error", f"Could not reach Anthropic API: {exc}", retryable=True) from exc

        if self.http is not None:
            return await _run(self.http)
        async with httpx.AsyncClient(timeout=180.0) as client:
            return await _run(client)

    async def _consume_sse(self, response: httpx.Response, on_event: Callable[[dict], Awaitable[None]]) -> dict[str, Any]:
        message_item_id = f"msg-{uuid4().hex[:10]}"
        text_parts: list[str] = []
        tool_blocks: dict[int, dict[str, Any]] = {}
        output_items: list[dict[str, Any]] = []
        web_searched = False
        message_announced = False

        async for line in response.aiter_lines():
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            kind = event.get("type")
            if kind == "error":
                err = event.get("error") if isinstance(event.get("error"), dict) else {}
                raise ChatGPTError("provider_stream_error", str(err.get("message") or "Anthropic stream error."))
            if kind == "content_block_start":
                idx = event.get("index", 0)
                block = event.get("content_block") or {}
                btype = block.get("type")
                if btype == "text" and not message_announced:
                    message_announced = True
                    await on_event({"type": "response.output_item.added", "item": {"type": "message", "id": message_item_id}})
                elif btype == "tool_use":
                    tool_blocks[idx] = {
                        "call_id": str(block.get("id") or f"call-{uuid4().hex[:10]}"),
                        "name": str(block.get("name") or ""),
                        "input_parts": [],
                    }
                elif btype in {"server_tool_use", "web_search_tool_result"}:
                    web_searched = True
            elif kind == "content_block_delta":
                idx = event.get("index", 0)
                delta = event.get("delta") or {}
                dtype = delta.get("type")
                if dtype == "text_delta" and isinstance(delta.get("text"), str):
                    if not message_announced:
                        message_announced = True
                        await on_event({"type": "response.output_item.added", "item": {"type": "message", "id": message_item_id}})
                    text_parts.append(delta["text"])
                    await on_event({"type": "response.output_text.delta", "item_id": message_item_id, "delta": delta["text"]})
                elif dtype == "input_json_delta" and isinstance(delta.get("partial_json"), str) and idx in tool_blocks:
                    tool_blocks[idx]["input_parts"].append(delta["partial_json"])
            elif kind == "content_block_stop":
                idx = event.get("index", 0)
                if idx in tool_blocks:
                    tb = tool_blocks.pop(idx)
                    args_str = "".join(tb["input_parts"]).strip() or "{}"
                    output_items.append({"type": "function_call", "call_id": tb["call_id"], "name": tb["name"], "arguments": args_str})

        if web_searched:
            output_items.insert(0, {"type": "web_search_call", "id": f"ws-{uuid4().hex[:8]}"})
        full_text = "".join(text_parts)
        if full_text:
            output_items.insert(0, {"type": "message", "id": message_item_id, "content": [{"type": "output_text", "text": full_text}]})
        return {"status": "completed", "output": output_items}


class OpenAICompatibleClient:
    """Generic OpenAI-compatible Chat Completions streaming client."""

    def __init__(self, *, api_key: str, base_url: str = OPENAI_DEFAULT_BASE_URL, http: httpx.AsyncClient | None = None):
        self.api_key = api_key
        self.base_url = normalize_base_url("openai_compatible", base_url)
        self.http = http

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json", "accept": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        return headers

    async def test_and_list_models(self, fallback_model: str | None = None) -> list[str]:
        async def _run(client: httpx.AsyncClient) -> list[str]:
            try:
                response = await client.get(f"{self.base_url}/models", headers=self._headers())
            except httpx.HTTPError as exc:
                raise ChatGPTError("transport_error", f"Could not reach endpoint {self.base_url}: {exc}", retryable=True) from exc
            if response.status_code == 200:
                try:
                    body = response.json()
                except ValueError:
                    body = {}
                data = body.get("data") if isinstance(body, dict) else None
                models = [str(m.get("id")) for m in data if isinstance(m, dict) and isinstance(m.get("id"), str)] if isinstance(data, list) else []
                if models:
                    return models
                if fallback_model:
                    return [fallback_model]
                return []
            if response.status_code in {404, 405} and fallback_model:
                # Some custom relays omit /models; fall back to a minimal completion probe.
                probe = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json={"model": fallback_model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1},
                )
                if probe.status_code == 200:
                    return [fallback_model]
                detail = _extract_error_detail(probe)
                raise ChatGPTError("provider_auth_failed", f"Connection failed ({probe.status_code}): {detail}", status=probe.status_code)
            detail = _extract_error_detail(response)
            raise ChatGPTError("provider_auth_failed", f"Connection failed ({response.status_code}): {detail}", status=response.status_code)

        if self.http is not None:
            return await _run(self.http)
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await _run(client)

    async def stream(
        self,
        *,
        model: str,
        instructions: str,
        items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        on_event: Callable[[dict], Awaitable[None]],
    ) -> dict[str, Any]:
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description") or "",
                    "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
                },
            }
            for tool in tools
            if tool.get("type") == "function"
        ]
        body: dict[str, Any] = {
            "model": model,
            "stream": True,
            "messages": _convert_items_to_openai_chat(instructions, items),
        }
        if openai_tools:
            body["tools"] = openai_tools
            body["parallel_tool_calls"] = False

        headers = {**self._headers(), "accept": "text/event-stream"}

        async def _run(client: httpx.AsyncClient) -> dict[str, Any]:
            try:
                async with client.stream("POST", f"{self.base_url}/chat/completions", json=body, headers=headers) as response:
                    if response.status_code != 200:
                        await response.aread()
                        detail = _extract_error_detail(response)
                        raise ChatGPTError("provider_request_failed", f"Provider error ({response.status_code}): {detail}", status=response.status_code, retryable=response.status_code >= 500)
                    return await self._consume_sse(response, on_event)
            except httpx.HTTPError as exc:
                raise ChatGPTError("transport_error", f"Could not reach provider endpoint: {exc}", retryable=True) from exc

        if self.http is not None:
            return await _run(self.http)
        async with httpx.AsyncClient(timeout=180.0) as client:
            return await _run(client)

    async def _consume_sse(self, response: httpx.Response, on_event: Callable[[dict], Awaitable[None]]) -> dict[str, Any]:
        message_item_id = f"msg-{uuid4().hex[:10]}"
        text_parts: list[str] = []
        tool_calls: dict[int, dict[str, Any]] = {}
        message_announced = False

        async for line in response.aiter_lines():
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                chunk = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(chunk.get("error"), dict):
                raise ChatGPTError("provider_stream_error", str(chunk["error"].get("message") or "Provider stream error."))
            choices = chunk.get("choices")
            if not isinstance(choices, list) or not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if isinstance(content, str) and content:
                if not message_announced:
                    message_announced = True
                    await on_event({"type": "response.output_item.added", "item": {"type": "message", "id": message_item_id}})
                text_parts.append(content)
                await on_event({"type": "response.output_text.delta", "item_id": message_item_id, "delta": content})
            tcs = delta.get("tool_calls")
            if isinstance(tcs, list):
                for tc in tcs:
                    if not isinstance(tc, dict):
                        continue
                    idx = tc.get("index", 0)
                    entry = tool_calls.setdefault(idx, {"call_id": "", "name": "", "arguments": []})
                    if isinstance(tc.get("id"), str) and tc["id"]:
                        entry["call_id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if isinstance(fn.get("name"), str) and fn["name"]:
                        entry["name"] += fn["name"]
                    if isinstance(fn.get("arguments"), str) and fn["arguments"]:
                        entry["arguments"].append(fn["arguments"])

        output_items: list[dict[str, Any]] = []
        full_text = "".join(text_parts)
        if full_text:
            output_items.append({"type": "message", "id": message_item_id, "content": [{"type": "output_text", "text": full_text}]})
        for idx in sorted(tool_calls):
            tc = tool_calls[idx]
            call_id = tc["call_id"] or f"call-{uuid4().hex[:10]}"
            args_str = "".join(tc["arguments"]).strip() or "{}"
            output_items.append({"type": "function_call", "call_id": call_id, "name": tc["name"], "arguments": args_str})
        return {"status": "completed", "output": output_items}


async def execute_external_web_search(
    *,
    provider: WebSearchKind,
    api_key: str,
    query: str,
    max_results: int = 5,
    http: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Run web search via user's optional Tavily or Brave Search API key."""
    clamped = max(1, min(max_results, 8))

    async def _run(client: httpx.AsyncClient) -> dict[str, Any]:
        if provider == "tavily":
            resp = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": api_key, "query": query, "max_results": clamped, "search_depth": "basic"},
            )
            if resp.status_code != 200:
                raise ValueError(f"Tavily search failed ({resp.status_code}): {_extract_error_detail(resp)}")
            data = resp.json()
            results = [
                {
                    "title": str(item.get("title") or "")[:200],
                    "url": str(item.get("url") or ""),
                    "snippet": str(item.get("content") or "")[:500],
                }
                for item in (data.get("results") or [])[:clamped]
                if isinstance(item, dict)
            ]
            return {"provider": "tavily", "query": query, "results": results}

        resp = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": clamped},
            headers={"Accept": "application/json", "X-Subscription-Token": api_key},
        )
        if resp.status_code != 200:
            raise ValueError(f"Brave Search failed ({resp.status_code}): {_extract_error_detail(resp)}")
        data = resp.json()
        web_items = ((data.get("web") or {}).get("results") or [])[:clamped]
        results = [
            {
                "title": str(item.get("title") or "")[:200],
                "url": str(item.get("url") or ""),
                "snippet": str(item.get("description") or "")[:500],
            }
            for item in web_items
            if isinstance(item, dict)
        ]
        return {"provider": "brave", "query": query, "results": results}

    if http is not None:
        return await _run(http)
    async with httpx.AsyncClient(timeout=20.0) as client:
        return await _run(client)
