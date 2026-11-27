---
title: Topic Skip, Fresh Non-Repeating Quizzes, and Mistake Review - Plan
type: feat
date: 2026-11-27
topic: topic-skip-fresh-quizzes-and-mistake-review
artifact_contract: ce-unified-plan/v1
product_contract_source: ce-brainstorm
execution: code
---

# Topic Skip, Fresh Non-Repeating Quizzes, and Mistake Review - Plan

## Goal Capsule

- **Objective:** Learners are never blocked on a topic they already feel ready to move past, get fresh questions on every quiz retake, and receive durable, interactive mistake reviews that explain why their wrong answers missed and how to correct them.
- **Means:** Expose a per-topic skip / mark-as-mastered action that preserves real quiz history, feed prior asked/missed questions into closure quiz generation to prevent repeats, and persist structured wrong-answer reviews in the topic popover with a one-click AI coaching handoff from both the quiz results dialog and the topic popover.
- **Product Authority:** This Product Contract owns user-facing topic skip behavior, quiz history preservation, question freshness expectations, persistent mistake review display, and AI mistake-coaching entry points. Implementation details are deferred to `ce-plan`.
- **Open Blockers:** None.

## Product Contract

### Summary

Add three tightly coupled improvements to Clew's topic completion and quiz loop: (1) a one-click "Skip / Mark mastered" action on any uncompleted topic (and on failed quiz results) that unlocks downstream topics while preserving real quiz attempt scores; (2) fresh, non-repeating questions on every quiz retake by passing prior question history to the quiz generator; and (3) a persistent mistake review section in the topic popover paired with a "Review mistakes with AI" button in both the quiz result modal and topic popover that launches a targeted correction walkthrough in the topic's chat thread.

### Problem Frame

