---
phase: 02-conversation-store-and-memory-in-the-answer-prompt
plan: 01
subsystem: planning
tags: [context-window, phase-contract, p2-base]
requires: ["01-05", "01-07"]
provides:
  - "P2_BASE: the commit the fail-first proofs of plans 02-05 to 02-08 check old files out at"
  - "docs/models.md: Phase 2 re-read outcome and the Value in force line (MODEL_CONTEXT_TOKENS = 8192)"
  - ".planning/STATE.md: Phase 2 max_model_len bullet"
affects: [02-02, 02-05, 02-06, 02-07, 02-08]
tech-stack:
  added: []
  patterns: []
key-files:
  created: [.planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-01-SUMMARY.md]
  modified: [docs/models.md, .planning/STATE.md]
key-decisions:
  - "Probe failed with WinError 10054 (tunnel forward resets); per the owner's decision of 2026-10-25 the 8192-token floor stays in force and the re-read is deferred to the merge gate"
requirements-completed: [PRMT-04]
completed: 2026-10-25
status: complete
actuals:
  tasks: 2
  commits: 2
---

# Phase 2 Plan 01: Phase 1 contract, base commit and context window

## Phase 2 base

P2_BASE=346cd43e71f9943432eafe38a03a690a658b2dc2
2026-10-25, `docs(01): mark phase 1 complete`

`git status --porcelain -- rag tests` printed nothing before the hash was taken.

## Phase 1 contract check

Output: `phase 1 contract ok` (exit 0). The four seam callables take `history_block=""`, `HistoryTurn` fields are in order, `render_block` shapes, `window`, the D-15 numbers (6, 400, 40, 60, 50, 1.5) and `MODEL_CONTEXT_TOKENS >= 8192` all match. No mismatch.

## Phase 1 suites

- `python -m pytest tests/test_prompt_snapshot.py tests/test_history.py -q`: `111 passed in 0.87s`
- Phase 1 baseline (STATE.md): pytest baseline after Phase 1 is 702 passed, 2 skipped (704 collected)

## Context window

- Phase 1 section said "not read on 2026-10-24", so the probe ran once (10-second timeout, no retry).
- Probe output: `ConnectionResetError: [WinError 10054] An existing connection was forcibly closed by the remote host`
- Case (c): other failure, recorded with the exact error text. The owner chose (2026-10-25) to continue on the floor and re-read before the merge gate (parked in STATE.md).
- Value in force for Phase 2: `MODEL_CONTEXT_TOKENS = 8192`. No D-15 number changed.

## Commits

- 33a2587 docs(02-01): record the context window in force for phase 2 (docs/models.md)
- a32468d docs(02-01): note the context window in force for phase 2 (.planning/STATE.md)

## Deviations

None. No file under rag/ or tests/ changed.
