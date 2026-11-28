---
title: Collapsible Zone Macro-Nodes, Non-Overlapping Zone Layout, and Cross-Zone Edge Focus - Plan
type: feat
date: 2026-11-28
topic: zone-macro-nodes-non-overlapping-layout-and-edge-focus
artifact_contract: ce-unified-plan/v1
product_contract_source: lfg
execution: code
---

# Collapsible Zone Macro-Nodes, Non-Overlapping Zone Layout, and Cross-Zone Edge Focus - Plan

## Goal Capsule

- **Objective:** Learners with 30+ topic graphs can view their graph as clean, collapsible module macro-nodes (expanding sub-nodes on click) or as completely non-overlapping zone territories with muted background cross-zone wires that light up on hover or selection.
- **Means:** Upgrade `computeTreeLayout` to a two-level zone-first DAG layout (non-overlapping zone bounding boxes + intra-zone mini-trees), add collapsible zone macro-nodes with aggregated inter-zone edges and clickable zone pills/cards in `GraphCanvas`, and dim unfocused cross-zone edges until hovered or selected.
- **Open Blockers:** None.

## Implementation Units

- **IU1. Two-Level Non-Overlapping Zone Tree Layout (`frontend/src/lib/treeLayout.ts`, `frontend/src/lib/treeLayout.test.ts`)**
  - When 2+ zones exist, build a deterministic cycle-safe Zone Meta-DAG, layer zones into macro-ranks, lay out each zone's internal `requires` mini-tree independently, and pack zone bounding boxes with generous gaps so zone convex hulls never overlap in either `vertical` or `horizontal` mode.
- **IU2. Collapsible Zone Macro-Nodes & Aggregated Edges (`frontend/src/lib/collapsedZones.ts`, `frontend/src/lib/collapsedZones.test.ts`, `frontend/src/components/GraphCanvas.tsx`)**
  - Persist per-graph collapsed zone IDs in `localStorage`; auto-expand a zone if a topic inside it is explicitly selected.
  - Render collapsed zones as interactive Macro-Node cards showing zone title, `completed / total` count, progress bar, and ready indicator; aggregate cross-zone edges to/from collapsed macro-nodes without duplicates or self-loops; make expanded zone header pills clickable (`▾`) to collapse individual zones, plus a one-click toolbar button (`分区总览 / 展开全部`) to collapse or expand all zones at once.
- **IU3. Cross-Zone Edge De-emphasis & Hover Highlight (`frontend/src/components/GraphCanvas.tsx`)**
  - Add pointer hover tracking for nodes, macro-nodes, and zone pills; keep intra-zone edges and macro-edges crisp, dim unfocused cross-zone topic-to-topic edges to ~28% alpha, and highlight incident upstream/downstream edges on hover or selection.
- **IU4. Toolbar Wiring, Localization & Verification (`frontend/src/WorkspaceApp.tsx`, `frontend/src/components/WorkspaceShell.tsx`, `frontend/src/components/TopStatsOverlay.tsx`, `frontend/src/components/WorkspaceShellOverlayControls.tsx`, `frontend/src/lib/appCopy.ts`, `frontend/src/lib/appCopy.zh-CN.ts`)**
  - Wire `allZonesCollapsed` / `toggleCollapseAllZones` into the 2D toolbar with full EN + zh-CN parity and verify all frontend & backend tests and production build.

## Verification Contract

- Frontend: `npm run typecheck && node scripts/check-localization.mjs && NODE_OPTIONS="--localstorage-file=/tmp/clew-vitest-ls" npx vitest run --fileParallelism=false && npm run build` passes 100%.
- Backend: `PYTHONPATH=backend ./.venv/bin/python -m unittest discover -s backend/tests -v` passes 100%.
