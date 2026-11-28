---
title: Conversation Distillation and Chat Turn Revert - Plan
type: feat
date: 2026-11-26
topic: conversation-distillation-and-chat-revert
artifact_contract: ce-unified-plan/v1
product_contract_source: ce-brainstorm
execution: code
---

# Conversation Distillation and Chat Turn Revert - Plan

## Goal Capsule

- **Objective:** Enable Clew learners to distill study conversations into durable topic notes and reviewable graph expansions, and to cleanly revert mistaken sent messages without corrupting conversation state or silently mutating the graph.
- **Product Authority:** Clew core invariants (`AGENTS.md`, `docs/agents/PROJECT_CONTEXT.md`, `docs/ARCHITECTURE.md`) plus user-confirmed brainstorm decisions from this session.
- **Open Blockers:** None.

## Product Contract

### Summary

Add two complementary chat workflow capabilities to Clew: (1) an explicit **Distill conversation** action (always available in the chat composer and surfaced as a lightweight prompt after finishing a topic closure quiz) that produces a unified review card combining a structured topic summary artifact and up to 1–3 deduplicated graph node/edge proposals with independent or combined Apply actions; and (2) a per-message **Revert** action on user messages that stops any active run, removes that message and everything after it from the thread, resets the model transcript cleanly, and restores the reverted message text into the composer for quick editing.

### Problem Frame

Today, learners study a topic through chat, take the closure quiz, and close the topic window—leaving insights, mental models, quiz misconceptions, and adjacent concepts buried in chat scrollback with no structured note saved and no new nodes proposed. Separately, when a learner sends a mistaken or off-target prompt, they cannot roll back that turn and must either live with the polluted context or delete the entire topic session.

### Key Decisions

