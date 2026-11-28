import { API_BASE } from "./api";
import { apiFetch } from "./apiRequest";
import type { CustomProviderKind, ProviderPreset, ProvidersSummary, WebSearchKind } from "./types";

export const DEFAULT_PROVIDER_PRESETS: ProviderPreset[] = [
  {
    id: "anthropic",
    label: "Anthropic (Claude)",
    kind: "anthropic",
    base_url: "https://api.anthropic.com/v1",
    default_models: ["claude-sonnet-4-5", "claude-opus-4-1", "claude-haiku-4-5"],
    supports_native_web_search: true,
  },
  {
    id: "openai",
    label: "OpenAI API",
    kind: "openai_compatible",
    base_url: "https://api.openai.com/v1",
    default_models: ["gpt-4.1", "gpt-4.1-mini", "o4-mini"],
    supports_native_web_search: false,
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    kind: "openai_compatible",
    base_url: "https://openrouter.ai/api/v1",
    default_models: ["anthropic/claude-sonnet-4.5", "openai/gpt-4.1", "google/gemini-2.5-pro"],
    supports_native_web_search: false,
  },
  {
    id: "deepseek",
    label: "DeepSeek",
    kind: "openai_compatible",
    base_url: "https://api.deepseek.com/v1",
    default_models: ["deepseek-chat", "deepseek-reasoner"],
    supports_native_web_search: false,
  },
  {
    id: "gemini",
    label: "Google Gemini",
    kind: "openai_compatible",
    base_url: "https://generativelanguage.googleapis.com/v1beta/openai",
    default_models: ["gemini-2.5-pro", "gemini-2.5-flash"],
    supports_native_web_search: false,
  },
  {
    id: "ollama",
    label: "Ollama (Local)",
    kind: "openai_compatible",
    base_url: "http://127.0.0.1:11434/v1",
    default_models: ["qwen2.5:14b", "llama3.1:8b"],
    supports_native_web_search: false,
  },
  {
    id: "custom",
    label: "Custom OpenAI-Compatible",
    kind: "openai_compatible",
    base_url: "",
    default_models: [],
    supports_native_web_search: false,
  },
];

async function providerRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  if (options?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await apiFetch(`${API_BASE}/api/v1/providers${path}`, { ...options, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof payload.detail === "string" ? payload.detail : `Request failed (${response.status})`);
  }
  return payload as T;
}

export function fetchProviders(): Promise<ProvidersSummary> {
  return providerRequest<ProvidersSummary>("");
}

export function testProviderConnection(input: {
  kind: CustomProviderKind;
  base_url?: string;
  api_key?: string;
  profile_id?: string;
  model?: string;
}): Promise<{ ok: boolean; models: string[] }> {
  return providerRequest<{ ok: boolean; models: string[] }>("/test", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function saveCustomProvider(input: {
  id?: string;
  name: string;
  kind: CustomProviderKind;
  base_url?: string;
  api_key?: string;
  models: string[];
  enabled?: boolean;
}): Promise<ProvidersSummary & { ok: boolean }> {
  return providerRequest<ProvidersSummary & { ok: boolean }>("", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function deleteCustomProvider(profileId: string): Promise<ProvidersSummary & { ok: boolean }> {
  return providerRequest<ProvidersSummary & { ok: boolean }>(`/${encodeURIComponent(profileId)}`, {
    method: "DELETE",
  });
}

export function saveWebSearchConfig(input: {
  provider: WebSearchKind;
  api_key?: string;
  enabled?: boolean;
}): Promise<ProvidersSummary & { ok: boolean }> {
  return providerRequest<ProvidersSummary & { ok: boolean }>("/web-search", {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export function deleteWebSearchConfig(): Promise<ProvidersSummary & { ok: boolean }> {
  return providerRequest<ProvidersSummary & { ok: boolean }>("/web-search", {
    method: "DELETE",
  });
}

export function parseModelInputList(raw: string): string[] {
  return Array.from(
    new Set(
      raw
        .split(/[\n,]+/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}
