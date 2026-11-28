const MAX_QUOTED_LENGTH = 2000;

export function normalizeQuotedText(raw: string): string {
  const cleaned = raw.replace(/\r\n/g, "\n").trim();
  if (!cleaned) return "";
  return cleaned.length > MAX_QUOTED_LENGTH ? `${cleaned.slice(0, MAX_QUOTED_LENGTH).trimEnd()}…` : cleaned;
}

export function formatQuotedPrompt(quotedText: string | null | undefined, question: string): string {
  const trimmedQuestion = question.trim();
  const normalizedQuote = normalizeQuotedText(quotedText ?? "");
  if (!normalizedQuote) return trimmedQuestion;
  const blockquote = normalizedQuote
    .split("\n")
    .map((line) => `> ${line}`)
    .join("\n");
  return `${blockquote}\n\n${trimmedQuestion}`;
}
