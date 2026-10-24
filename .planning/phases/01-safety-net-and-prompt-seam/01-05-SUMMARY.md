---
phase: 01-safety-net-and-prompt-seam
plan: 05
subsystem: query
tags: [history, neutralize, render_block, budget-constants, guard]
requires: ["01-02"]
provides:
  - "rag/query/history.py: HistoryTurn, window, neutralize, render_block"
  - "HISTORY_WINDOW_TURNS=6, HISTORY_BLOCK_MAX_WORDS=400, HISTORY_ANSWER_MAX_WORDS=40, HISTORY_QUESTION_MAX_WORDS=60, CONVERSATION_MAX_TURNS=50, TOKENS_PER_WORD=1.5, MODEL_CONTEXT_TOKENS=8192 (floor)"
  - "HISTORY_HEADER, DEFANG_MARKER, HISTORY_WITHHELD, TRUNCATION_MARKER"
affects: [01-06, phase-2-memory-in-prompt]
tech-stack:
  added: []
  patterns: ["neutralize reuses guard RULES/scan_text/filter_output and generate._CITATION; no new regex list"]
key-files:
  created: [rag/query/history.py]
  modified: []
key-decisions:
  - "MODEL_CONTEXT_TOKENS = 8192 floor: docs/models.md Context window says max_model_len was not read on 2026-10-24 (tunnel down); replace at the start of Phase 2 (D-11, D-13)"
  - "neutralize uses the strict filter_output(text, \"\"): any URL or image in a stored turn withholds that text"
  - "Span defang runs before the [S n] strip so spoofed-citation can still match"
  - "render_block shows turn.question as typed, not turn.rewritten"
requirements-completed: [PRMT-02]
duration: 10min
completed: 2026-10-25
status: complete
actuals:
  tasks: 2
  commits: 2
plan_head_before: ae3cf40c29f100ffdb0b02c2b03d6ffe95bf7220
plan_head_after: ab0147e
---

# Phase 1 Plan 05: Pure history helpers Summary

New `rag/query/history.py` holds the pure history helpers and the D-10 budget constants. It does no I/O, takes no owner, calls no LLM, and nothing under `rag/api` calls it yet. `render_block([])` returns `""`, so the first turn of every conversation keeps the snapshot-identical prompt.

## Commits

- `860e72f` feat(01-05): add pure history helpers and budget constants
- `ab0147e` feat(01-05): defang untrusted history and cap the block size

## MODEL_CONTEXT_TOKENS

`8192`, a floor and not a measurement. Source: `docs/models.md`, section `## Context window`, which records that `max_model_len` was not read on 2026-10-24 (tunnel down). The value is not below 8192, so D-10's premise holds.

## Verification

- Task 1 tracer: `tracer ok`
- Task 1 constants: `constants ok`
- Task 2 guard: `guard ok` (7 scanner-flagged POISONED_DOCS defanged or withheld and re-scan clean; canary and URL withheld; 6 x 160-word turns capped at 400 words, newest kept, oldest dropped)
- Task 2 tracer plus rag diff gate: `tracer still ok`, gate exit 0 (only the five phase files differ from 853f021 under rag/)
- `grep -nE '^(import re|from rag\.common\.config)' rag/query/history.py`: no lines
- No line over 120 characters
- `python -m pytest tests/test_prompt_snapshot.py -q`: `26 passed in 0.14s`

## Deviations from Plan

None - plan executed exactly as written. No tests in this plan (they are plan 01-06), so no fail-first stash proof was needed.

## Known limit

P04, P07 and P08 (written to evade the scanner) pass through `neutralize` unchanged apart from whitespace; this is the scanner's stated limit and plan 01-06 pins it as a known-limit test.

## Self-Check: PASSED
