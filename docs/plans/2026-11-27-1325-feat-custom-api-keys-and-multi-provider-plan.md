---
title: Custom API Keys and Multi-Provider Model Support - Plan
type: feat
date: 2026-11-27
topic: custom-api-keys-and-multi-provider
artifact_contract: ce-unified-plan/v1
product_contract_source: ce-brainstorm
execution: code
---

# Custom API Keys and Multi-Provider Model Support - Plan

## Goal Capsule

- **Objective:** Learners can connect Clew to Anthropic (Claude) and any OpenAI-compatible AI provider using their own API keys—without needing a ChatGPT subscription—and switch models freely mid-conversation while preserving graph editing, study tools, and credential security.
- **Means:** Add built-in Anthropic native and OpenAI-compatible provider adapters alongside the existing ChatGPT OAuth flow, store custom keys in the OS keychain, relax the startup sign-in gate, and support native or optional BYOK web search.
- **Product Authority:** This Product Contract owns user-facing provider setup, startup entry, model switching, cross-provider conversation continuity, capability signaling, and web-search behavior. Implementation architecture and endpoints are left to `ce-plan`.
- **Open Blockers:** None.

## Product Contract

### Summary

Add bring-your-own-key (BYOK) multi-provider support to Clew so users can configure Anthropic (native Messages API) and OpenAI-compatible providers (OpenAI API, OpenRouter, Gemini, DeepSeek, Ollama, custom relays) alongside existing ChatGPT OAuth. Users can enter the workspace from the welcome screen with either ChatGPT sign-in or a custom API key, switch models across providers at any time without breaking existing conversations, and use native web search where supported or an optional custom search API key where not.

### Problem Frame

Clew currently gates workspace entry behind ChatGPT Plus/Pro OAuth (`frontend/src/App.tsx`) and hardcodes the OpenAI Responses API (`backend/app/agent/chatgpt_api.py`, `backend/app/agent/runtime.py`). Learners who prefer Claude, use API relays or OpenRouter, or run local models cannot use Clew at all without a ChatGPT subscription. Meanwhile, Clew's agent loop persists raw Responses API transcript items (`backend/app/agent/store.py`) and unconditionally injects OpenAI-only parameters (`web_search`, `reasoning.encrypted_content`), which would fail immediately against non-OpenAI providers.

### Key Decisions

- **Built-in dual adapters (Anthropic native + OpenAI-compatible) alongside existing ChatGPT OAuth** (session-settled: user-approved — chosen over LiteLLM proxy or OpenAI-compatible-only: avoids extra local daemon/infrastructure while preserving Anthropic prompt caching and native web search). Governs R1, R2, R8.
- **Welcome screen offers side-by-side ChatGPT sign-in and custom API key setup** (session-settled: user-directed — chosen over open-canvas-first or skip-welcome: keeps first-run onboarding clean while removing the hard ChatGPT subscription gate). Governs R3.
- **Native web search when supported, explicit notice plus optional BYOK web-search key when not** (session-settled: user-directed — chosen over disabling web search for all custom keys: gives Claude/ChatGPT native search out of the box while letting OpenAI-compatible users opt into search with a Tavily/Brave key). Governs R8, R9.
- **OS keychain storage with no plaintext key persistence** (aligned with existing `KeyringCredentialStore` invariant in `backend/app/agent/chatgpt_auth.py`). Governs R4.
- **Explicit fail-closed behavior with no silent provider fallback** (aligned with `AGENTS.md`). Governs R10, R11.

### Requirements

**Provider Coverage & Connections**

R1. Clew supports three connection types concurrently: existing ChatGPT OAuth, Anthropic native API (with prompt caching enabled on static system/graph context), and generic OpenAI-compatible Chat Completions endpoints (with configurable Base URL, API key, and model IDs).
R2. Users can create, edit, test, and delete multiple named provider profiles in Settings (for example: Anthropic Official, OpenRouter, DeepSeek, Local Ollama) and keep ChatGPT OAuth connected at the same time.
R3. The welcome screen (`SignIn`) allows entering the workspace once any valid provider is configured—either via ChatGPT OAuth or by adding and verifying a custom API key directly from the welcome screen.

**Credential Security & Validation**

R4. Custom provider API keys and optional web-search API keys are stored exclusively in the OS credential store (keychain) and are never persisted in plaintext inside SQLite, workspace JSON, or frontend storage; UI responses only expose masked key hints.
R5. Each custom provider profile provides a one-click connection test that verifies reachability and credentials, reports actionable errors on failure (invalid key, unreachable Base URL, unauthorized model), and attempts to fetch available models while always allowing manual model ID entry.

**Model Switching & Conversation Continuity**

R6. The chat model selector groups available models by connected provider profile and lets the user switch models or default workspace model across providers at any time.
R7. When a user switches to a model backed by a different provider protocol mid-session, Clew automatically rebuilds conversation context from the canonical chat message history (including applied proposal, distillation, and quiz receipts) instead of replaying incompatible raw provider transcripts.