- **Explicit distillation over silent mutation** (session-settled: user-directed — chosen over automatic background graph writes: preserves Clew's non-negotiable reviewable-proposal and reversible-snapshot guarantees). Governs R1, R3, R4.
- **Always-available button + post-quiz nudge** (session-settled: user-directed — chosen over button-only or forced auto-generation: fits the learner's "chat → closure test → close node" wrap-up loop without intruding during study). Governs R1, R2.
- **Unified review card with independent apply controls** (session-settled: user-directed — chosen over all-or-nothing atomic apply or two separate cards: keeps wrap-up in one place while letting users save only the summary or only the graph nodes). Governs R3, R4, R5.
- **Four-part Summary-vs-Node split rulebook** (session-settled: user-directed — chosen over uncapped node extraction or gap-only extraction: prevents graph bloat while capturing both blindspots and worthy extensions). Governs R6.
- **Chat revert does not roll back accepted graph snapshots** (user-approved default aligned with `docs/ARCHITECTURE.md`: chat history and workspace snapshots remain decoupled and independently reversible). Governs R8, R9.

### Requirements

**Conversation Distillation**

- R1. The chat composer provides an explicit "Distill conversation" action (disabled while loading, unauthenticated, or when the thread has no messages) that triggers a distillation turn in the current session.
- R2. After completing a topic closure quiz, the topic completion notice offers a lightweight one-click action to open the topic's chat and distill the conversation.
- R3. A dedicated `propose_distillation` Clew tool returns a unified distillation review card containing an optional structured study summary (for topic conversations) and an optional validated graph proposal (for new/updated topics and edges), with at least one present.
- R4. From the unified distillation card, the user can apply both parts at once ("Apply all") or independently ("Save summary" / "Apply nodes"), with persisted applied state surviving page reloads and backend restarts.
- R5. Saving a distillation summary appends a new note artifact to the target topic (creating a reversible workspace snapshot and preserving earlier notes) without overwriting prior artifacts.
- R6. Distillation instructions enforce the combined granularity rulebook: (a) new nodes must be closure-testable standalone study units (15–45 min), (b) prioritize prerequisite gaps and misconceptions revealed in chat or quiz attempts, (c) cap newly proposed topics at 1–3 high-value items while placing smaller/future concepts into a "Further Leads / 延伸线索" section inside the summary, and (d) link-first deduplication (prefer adding an edge to an existing topic over creating a duplicate node).
- R7. Graph-level conversations (no topic selected) may distill graph proposals without requiring a topic-bound summary; topic conversations with no new nodes warranted may produce a summary-only distillation card.

**Chat Turn Revert**

- R8. Each visible user message in the chat thread exposes a Revert action that interrupts any in-flight generation in that session, deletes that user message and all subsequent messages in the session, resets the session's stored Responses transcript so future turns rebuild cleanly from remaining messages, and leaves already-accepted graph snapshots untouched.
- R9. After a successful revert, the frontend updates the thread immediately from the authoritative server response, refreshes session counts, and restores the reverted user message's text into the composer input (focusing the composer) so the user can edit and resend.

**Localization & Quality**

- R10. All new user-facing copy is localized in both English (`frontend/src/lib/appCopy.ts`) and Simplified Chinese (`frontend/src/lib/appCopy.zh-CN.ts`) with full parity passing `frontend/scripts/check-localization.mjs`.

### Scope Boundaries

- **Deferred:** Rich-text inline editing of the distillation summary inside the review card; one-click promotion of individual "Further Leads" bullets into nodes; live background ghost-node staging during chat.
- **Outside identity:** Silent AI graph mutation without user review; reverting accepted graph snapshots automatically when reverting chat messages.

## Implementation Units

### Unit 1: Backend Domain, Tool Contract & Distillation Persistence
- **Files:**
  - `backend/app/models/domain.py`: Add `DistillationSummary`, `DistillationCard`, extend `ChatAction` with `"propose_distillation"`, add `distillation: DistillationCard | None = None` to `ChatMessage`.
  - `backend/app/agent/contracts.py`: Add `DistillationSummaryDraft`, `DistillationDraft`, register `propose_distillation` in `TOOL_MODELS` and `tool_specs`.
  - `backend/app/agent/context.py`: Document `propose_distillation` and the 4-part Summary-vs-Node rulebook in `BASE_INSTRUCTIONS`.
  - `backend/app/agent/tools.py`: Handle `propose_distillation` execution (validate topic_id for summary, validate proposal via `ProposalService().prepare`, persist `message.distillation`, return `awaiting_review`).
  - `backend/app/services/repository.py`: Update `apply_proposal` to also set `message["distillation"]["proposal_applied"] = True` when a matching proposal inside a distillation card is applied; add `apply_distillation_summary(graph_id, session_id, message_id)` that atomically appends the topic artifact (creating a snapshot) and marks `summary.applied = True` and `summary.artifact_id` on the chat message (idempotent on retry).
  - `backend/app/api/chat_routes.py`: Add `POST /api/v1/graphs/{graph_id}/chat/distill/apply-summary`.

### Unit 2: Backend Chat Turn Revert
- **Files:**
  - `backend/app/services/repository.py`: Add `revert_chat_from_message(graph_id, session_id, message_id)` returning `(removed_message_ids, reverted_message)` after validating `message_id` belongs to `session_id` and has `role == "user"`, deleting all rows with `ordinal >= target_ordinal` in `chat_messages` and updating `chat_sessions.updated_at`.
  - `backend/app/agent/store.py`: Add `reset_after_revert(session_id)` to clear `agent_transcripts` and `agent_tool_results` for `session_id`, reset `agent_sessions` to `idle` (`run_id=NULL, turn_id=NULL, error=NULL, client_message_id=NULL`), while preserving `agent_events` so `last_event_id` stays strictly monotonic.
  - `backend/app/agent/runtime.py`: Add `async def revert_message(self, graph_id: str, session_id: str, message_id: str) -> dict` that interrupts any active run for `session_id`, calls repository truncation + store reset, and returns `{thread, reverted_prompt, reverted_message_id}`.
  - `backend/app/api/chat_routes.py`: Add `POST /api/v1/graphs/{graph_id}/chat/revert` (`RevertMessageRequest`).

### Unit 3: Frontend Types, Copy, Controller & UI
- **Files:**
  - `frontend/src/lib/types.ts`: Add `DistillationSummary`, `DistillationCard`, `distillation?: DistillationCard | null` on `ChatMessage`.
  - `frontend/src/lib/appCopy.ts` & `frontend/src/lib/appCopy.zh-CN.ts`: Add EN & zh-CN copy for distillation button, prompt, card labels, apply/saved states, post-quiz distill action, and revert button/errors.
  - `frontend/src/lib/chatPresentation.ts`: Include `message.distillation` in `cards` and `propose_distillation` in `progressLabel`.
  - `frontend/src/hooks/useGraphChatController.ts`: Add `revertMessage(messageId: string)` calling `/chat/revert`, updating chat state + restoring composer input, and refreshing sessions.
  - `frontend/src/WorkspaceApp.tsx`: Wire `distillConversation()`, `applyDistillationSummary(messageId)`, `applyDistillationProposal(messageId, proposal)`, `applyDistillationAll(messageId, distillation)`, `revertMessage`, and post-quiz `distillAfterQuiz()`.
  - `frontend/src/components/assistant/AssistantThread.tsx`: Render the unified `.distillationCard` (Summary section + Proposal section + Apply all / Save summary / Apply nodes buttons) and the per-user-message Revert button.
  - `frontend/src/components/assistant/AssistantComposer.tsx`: Add the "Distill / 提炼对话" action button.
  - `frontend/src/components/WorkspaceShell.tsx` & `WorkspaceShellAuxWindows.tsx`: Thread the new handlers and render the lightweight post-quiz distill button next to `quizSuccess`.
  - `frontend/src/styles/components/` (chat/proposal CSS): Add clean, minimal styles for `.distillationCard` and `.chatRevertButton` matching Clew's existing design tokens.

### Unit 4: Verification & Tests
- Backend unit tests (`backend/tests/`):
  - `propose_distillation` tool validation (summary-only, proposal-only, combined, invalid topic_id, empty payload rejection).
  - `apply_distillation_summary` idempotency, artifact persistence, snapshot creation, and `apply_proposal` marking `distillation.proposal_applied = True`.
  - `POST /api/v1/graphs/{graph_id}/chat/revert` truncating messages, clearing transcript, preserving monotonic `last_event_id`, rejecting non-user or unknown message_id, and keeping accepted graph snapshots intact.
- Frontend tests & checks (`frontend/`):
  - Localization parity (`node scripts/check-localization.mjs`).
  - Typecheck (`npm run typecheck`), unit tests (`npm test`), and production build (`npm run build`).
