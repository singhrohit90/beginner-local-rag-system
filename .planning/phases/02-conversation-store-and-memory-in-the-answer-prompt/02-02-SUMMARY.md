---
phase: 02-conversation-store-and-memory-in-the-answer-prompt
plan: 02
subsystem: query
tags: [prompt-budget, history, context-window]
requires: ["02-01"]
provides:
  - "rag/query/history.py: THINKING_TOKENS, ANSWER_TOKENS, CONVERSATION_MAX_STORED_WORDS, estimate_prompt_tokens, fits_context, block_turns"
affects: [02-03, 02-04, 02-08]
tech-stack:
  added: []
  patterns: ["budget constants read from module globals at call time (monkeypatchable)"]
key-files:
  created: [.planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-02-SUMMARY.md]
  modified: [rag/query/history.py]
key-decisions:
  - "MODEL_CONTEXT_TOKENS stays 8192 (docs/models.md Value in force for Phase 2; owner decision 2026-10-25); only its comment changed"
requirements-completed: [PRMT-04, PRMT-01]
completed: 2026-10-25
status: complete
actuals:
  tasks: 2
  commits: 2
---

# Phase 2 Plan 02: Prompt budget helpers

## Commits

- 6a008d8 feat(02-02): add the prompt budget check to the history helpers
- e7d18fc feat(02-02): add the stored-word cap and the block turn count

## Results

- Worst realistic follow-up (1999-character question, five 300-word passages, spotlight, document,
  six-turn window of seven maximal turns) through `build_prompts`: estimate **3815** tokens;
  3815 + 3000 + 600 = 7415 <= 8192, so it fits.
- `MODEL_CONTEXT_TOKENS = 8192`, source: docs/models.md, Context window, line
  "Value in force for Phase 2: `MODEL_CONTEXT_TOKENS = 8192`" (a floor, not a measurement).

## Verify lines

- Task 1 tracer: `budget tracer ok 3815` (equality fits, one over refused, ceil rounding, constants read at call time)
- Task 2: `constants ok 8192`
- `python -m pytest tests/test_prompt_snapshot.py tests/test_history.py -q`: `111 passed`
- `python -m pytest tests -q`: `702 passed, 2 skipped` (Phase 1 baseline)
- `git diff --name-only P2_BASE -- rag`: `rag/query/history.py` only
- No forbidden imports, no default arguments on the budget functions, no line over 120 characters

## Fail-first

- Before Task 1 the tracer failed: `AttributeError: module 'rag.query.history' has no attribute 'estimate_prompt_tokens'`
- Before Task 2 the constants check failed: `AttributeError: ... no attribute 'CONVERSATION_MAX_STORED_WORDS'`

## Deviations

- The `CONVERSATION_MAX_STORED_WORDS` trailing comment was shortened (D-15/D-16 reference dropped) to stay under 120 characters.
- Phase 1's two-line comment above `MODEL_CONTEXT_TOKENS` ("replace it at the start of Phase 2") was replaced by the plan's trailing comment, since Phase 2 has now recorded the value in force.
