from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agent.chatgpt_auth import ChatGPTError
from app.agent.providers import (
    AnthropicClient,
    OpenAICompatibleClient,
    ProviderKind,
    WebSearchKind,
    is_local_base_url,
    normalize_base_url,
)
from app.api.deps import get_agent_runtime

router = APIRouter(prefix="/api/v1/providers")


class TestProviderRequest(BaseModel):
    kind: ProviderKind
    base_url: str | None = None
    api_key: str | None = None
    profile_id: str | None = None
    model: str | None = None


class UpsertProviderRequest(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=80)
    kind: ProviderKind
    base_url: str | None = None
    api_key: str | None = None
    models: list[str] = Field(default_factory=list)
    enabled: bool = True


class UpsertWebSearchRequest(BaseModel):
    provider: WebSearchKind
    api_key: str | None = None
    enabled: bool = True


@router.get("")
def list_providers(runtime=Depends(get_agent_runtime)) -> dict:
    return runtime.providers.public_summary()


@router.post("/test")
async def test_provider(body: TestProviderRequest, runtime=Depends(get_agent_runtime)) -> dict:
    try:
        base_url = normalize_base_url(body.kind, body.base_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    api_key = (body.api_key or "").strip()
    if not api_key and body.profile_id:
        api_key = runtime.providers.get_api_key(body.profile_id) or ""
    if not api_key and not (body.kind == "openai_compatible" and is_local_base_url(base_url)):
        raise HTTPException(status_code=400, detail="API key is required to test this connection.")

    try:
        if body.kind == "anthropic":
            client = AnthropicClient(api_key=api_key, base_url=base_url, http=runtime.provider_http)
            models = await client.test_and_list_models()
        else:
            client = OpenAICompatibleClient(api_key=api_key, base_url=base_url, http=runtime.provider_http)
            models = await client.test_and_list_models(fallback_model=(body.model or "").strip() or None)
    except ChatGPTError as exc:
        raise HTTPException(status_code=400 if exc.status and exc.status < 500 else 502, detail=str(exc)) from exc

    return {"ok": True, "models": models}


@router.post("")
def upsert_provider(body: UpsertProviderRequest, runtime=Depends(get_agent_runtime)) -> dict:
    try:
        profile = runtime.providers.upsert_profile(
            profile_id=body.id,
            name=body.name,
            kind=body.kind,
            base_url=body.base_url,
            models=body.models,
            api_key=body.api_key,
            enabled=body.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ChatGPTError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True, "profile": profile.to_public_dict(has_key=True), **runtime.providers.public_summary()}


@router.delete("/{profile_id}")
def delete_provider(profile_id: str, runtime=Depends(get_agent_runtime)) -> dict:
    if runtime._active():
        raise HTTPException(status_code=409, detail="Stop active conversations before removing a provider.")
    deleted = runtime.providers.delete_profile(profile_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Provider profile not found.")
    return {"ok": True, **runtime.providers.public_summary()}


@router.put("/web-search")
def upsert_web_search(body: UpsertWebSearchRequest, runtime=Depends(get_agent_runtime)) -> dict:
    try:
        profile = runtime.providers.set_web_search(
            provider=body.provider,
            api_key=body.api_key,
            enabled=body.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ChatGPTError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True, "web_search": profile.to_public_dict(has_key=True), **runtime.providers.public_summary()}


@router.delete("/web-search")
def delete_web_search(runtime=Depends(get_agent_runtime)) -> dict:
    runtime.providers.delete_web_search()
    return {"ok": True, **runtime.providers.public_summary()}