**Capabilities & Web Search**

R8. Providers with native web search (ChatGPT OAuth and Anthropic native) use their built-in web search automatically during chat turns; closure quiz generation remains offline.
R9. For providers without native web search, Clew omits unsupported native search parameters, shows a clear non-intrusive indicator when web search is unavailable, and offers an optional Settings entry for a third-party search API key (such as Tavily or Brave Search) that enables a `web_search` tool for those models.
R10. Provider-specific request options (such as `reasoning.effort` and `reasoning.encrypted_content`) are sent only to providers that declare support for them; unsupported options are never blindly forwarded.
R11. All existing Clew agent tools (graph read/propose, conversation distillation, inline/closure quizzes, and bound local material tools) work identically through Clew's server-side validation and snapshot boundaries across supported providers; if a configured model or endpoint fails tool calling or returns an error, Clew surfaces the error explicitly without silently falling back to another model or provider.

**Localization**

R12. All new welcome screen, settings, connection test, model selector, and capability notice strings are provided in both English and Simplified Chinese with full key parity.

### Key Flows

F1. **First-run onboarding with a custom API key**
- **Trigger:** User launches Clew with no ChatGPT session and no configured custom provider.
- **Steps:** Welcome screen displays "Sign in with ChatGPT" and "Use custom API key". User selects custom API key, picks a preset (Anthropic, OpenAI, OpenRouter, DeepSeek, or Custom OpenAI-compatible), enters API key (and Base URL / model if needed), and clicks Verify & Continue. Backend validates the connection, saves the key to the OS keychain, persists profile metadata, and unlocks the workspace.
- **Covers R1, R3, R4, R5.**

F2. **Adding and testing another provider in Settings**
- **Trigger:** User opens Settings → Account & Models and clicks "Add provider".
- **Steps:** User fills profile name, provider type, optional Base URL, and API key, then clicks "Test connection". Backend probes the endpoint, populates fetched models (plus manual model input), and shows either success with model count or a clear error message. User saves the profile; its models immediately appear in the chat model switcher.
- **Covers R2, R4, R5, R6.**

F3. **Switching providers mid-conversation**
- **Trigger:** User has an active thread started with ChatGPT and switches the chat model dropdown to an Anthropic Claude model (or vice versa), then sends a new message.
- **Steps:** Backend detects that the stored transcript protocol differs from the newly selected provider's protocol, bypasses the incompatible raw transcript, hydrates context from canonical `chat_messages` + current `turn_context`, and streams the reply normally with full tool support.
- **Covers R6, R7, R10, R11.**

F4. **Web search across native and non-native providers**
- **Trigger:** User asks a current-events or lookup question while using either Anthropic Claude or a DeepSeek/OpenAI-compatible profile.
- **Steps:** On Anthropic, Clew attaches Claude's native web search tool and streams grounded results. On a generic OpenAI-compatible profile without a search key, Clew runs without web search and displays a subtle capability hint linking to Settings; once the user configures an optional Tavily/Brave search key in Settings, Clew exposes a custom `web_search` tool to that model.
- **Covers R8, R9, R10.**

### Acceptance Examples

AE1. **Zero-ChatGPT entry:** Given a fresh Clew installation with no ChatGPT login, when the user enters a valid Anthropic API key on the welcome screen and submits, then Clew opens the workspace, stores the key only in the OS keychain, and can stream a chat reply and propose a graph edit with Claude. **Covers R1, R3, R4, R11.**
AE2. **Mid-thread provider switch:** Given a chat thread containing 4 turns with ChatGPT (including a tool call and reasoning items in `agent_transcripts`), when the user switches the model selector to an OpenRouter or Anthropic model and asks a follow-up question, then the turn completes without protocol errors and references the prior conversation accurately. **Covers R6, R7, R10.**
AE3. **Bad credentials fail closed:** Given an invalid API key or mistyped Base URL during "Test connection" or chat, when the request is sent, then Clew displays a clear, localized error message and does not save broken credentials as active or fall back to another configured provider. **Covers R5, R11, R12.**
AE4. **No plaintext leakage:** Given saved Anthropic, OpenAI-compatible, and optional search API keys, when inspecting the SQLite database, workspace config JSON, and API responses to the frontend, then zero raw API keys appear anywhere outside the OS keychain. **Covers R4.**
AE5. **Web search fallback path:** Given an OpenAI-compatible provider (e.g. DeepSeek), when no custom search key is configured, then chat requests do not send OpenAI Responses `web_search` payloads and the UI indicates web search is off; when a valid optional search key is configured in Settings, then the model receives a working `web_search` tool during chat turns (and not during closure quizzes). **Covers R8, R9, R10.**

### Scope Boundaries

