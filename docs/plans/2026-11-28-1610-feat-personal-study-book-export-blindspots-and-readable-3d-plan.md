---
title: Personal Study Book & Blindspot Cheat-Sheet Export, Confusion Distillation, and High-Contrast Stratified 3D Graph - Plan
type: feat
date: 2026-11-28
topic: personal-study-book-export-blindspots-and-readable-3d
artifact_contract: ce-unified-plan/v1
product_contract_source: lfg
execution: code
---

# Personal Study Book & Blindspot Cheat-Sheet Export, Confusion Distillation, and High-Contrast Stratified 3D Graph - Plan

## Goal Capsule

- **Objective:** Let learners export their graph as a personal study book (`.html` interactive GitBook-style reader + `.md` single-file book) or a focused blindspot cheat-sheet (`blindspots_only`), upgrade conversation distillation (`提炼对话`) and add one-click blindspot distillation (`提炼盲区`) to capture personal confusions & quiz mistakes, and overhaul the 3D graph into a readable, high-contrast stratified prerequisite terrace layout.
- **Means:** Add `backend/app/services/study_book_export.py` with cycle-safe Zone Meta-DAG + intra-zone topological ordering, quiz mistake & chat Q&A aggregation, strict XSS-safe HTML/Markdown rendering, and optional isolated AI blindspot synthesis; upgrade `propose_distillation` prompts/UI for confusion capture; rewrite `graph3dCore.ts` and `Graph3DCanvas.tsx` for stratified Y-terraces, non-overlapping X-Z zone islands, muted fog, and high-contrast pill labels.
- **Open Blockers:** None.

## Implementation Units

- **IU1. Backend Study Book & Blindspot Export + Optional AI Synthesis** (`backend/app/models/api.py`, `backend/app/services/study_book_export.py`, `backend/app/services/repository.py`, `backend/app/agent/contracts.py`, `backend/app/agent/tools.py`, `backend/app/agent/runtime.py`, `backend/app/api/routes.py`)
- **IU2. Upgraded Conversation Distillation & One-Click Blindspot Action** (`backend/app/agent/context.py`, `backend/app/agent/contracts.py`, `frontend/src/lib/appCopy.ts`, `frontend/src/lib/appCopy.zh-CN.ts`, `frontend/src/WorkspaceApp.tsx`, `frontend/src/components/assistant/AgentInteraction.tsx`, `frontend/src/components/assistant/AssistantComposer.tsx`, `frontend/src/components/WorkspaceShell.tsx`)
- **IU3. Frontend Export Modal Options & Download** (`frontend/src/lib/types.ts`, `frontend/src/WorkspaceApp.tsx`, `frontend/src/components/AppDialogs.tsx`, `frontend/src/components/dialogs/ExportGraphDialog.tsx`)
- **IU4. High-Contrast Stratified 3D Graph** (`frontend/src/components/graph3dCore.ts`, `frontend/src/components/graph3dCore.test.ts`, `frontend/src/components/Graph3DCanvas.tsx`)

## Verification Contract

- Backend: `PYTHONPATH=backend ./.venv/bin/python -m unittest discover -s backend/tests -v` passes 100% (including new `backend/tests/test_study_book_export.py`).
- Frontend: `cd frontend && npm run typecheck && node scripts/check-localization.mjs && rm -f /tmp/clew-vitest-ls && NODE_OPTIONS="--localstorage-file=/tmp/clew-vitest-ls" npx vitest run --fileParallelism=false && npm run build` passes 100%.
- GitHub PR #1 CI (`CI / checks`) passes green after push.
