import { describe, expect, it } from "vitest";
import { DEFAULT_PROVIDER_PRESETS, parseModelInputList } from "./providers";

describe("providers helpers", () => {
  it("deduplicates and trims comma or newline separated model ids", () => {
    expect(parseModelInputList(" claude-sonnet-4-5 , claude-haiku-4-5\nclaude-sonnet-4-5, ")).toEqual([
      "claude-sonnet-4-5",
      "claude-haiku-4-5",
    ]);
  });

  it("includes Anthropic native and OpenAI-compatible presets", () => {
    const anthropic = DEFAULT_PROVIDER_PRESETS.find((p) => p.id === "anthropic");
    const openrouter = DEFAULT_PROVIDER_PRESETS.find((p) => p.id === "openrouter");
    expect(anthropic?.kind).toBe("anthropic");
    expect(anthropic?.supports_native_web_search).toBe(true);
    expect(openrouter?.kind).toBe("openai_compatible");
    expect(openrouter?.supports_native_web_search).toBe(false);
  });
});
