---
title: Local Material and Codebase Grounding - Plan
type: feat
date: 2026-11-26
topic: local-material-grounding
artifact_contract: ce-unified-plan/v1
product_contract_source: ce-brainstorm
execution: code
---

# Local Material and Codebase Grounding - Plan

## Goal Capsule

- **Objective:** Allow Clew learners to attach local source code repositories, Markdown/text docs, and PDFs to a graph—and optionally pin key files on individual topics—so AI explanations and closure quizzes are grounded in real local files with explicit citations.
- **Product Authority:** Clew core invariants (`AGENTS.md`, `docs/agents/PROJECT_CONTEXT.md`, `docs/ARCHITECTURE.md`) plus user-confirmed decisions from this session.
- **Open Blockers:** None.

## Product Contract

### Summary

Add read-only local material grounding to Clew: each graph can bind one or more local folders (source code repos, Markdown/TXT notes, PDFs) shared across its topics, and each topic can pin key relative file paths. The Clew agent gains three strictly read-only, root-confined tools (`list_materials`, `search_materials`, `read_material`) available in both study chat and closure-quiz generation so explanations cite exact `file:line` / PDF page references and closure quizzes test real code and document comprehension.

### Key Decisions

- **Graph-level folder bindings + per-topic key files** (session-settled: user-directed — chosen over graph-only or topic-only binding: avoids re-binding a repo per topic while giving closure quizzes focused starting files).
- **Code + Markdown/TXT + PDF text extraction in v1** (session-settled: user-directed — chosen over code-only or PDF-only: supports studying a codebase alongside design docs and papers).
- **Strict read-only root confinement** (aligned with `AGENTS.md` fail-closed boundary: resolve symlinks and reject any path escaping a bound root; skip `.git`, `node_modules`, virtualenvs, build outputs, and binary files).

### Requirements

- R1. A graph stores a list of bound local material roots (`material_sources`: id, label, path) managed via explicit add/remove API endpoints and persisted in workspace snapshots.
- R2. A topic stores optional pinned key file references (`key_files`: source_id, relative_path, optional note) managed via add/remove API endpoints and included in topic context.
- R3. Read-only material service validates that every accessed path resolves inside a bound root (fail-closed on traversal or symlink escape), skips ignored directories (`.git`, `node_modules`, `.venv`, `dist`, `build`, `__pycache__`, `target`), and supports text/code files (line-numbered slices) and PDF files (page-numbered text extraction).
- R4. Clew exposes three read-only agent tools—`list_materials`, `search_materials`, `read_material`—available in normal chat turns AND in `CLOSURE_QUIZ_TOOLS` when the graph has bound material sources, so both explanations and closure tests ground themselves in real files.
- R5. Frontend provides a clean "Materials / 资料库" management UI for the active graph (add folder via desktop native picker or path input, remove folder) and a "Key files / 重点文件" list inside the topic popover, with full English and Simplified Chinese localization parity.

## Implementation Units

### Unit 1: Backend Domain, Material Service & Persistence
- `backend/pyproject.toml`: Add `pypdf>=5.0.0` for local PDF text extraction.
- `backend/app/models/domain.py`: Add `MaterialSource` (`id`, `label`, `path`), `TopicKeyFile` (`id`, `source_id`, `path`, `note`), add `material_sources: list[MaterialSource]` on `StudyGraph` and `key_files: list[TopicKeyFile]` on `Topic`.
- `backend/app/services/material_service.py`: Implement strictly read-only, root-confined `MaterialService` with `list_files`, `search_text`, and `read_slice` (supporting line ranges for code/text and page ranges for `.pdf` via `pypdf`).
- `backend/app/services/repository.py`: Add `add_material_source`, `remove_material_source`, `add_topic_key_file`, `remove_topic_key_file` (each creating a reversible snapshot).
- `backend/app/api/routes.py`: Add REST endpoints for graph material sources and topic key files.

### Unit 2: Agent Tools, Context & Closure Quiz Grounding
- `backend/app/agent/contracts.py`: Add `ListMaterialsDraft`, `SearchMaterialsDraft`, `ReadMaterialDraft`; register in `TOOL_MODELS`, `tool_specs`, and include them in `CLOSURE_QUIZ_TOOLS`.
- `backend/app/agent/tools.py`: Add `LABELS` and `execute_tool` handlers for `list_materials`, `search_materials`, `read_material`.
- `backend/app/agent/context.py`: Include `material_sources` in `graph_context` and instruct the model in `BASE_INSTRUCTIONS` to read real bound files (prioritizing `selected_topic.key_files` when teaching or authoring closure quizzes) and cite `file:line` or PDF page numbers.
- `backend/app/agent/runtime.py`: Update `generate_closure_quiz` prompt to instruct reading the topic's key files / bound materials when `graph.material_sources` is non-empty.

### Unit 3: Desktop IPC & Frontend UI
- `desktop/preload.cjs`, `desktop/main.cjs`, `frontend/src/lib/desktop.ts`: Add `pickMaterialFolder()` IPC returning a selected local directory path on Electron.
- `frontend/src/lib/types.ts`: Add `MaterialSource`, `TopicKeyFile`, `material_sources` on `GraphEnvelope`, `key_files` on `Topic`.
- `frontend/src/lib/appCopy.ts` & `frontend/src/lib/appCopy.zh-CN.ts`: Add EN & zh-CN strings for Materials management and Topic key files.
- `frontend/src/WorkspaceApp.tsx`, `frontend/src/components/WorkspaceShell.tsx`, `frontend/src/components/SettingsModal.tsx` (or graph materials modal): Wire add/remove material source (with desktop folder picker + manual path input) and add/remove topic key file in the topic popover.

### Unit 4: Tests & Verification
- `backend/tests/test_materials.py`: Test path-traversal / symlink-escape rejection, directory listing & ignore rules, keyword search across code + PDF, line-slice & PDF page reading, repository add/remove snapshots, and `CLOSURE_QUIZ_TOOLS` access.
- Frontend `typecheck`, `check-localization.mjs`, `npm test`, `npm run build`, and `npm run test:desktop`.
