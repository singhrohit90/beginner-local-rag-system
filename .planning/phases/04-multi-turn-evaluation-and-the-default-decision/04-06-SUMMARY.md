---
phase: 04-multi-turn-evaluation-and-the-default-decision
plan: 06
status: complete
requirements: [EVAL-01]
---

# 04-06 Summary: tests for the multi-turn golden loader and the committed set

New file `tests/test_golden_conversations.py` (39 tests): the valid-row round trip, the committed set's coverage and
page check, a 28-case reject table (`BAD_ROWS`), the EVAL-01 edges (touching ranges, empty file, blank lines and file
order, duplicate ids with the line), `load_golden` unchanged (45 questions, 37 answerable, a conversation row still a
`TypeError`), no row text in the rewriter prompts, the review file listing every row, and the CLI counts.

## Verification

- Task 1: `3 passed` (`-k "valid_row or committed_set"`; the page test ran, not skipped). Baseline at P4_BASE: the
  loader module did not exist (ImportError).
- Task 2: module `39 passed`; `--collect-only -k bad_row` collects 28 reject cases.
- P4_BASE check: `rag/observe/golden.py`, `data/golden/ddia_questions.jsonl` and `about_questions.jsonl` unchanged
  since P4_BASE; `git diff --quiet HEAD -- rag` exits 0.

## Mutation proofs (not committed)

- Unknown-key check disabled (`if unknown:` -> `if False:` in `parse_row`):
  `test_a_bad_row_is_rejected[unknown_key]` -> `Failed: DID NOT RAISE <class 'ValueError'>` (1 failed).
- Clarify-category pairing disabled in `validate`:
  `test_a_bad_row_is_rejected[clarify_in_wrong_category]` -> `Failed: DID NOT RAISE <class 'ValueError'>` (1 failed).
- Both restored with `git checkout HEAD -- rag/observe/golden_conversations.py`; `git diff --quiet HEAD -- rag`
  exits 0 afterwards.

Full suite in the worktree: 877 passed, 2 skipped (838 + 39 new).

## Commits

- 0af4b5e test(04-06): load the committed multi-turn set and check its pages
- 2e996b3 test(04-06): pin the loader's rejects, edges and load_golden unchanged

## Deviations

None.
