---
phase: 01-safety-net-and-prompt-seam
plan: 03
subsystem: query
tags: [prompt, history_block, seam, snapshot]
requires: ["01-01"]
provides:
  - "build_user_prompt, spotlight_user_prompt, build_prompts, answer_from_context: last keyword history_block=\"\""
  - "RagPipeline.answer(trace, history_block=\"\") and RagPipeline.stream(trace, history_block=\"\")"
affects: [01-04, 01-06, phase-2-memory-in-prompt]
tech-stack:
  added: []
  patterns: ["empty-default seam: `if not history_block:` returns the old expression byte for byte"]
key-files:
  created: []
  modified: [rag/query/prompt.py, rag/query/generate.py, rag/security/defenses.py, rag/query/pipeline.py]
key-decisions:
  - "naive style forwards history_block like standard and spotlight (RESEARCH A6 over ARCHITECTURE.md line 178); silently dropping a block would be a trap for callers"
  - "Under spotlight the block sits after the passages and before Question/Reminder, outside the nonce tags (T-01-07 accepted for Phase 1; Phase 2 verifies PRMT-03)"
requirements-completed: [PRMT-02]
duration: 10min
completed: 2026-10-25
status: complete
actuals:
  tasks: 2
  commits: 2
plan_head_before: ae3cf40c29f100ffdb0b02c2b03d6ffe95bf7220
plan_head_after: f29a30d
---

# Phase 1 Plan 03: history_block prompt seam Summary

One keyword parameter, `history_block: str = ""`, now runs through the four prompt builders and the two `RagPipeline` methods. An empty (or `None`) block executes the old return expression unchanged; a non-empty block is inserted immediately before `Question: `.

## Commits

- `edd8b72` feat(01-03): add the history_block seam on the standard prompt path
- `f29a30d` feat(01-03): extend the history_block seam to spotlight, naive and stream

## Verification

- Before editing: `python -m pytest tests/test_prompt_snapshot.py -q` -> `26 passed in 0.16s`
- Task 1 tracer: `tracer ok`
- Task 1 snapshot: `26 passed in 0.14s`
- Fingerprint of SYSTEM_PROMPT + DOCUMENT_SYSTEM_PROMPT + SPOTLIGHT_ADDENDUM + NAIVE_SYSTEM_PROMPT: `b69624ed9d1a5781` (unchanged from 853f021)
- Task 2 all-styles check: `all styles ok` (3 styles x 2 subjects; spotlight Reminder after the block)
- Affected-file suite `tests/test_prompt_snapshot.py tests/test_generation.py tests/test_security.py tests/test_stream_api.py`: `90 passed in 14.61s` = 26 snapshot + 64, matching plan 01-01's affected-file baseline `64 passed in 11.60s`
- Signature grep gate: exit 0
- Fingerprint plus rag diff gate (only the five phase files differ from 853f021 under rag/): exit 0
- Added lines all at or under 120 characters

## Decision: naive forwards the block

`naive` forwards `history_block` like the other styles. Reversible: one argument in one branch.

## Deviations from Plan

None - plan executed exactly as written. No new tests in this plan (the seam's tests are plan 01-04), so no fail-first stash proof was needed.

## Self-Check: PASSED
