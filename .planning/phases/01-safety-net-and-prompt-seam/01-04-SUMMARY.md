---
phase: 01-safety-net-and-prompt-seam
plan: 04
subsystem: tests
tags: [prompt, history_block, seam, snapshot, tests]
requires: ["01-01", "01-03"]
provides:
  - "HISTORY_BLOCK_SAMPLE, snapshot_trace() in tests/test_prompt_snapshot.py"
  - "test_empty_history_equals_no_history_equals_snapshot (24), test_history_block_position (24), test_pipeline_answer_and_stream_forward_history_block (3), test_answer_from_context_forwards_history_block (1)"
affects: [01-06, phase-2-memory-in-prompt]
tech-stack:
  added: []
  patterns: ["fail-first proof on committed code: check the seam files out at 853f021, run, git checkout HEAD -- them"]
key-files:
  created: []
  modified: [tests/test_prompt_snapshot.py]
requirements-completed: [PRMT-02]
duration: 10min
completed: 2026-10-25
status: complete
actuals:
  tasks: 2
  commits: 2
plan_head_before: f909d46
plan_head_after: b66ca95
---

# Phase 1 Plan 04: seam tests Summary

52 tests appended to `tests/test_prompt_snapshot.py` prove the `history_block` seam: an omitted, `""` or `None` block gives the committed snapshot bytes in all 24 cases; a non-empty block lands directly before `Question: ` (and before the spotlight `Reminder:`) with the system prompt unchanged; `RagPipeline.answer`, `RagPipeline.stream` and `answer_from_context` forward it, and a later call without it sends the snapshot again.

## Commits

- `ff4213e` test(01-04): prove an empty history block keeps the snapshot bytes
- `b66ca95` test(01-04): pin where a history block lands and that the pipeline forwards it

Each commit touches only `tests/test_prompt_snapshot.py`.

## Fail-first proof (pre-seam files)

`git checkout 853f021 -- rag/query/prompt.py rag/query/generate.py rag/security/defenses.py rag/query/pipeline.py`, run, then `git checkout HEAD --` the same four files; `git diff --quiet HEAD -- rag` exit 0 and `git status --short rag` empty after each proof.

- Task 1, `-k empty_history`: `24 failed, 26 deselected in 0.27s`, all `TypeError: build_prompts() got an unexpected keyword argument 'history_block'`
- Task 2, `-k "history_block_position or pipeline or answer_from_context"`: `28 failed, 50 deselected in 0.62s` (24 `build_prompts()`, 3 `RagPipeline.answer()`, 1 `answer_from_context()` TypeErrors on `history_block`)

## Verification

- `-k empty_history`: `24 passed, 26 deselected`
- After Task 1, whole module: `50 passed in 0.14s`
- `-k "history_block_position or pipeline or answer_from_context"`: `28 passed, 50 deselected`
- Whole module: `78 passed in 0.50s`
- Snapshot gate: last commit touching `tests/snapshots` is `4b73d94 test(01-01): pin single-turn prompt bytes before the prompt seam`; no uncommitted fixture change
- Affected files `tests/test_prompt_snapshot.py tests/test_generation.py tests/test_security.py tests/test_stream_api.py`: `142 passed in 13.94s` (90 from 01-03 plus 52)
- No added line over 120 characters

## Deviations from Plan

- `answer_from_context` test unpacks `_, prompt` instead of `answer, prompt` (the answer is unused; repo keeps code free of unused variables).
- The long assert in that test is split through an `expected` local to stay within 120 characters.

## Self-Check: PASSED
