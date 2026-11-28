import { describe, expect, it } from "vitest";

import { formatQuotedPrompt, normalizeQuotedText } from "./chatQuote";

describe("chatQuote", () => {
  it("formats single-line and multi-line quotes as a Markdown blockquote above the question", () => {
    expect(formatQuotedPrompt("ReadView decides visibility.\nUndo log stores older rows.", "Why does this avoid locks?")).toBe(
      "> ReadView decides visibility.\n> Undo log stores older rows.\n\nWhy does this avoid locks?",
    );
  });

  it("returns the trimmed question unchanged when no quote is present", () => {
    expect(formatQuotedPrompt(null, "  Explain MVCC  ")).toBe("Explain MVCC");
    expect(formatQuotedPrompt("   ", "Explain MVCC")).toBe("Explain MVCC");
  });

  it("truncates overly long selections cleanly", () => {
    const longText = "a".repeat(2500);
    const normalized = normalizeQuotedText(longText);
    expect(normalized.length).toBeLessThanOrEqual(2001);
    expect(normalized.endsWith("…")).toBe(true);
  });
});