When closure tests are enabled (Clew's default), the topic popover (`frontend/src/components/WorkspaceShell.tsx`) hides `markTopicFinished` completely, forcing learners to re-take a quiz even when they feel ready to move on (for example after scoring 67% right below a 75% threshold). Meanwhile, `repository.mark_topic_finished` (`backend/app/services/repository.py`) wipes prior `quiz_attempts` and fabricates a synthetic 100% attempt, erasing real progress history. On retakes, `runtime.generate_closure_quiz` (`backend/app/agent/runtime.py`) sends no record of previously asked questions, so retakes frequently repeat the same prompts. Finally, `QuizDialog` (`frontend/src/components/dialogs/QuizDialog.tsx`) only shows a transient list of results with no footer action, so closing the modal discards detailed wrong-answer feedback without helping the learner understand or correct their misconceptions.

### Key Decisions

- **Allow skipping any uncompleted topic at any time while preserving real quiz history** (session-settled: user-directed — chosen over requiring at least one failed attempt or adding a separate "skipped" graph state: keeps the graph state model simple, unblocks learners immediately, and avoids falsifying past quiz scores). Governs R1, R2, R3.
- **Combine one-click AI mistake coaching in chat with a persistent mistake review card in the topic popover** (session-settled: user-directed — chosen over auto-sending to chat or notes-only storage: gives learners explicit control over when to invoke AI while keeping missed questions inspectable after closing the quiz dialog). Governs R6, R7, R8.
- **Prevent repeated quiz questions by supplying prior topic prompts to generation** (aligned with Clew's model-as-decision-engine stance in `AGENTS.md`). Governs R4, R5.

### Requirements

**Topic Skip & Progress Integrity**

R1. Any uncompleted topic whose prerequisites are satisfied (or when the user chooses to skip it directly) displays a secondary "Skip / Mark mastered" action in the topic popover even while closure tests remain enabled, and also shows the action in the quiz results footer when a quiz attempt does not pass.
R2. Triggering "Skip / Mark mastered" marks the topic as completed (`solid`), unlocks downstream topics that depend on it, and creates a reversible snapshot.
R3. Skipping or manually marking a topic finished preserves all existing real `QuizAttempt` records (such as prior 20% or 67% scores) instead of deleting them or fabricating a 100% test score.

**Fresh Non-Repeating Quiz Retakes**

R4. Clew retains the question prompts previously asked for a topic across quiz attempts and supplies recent prior prompts to the model whenever generating a new closure quiz for that topic.
R5. Quiz generation instructs the model to create fresh questions from new angles or scenarios rather than repeating or trivially rephrasing prior prompts, while optionally re-testing concepts from previously missed questions using new scenarios.

**Persistent Mistake Review & AI Coaching**

R6. Grading a quiz persists structured wrong-answer review items (question prompt, learner's selected wrong choice, correct choice, and explanation) on the attempt so they survive closing the quiz dialog and page reloads.
R7. When a quiz submission contains one or more wrong answers, the quiz results dialog displays a "Review mistakes with AI" action in its footer; clicking it opens or switches to that topic's chat session and sends a structured coaching prompt containing the missed questions, wrong choices, and correct answers so the assistant explains each misconception and invites follow-up questions.
R8. When a topic's latest quiz attempt contains wrong answers, the topic popover displays a collapsible or compact "Recent mistake review" section showing the missed items and providing the same "Review mistakes with AI" button at any time.

**Localization**

R9. All new skip, retake, mistake review, and AI coaching UI labels and prompts are localized in both English and Simplified Chinese with full key parity.

### Key Flows

F1. **Skipping a topic after a near-miss attempt (or upfront)**
- **Trigger:** Learner scores 67% on a topic quiz (below 75%) or decides they already know an uncompleted topic and clicks "Skip / Mark mastered" in the quiz results footer or topic popover.
- **Steps:** Backend marks the topic `solid`, preserves prior quiz attempts intact, writes a reversible snapshot, and returns the updated workspace. Downstream topics immediately unlock and reflect as ready on the graph.
- **Covers R1, R2, R3.**

F2. **Retaking a topic quiz with fresh questions**
- **Trigger:** Learner clicks "Take test" again on a topic that already has one or more prior quiz attempts.
- **Steps:** Backend collects prior question prompts for this topic (plus missed concepts), passes them in the closure quiz generation prompt with a non-repetition directive, validates the returned questions, and opens the new quiz session.
- **Covers R4, R5.**

F3. **Reviewing mistakes with AI immediately after grading**
- **Trigger:** Learner submits a quiz with at least one wrong answer and clicks "Review mistakes with AI" in the quiz results footer.
- **Steps:** Clew closes the quiz dialog, opens the assistant panel on that topic's chat session, and sends a structured review request listing each missed question, the learner's chosen option, and the right option. The assistant explains why each wrong answer is a misconception, clarifies the correct concept, and lets the learner ask follow-up questions.
- **Covers R6, R7.**

F4. **Re-visiting saved mistakes later from the topic popover**
- **Trigger:** Learner closes the quiz dialog, later clicks the same topic node on the graph, and expands the "Recent mistake review" section.
- **Steps:** Topic popover renders the persisted wrong-answer items from the latest attempt (prompt, your answer, correct answer, explanation) alongside a "Review mistakes with AI" button that triggers the same coaching flow as F3.
- **Covers R6, R8.**

### Acceptance Examples

AE1. **Skip preserves history and unlocks downstream:** Given Topic A (prerequisite of Topic B) with prior quiz attempts of 20% and 67% and `closureTestsEnabled = true`, when the learner clicks "Skip / Mark mastered" on Topic A, then Topic A becomes `solid`, Topic B becomes unlocked, a reversible snapshot is created, and the 20% and 67% attempts remain present in history (no synthetic 100% score overwrites them). **Covers R1, R2, R3.**
AE2. **Retake avoids prior prompts:** Given Topic A already has a prior quiz session with 6 questions, when the learner starts a second closure quiz for Topic A, then the model prompt includes the prior question prompts with an explicit instruction not to repeat them. **Covers R4, R5.**
AE3. **Mistake review persists across reload:** Given a learner submits a quiz with 2 wrong answers and closes the modal (and reloads the page), when they open Topic A's popover, then those 2 wrong answers (prompt, selected wrong choice, correct choice, explanation) are still displayed in the "Recent mistake review" section. **Covers R6, R8.**
AE4. **One-click AI mistake coaching:** Given a quiz result with 2 wrong answers, when the learner clicks "Review mistakes with AI", then Clew opens the topic's chat thread and sends a message containing both missed questions, the learner's wrong answers, and the correct answers so the assistant explains the mistakes. **Covers R7.**
AE5. **Perfect score hides mistake review:** Given a learner scores 100% with zero wrong answers, when viewing the quiz results or topic popover, then no empty mistake review box or "Review mistakes with AI" button is shown. **Covers R7, R8.**

### Scope Boundaries

**Out of Scope / Deferred for Later:**
- Spaced repetition (Anki / SM-2) scheduling or review calendar reminders.
- Adding a separate `skipped` topic state or new node color on the canvas (reuses `solid` for completion simplicity).
- Changing the global default pass threshold (already configurable in Settings).

### Outstanding Questions

**Resolve Before Planning:**
- None.

**Deferred to Planning:**
- Exact data field names on `QuizAttempt` (`missed_reviews: list[QuizQuestionReview]` and `asked_prompts: list[str]`) with backward-compatible defaults for existing SQLite snapshots.
- How `repository.mark_topic_finished` handles topics with unclosed prerequisites when skipped directly (close only the target topic vs also closing unclosed prerequisites, matching existing repository tests).
- Prompt length cap on prior `asked_prompts` passed to `generate_closure_quiz` (e.g., last 30 prompts for the topic) to keep token usage bounded.

### Sources / Research

- `backend/app/services/quiz_service.py` — `build_closure_status`, `start_session`, and `grade_session` (already produces `QuizQuestionReview` items).
- `backend/app/services/repository.py` — `mark_topic_finished` (lines 610-648, currently deletes prior `quiz_attempts` and inserts synthetic `score=1.0`).
- `backend/app/agent/runtime.py` — `generate_closure_quiz` (line 244, currently sends no prior question history).
- `frontend/src/components/WorkspaceShell.tsx` — topic popover completion button (lines 1510-1524, currently hides `markTopicFinished` when `closureTestsEnabled` is true).
- `frontend/src/components/dialogs/QuizDialog.tsx` — quiz results modal (lines 49-69, currently omits footer actions when `reviews` is shown).

## Implementation Units

- **IU1. Backend QuizAttempt Enrichment, History-Preserving Skip, and Fresh Quiz Generation (`backend/app/models/domain.py`, `backend/app/services/quiz_service.py`, `backend/app/services/repository.py`, `backend/app/api/routes.py`, `backend/app/agent/runtime.py`)**
  - Add `missed_reviews: list[QuizQuestionReview]` and `asked_prompts: list[str]` (default empty lists) to `QuizAttempt`, populated in `QuizService.grade_session()`.
  - Update `repository.mark_topic_finished(graph_id, topic_id, preserve_history: bool = False)` (or `preserve_history=True` when skipping with existing real attempts) so real quiz attempts (e.g. 20%, 67%) are preserved intact when skipping a topic while still unlocking downstream topics and creating a reversible snapshot; keep backward compatibility when no prior attempts exist.
  - Update `AgentRuntime.generate_closure_quiz()` to collect prior `asked_prompts` and `missed_questions` for the topic (capped at the last 30 unique prompts) and instruct the model not to repeat or trivially rephrase prior questions while testing weak areas from fresh angles.
- **IU2. Frontend Skip Action, Persistent Mistake Review, and One-Click AI Coaching (`frontend/src/lib/types.ts`, `frontend/src/lib/appCopy.ts`, `frontend/src/lib/appCopy.zh-CN.ts`, `frontend/src/WorkspaceApp.tsx`, `frontend/src/components/WorkspaceShell.tsx`, `frontend/src/components/AppDialogs.tsx`, `frontend/src/components/dialogs/QuizDialog.tsx`)**
  - Add `missed_reviews?: QuizQuestionReview[]` to frontend `QuizAttempt`.
  - Expose a secondary "Skip / Mark mastered" button in the topic popover (even when `closureTestsEnabled` is true) and in the failed quiz results footer.
  - Add a "Review mistakes with AI" button in `QuizDialog` footer whenever wrong answers exist, and a persistent "Recent mistake review" collapsible section in the topic popover when the latest attempt has `missed_reviews`, both launching a structured coaching message in the topic's chat session.
- **IU3. Automated Verification (`backend/tests/test_quiz_skip_and_review.py`, frontend tests)**
  - Test skip preserving prior attempts and unlocking downstream topics, fresh-quiz prompt injection of prior `asked_prompts`, persistence of `missed_reviews` across reload, and full backend + frontend verification suites.

## Verification Contract

- Backend: `PYTHONPATH=backend ./.venv/bin/python -m unittest discover -s backend/tests -v` passes 100%.
- Frontend: `npm run typecheck && node scripts/check-localization.mjs && NODE_OPTIONS="--localstorage-file=/tmp/clew-vitest-ls" npm test && npm run build` passes 100%.
