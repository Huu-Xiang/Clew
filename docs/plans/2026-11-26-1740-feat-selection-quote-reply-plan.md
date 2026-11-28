---
title: Selection Quote Reply in Chat - Plan
type: feat
date: 2026-11-26
topic: selection-quote-reply
artifact_contract: ce-unified-plan/v1
product_contract_source: ce-brainstorm
execution: code
---

# Selection Quote Reply in Chat - Plan

## Goal Capsule

- **Objective:** Let Clew learners select any sentence or passage inside an assistant reply and quote it directly into a follow-up question, matching the low-friction quote-reply workflow of Codex and ChatGPT.
- **Product Authority:** Clew graph-first UI invariants (`AGENTS.md`) and user request.
- **Open Blockers:** None.

## Product Contract

### Summary

When the learner highlights text inside an assistant message in the chat thread, a floating "Ask about this / 引用追问" button appears near the selection. Clicking it attaches the quoted snippet as a dismissible quote card above the composer input and focuses the input; sending prepends the quote as a Markdown blockquote before the learner's question and clears the pending quote.

### Requirements

- R1. Selecting non-empty text inside an assistant message displays a floating quote action button positioned near the selection inside the chat thread viewport.
- R2. Clicking the floating quote button stores the trimmed selection in the active session's chat state (`quotedText`), clears the text selection, and focuses the composer textarea.
- R3. While `quotedText` is present, the composer displays a compact quote card above the input with a dismiss (`×`) button.
- R4. Sending a user message while `quotedText` is set formats the prompt as a Markdown blockquote followed by the user's question, clears both `input` and `quotedText`, and restores both if the request is rejected.
- R5. All new strings are localized in both English (`appCopy.ts`) and Simplified Chinese (`appCopy.zh-CN.ts`) passing `check-localization.mjs`.

## Implementation Units

- `frontend/src/lib/appContracts.ts`: Add `quotedText?: string | null` to `GraphChatState`.
- `frontend/src/lib/chatQuote.ts` & `frontend/src/lib/chatQuote.test.ts`: Pure helper `formatQuotedPrompt(quote, question)` + unit tests.
- `frontend/src/lib/appCopy.ts` & `frontend/src/lib/appCopy.zh-CN.ts`: Add EN/zh-CN strings for selection quote button, quote label, and clear button.
- `frontend/src/components/assistant/AssistantThread.tsx`: Detect selection inside `.chatMessage-assistant .chatCopy`, position and render the floating quote pill button.
- `frontend/src/components/assistant/AssistantComposer.tsx`: Render dismissible `.composerQuoteBar` above the textarea when `currentChatState.quotedText` is set.
- `frontend/src/hooks/useGraphChatController.ts`: Compose quoted prompt in `sendChat`, clear `quotedText` on send, and restore on rejection.
- `frontend/src/styles/components/chat.css`: Style `.chatSelectionQuoteBtn` and `.composerQuoteBar`.