**Out of Scope / Deferred for Later:**
- Automatic silent fallback across providers on rate limits or errors (explicitly violates Clew's transparent billing and fail-closed invariants).
- Per-task automatic model routing (e.g., separate default models for chat vs closure quizzes vs distillation — can be added in a follow-up once multi-provider basics are solid).
- External gateway daemons (LiteLLM Proxy, Redis, Docker sidecars).
- Token cost/usage analytics dashboard.
- OAuth flows for non-ChatGPT providers (only API keys for non-ChatGPT providers in this phase).

### Outstanding Questions

**Resolve Before Planning:**
- None.

**Deferred to Planning:**
- Exact internal `LLMProvider` abstraction shape in `backend/app/agent/` and whether to use raw `httpx` SSE parsers (matching `chatgpt_api.py`) or official Python SDKs (`anthropic`, `openai`).
- Which optional third-party web search providers to support in v1 (e.g., Tavily and/or Brave Search) and result truncation limits.
- API route layout: extending `/api/v1/chatgpt/*` vs introducing a unified `/api/v1/providers/*` route family while keeping backward compatibility for existing ChatGPT endpoints.
- How `agent_transcripts` stores protocol metadata (`provider_protocol` column vs wrapper JSON) and handles SQLite migration cleanly for existing local DBs.

### Sources / Research

- `frontend/src/App.tsx` — current ChatGPT-only workspace entry gate (`ready = !!chatgpt.account?.authenticated && chatgpt.account.sharing`).
- `frontend/src/components/SignIn.tsx` & `frontend/src/components/ChatGPTAccountPanel.tsx` — current welcome screen and account/model settings UI.
- `backend/app/agent/chatgpt_api.py` & `backend/app/agent/runtime.py` — current Responses API client, event loop, and hardcoded `web_search` / `reasoning.encrypted_content` injection.
- `backend/app/agent/chatgpt_auth.py` — existing `KeyringCredentialStore` OS keychain pattern with no plaintext fallback.
- `backend/app/agent/store.py` — `agent_transcripts` storage and `reset_after_revert` pattern.
- `docs/ideation/2026-11-27-custom-api-keys-and-providers-ideation.html` — prior ideation exploring adapter options and rejected alternatives.

## Implementation Units

- **IU1. Backend Provider Registry, Keychain Store & Dual Adapters (`backend/app/agent/providers.py`)**
  - Add `ProviderProfile`, `WebSearchConfig`, `ProviderCredentialStore` (OS keychain via `keyring`, no plaintext fallback), `ProviderRegistry` (SQLite metadata + keychain secrets), `AnthropicClient` (`/v1/messages` SSE + prompt caching + native `web_search_20250305` + tool calling), `OpenAICompatibleClient` (`/v1/chat/completions` SSE + tool calling + `/models` discovery), and `execute_web_search` (Tavily / Brave).
- **IU2. Runtime, Transcript Protocol Isolation, Auth Gate & Routes (`backend/app/agent/store.py`, `backend/app/agent/runtime.py`, `backend/app/agent/contracts.py`, `backend/app/agent/tools.py`, `backend/app/main.py`, `backend/app/api/provider_routes.py`, `backend/app/api/routes.py`)**
  - Track `provider_protocol` on `agent_transcripts` and auto-rehydrate from `chat_messages` when protocol changes mid-thread.
  - Dispatch `AgentRuntime._execute()` to ChatGPT, Anthropic, or OpenAI-compatible clients with capability-gated `web_search` and `reasoning_effort`, plus optional BYOK `web_search` tool for non-native providers.
  - Expose `/api/v1/providers/*` routes and update `main.py` middleware to unlock `/api/*` when either ChatGPT OAuth or a custom provider is ready while keeping `/api/v1/providers/*` accessible for onboarding.
- **IU3. Frontend Onboarding, Settings & Model Switcher (`frontend/src/App.tsx`, `frontend/src/components/SignIn.tsx`, `frontend/src/components/CustomProvidersPanel.tsx`, `frontend/src/components/ChatGPTAccountPanel.tsx`, `frontend/src/components/SettingsModal.tsx`, `frontend/src/components/WorkspaceShellAuxWindows.tsx`, `frontend/src/lib/types.ts`, `frontend/src/lib/appCopy.ts`, `frontend/src/lib/appCopy.zh-CN.ts`)**
  - Add custom API key onboarding directly on `SignIn.tsx` and relax `App.tsx` gate via `account.ready`.
  - Add multi-profile custom provider & optional web-search key management in Settings.
  - Show provider-grouped models in Settings and the chat model menu.
- **IU4. Automated Verification (`backend/tests/test_custom_providers.py`, frontend unit tests)**
  - Unit tests covering keychain-only storage (no plaintext in SQLite/API), Anthropic SSE + tool calling + prompt caching + native web search, OpenAI-compatible SSE + tool calling + optional Tavily/Brave search, mid-thread protocol switch rehydration, access boundary unlock/relock, and frontend typecheck/localization/vitest/build.

## Verification Contract

- Backend: `PYTHONPATH=backend ./.venv/bin/python -m unittest discover -s backend/tests -v` passes 100%.
- Frontend: `npm run typecheck && node scripts/check-localization.mjs && NODE_OPTIONS="--localstorage-file=/tmp/clew-vitest-ls" npm test && npm run build` passes 100%.
