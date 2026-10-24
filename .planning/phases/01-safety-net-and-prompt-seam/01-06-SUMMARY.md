---
phase: 01-safety-net-and-prompt-seam
plan: 06
subsystem: tests
tags: [history, neutralize, render_block, budget, worst-case, fail-first]
requires: ["01-03", "01-04", "01-05"]
provides:
  - "tests/test_history.py: 33 tests (3 budget, 30 unit) for window, neutralize, render_block, the D-10 constants and the D-11 worst-case budget"
affects: [phase-2-memory-in-prompt]
tech-stack:
  added: []
  patterns: ["hostile inputs as POISONED_DOCS parametrization and a WITHHELD_INPUTS dict; budget test goes through the real build_prompts seam"]
key-files:
  created: [tests/test_history.py]
  modified: []
key-decisions:
  - "Fail-first proof (1) checks out the four seam files (generate.py, pipeline.py, prompt.py, defenses.py) at 853f021 and keeps history.py; deleting history.py instead only gives a collection ImportError, which proves nothing about the seam"
requirements-completed: [PRMT-02]
duration: 15min
completed: 2026-10-25
status: complete
actuals:
  tasks: 2
  commits: 2
plan_head_before: 6f81799
plan_head_after: db72f09
---

# Phase 1 Plan 06: History tests Summary

New `tests/test_history.py` pins the history helpers from plan 01-05 and proves the D-11 worst case fits the context window through the real `build_prompts(..., history_block=...)` seam. No file under `rag/` changed.

## Commits

- `58b8423` test(01-06): prove the worst-case prompt fits the context window
- `db72f09` test(01-06): pin windowing, neutralizing and rendering of history

## Verification

- `python -m pytest tests/test_history.py -q -k "worst_case or constants_fit"` -> `3 passed`
- `python -m pytest tests/test_history.py -q -k "defangs or known_limit or withholds"` -> `15 passed, 18 deselected`
- `python -m pytest tests/test_history.py -q` -> `33 passed`
- `python -m pytest tests/test_prompt_snapshot.py tests/test_history.py -q` -> `111 passed`
- `git diff --quiet HEAD -- rag` exits 0; `git status --short rag` empty

## Worst-case numbers (scratch run, not left in the test)

- Rendered block of six maximal turns: 338 words (oldest turns dropped to fit 400).
- Worst case: spotlight style, book subject, 2000-character question: 2544 words, 2544 x 1.5 + 3000 + 600 = 7416 tokens <= 8192 (`MODEL_CONTEXT_TOKENS` floor; docs/models.md says max_model_len not read).
- 60-word question worst case: spotlight/book, 2204 words, 6906 tokens.

## Fail-first proofs

1. Seam files at `853f021` (`git checkout 853f021 -- rag/query/generate.py rag/query/pipeline.py rag/query/prompt.py rag/security/defenses.py`), `-k "worst_case or constants_fit"`: `2 failed, 1 passed` with `TypeError: build_prompts() got an unexpected keyword argument 'history_block'`. Restored with `git checkout HEAD -- rag`; `git diff --quiet HEAD -- rag` exit 0.
2. Span-replacement loop (`for name in scan_text(text).rules:` / `RULES[name].sub(DEFANG_MARKER, text)`) removed from `neutralize` with the Edit tool, `-k defangs`: `7 failed, 26 deselected`. Restored with `git checkout HEAD -- rag/query/history.py`; `git diff --quiet HEAD -- rag` exit 0.
3. Extra: with `rag/query/history.py` absent (pre-helper state), the module fails collection with `ModuleNotFoundError: No module named 'rag.query.history'`. Restored; diff clean.

## Deviations

None.
