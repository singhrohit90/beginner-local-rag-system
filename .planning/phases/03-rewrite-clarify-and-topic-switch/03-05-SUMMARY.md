---
phase: 03-rewrite-clarify-and-topic-switch
plan: 05
subsystem: query
tags: [rewrite, tests, guards, fail-first]
requires: [rag/query/rewrite.py (plan 03-01), rag/query/history.py (Phase 1)]
provides: [tests/test_rewrite.py]
affects: [plans 03-06, 03-07 (service-level rewrite tests build on these fixtures' shapes)]
key-files:
  created: [tests/test_rewrite.py]
  modified: []
decisions: [none new; tests pin D-03, D-04, D-06 to D-09, D-12 to D-14, A4, A7 as built in 03-01]
metrics:
  tasks: 3
  commits: 3
  tests_added: 55
---

# Phase 3 Plan 05: pure rewrite tests Summary

`tests/test_rewrite.py` pins the gate, the rewriter prompt, the reply parser, the guards (with the four named bad rewrites of RWR-04), the clarify and topic outcomes, the known wrong-pick limit, the injection channel, failure classification, the prompt size cap and totality on odd text. Every model is a `_Spy` or a `FakeLLM`; no service, HTTP client, network or draft golden file.

## Commits

| Task | Commit | Subject |
|------|--------|---------|
| 1 | 575dcfc | test(03-05): pin the rewrite gate and the rewriter prompt |
| 2 | 8d2bce9 | test(03-05): pin the parser, the guards and the four named bad rewrites |
| 3 | 7b7670e | test(03-05): pin failure codes, the size cap and totality |

## Verification

- Task 1 verify: `11 passed`.
- Task 2 verify: `46 passed`; four named rows `-k "bad_rewrite and (invented_details or dropped_constraints or wrong_pronoun or topic_leak)"`: `4 passed, 42 deselected`.
- Task 3 verify: `55 passed`; `--collect-only`: `55 tests collected`; `rag clean` printed.
- `grep -cE 'conversations_draft|urlopen|TestClient' tests/test_rewrite.py`: 0. No line over 120 characters.
- Full suite in the worktree: `796 passed, 2 skipped in 234.02s` (baseline 741 passed, 2 skipped, plus the 55 new cases).

## Fail-first mutation proofs

Each a one-place Edit of `rag/query/rewrite.py`, the named ids run, then `git checkout HEAD -- rag/query/rewrite.py` and `git diff --quiet HEAD -- rag` (exit 0). No commit was made while a mutation was in the tree.

- (a) `if kind == "rewrite":` -> `if False:` (whole dropped_constraint block skipped); `-k "bad_rewrite and dropped"`: `3 failed, 52 deselected`
- (b) `for match in _NAME.finditer(text):` -> `for match in []:` (capitalised-word loop removed); `-k "wrong_pronoun or (only_known and invented)"`: `2 failed, 53 deselected`
- (c) `leaked` returns `False`; `-k "bad_rewrite and topic_leak"`: `1 failed, 54 deselected`
- (d) `except Exception` handler in `rewrite_question` re-raises; `-k reason_code`: `7 failed, 48 deselected`
- (e) `if not window or not words:` -> `if not words:` in `needs_rewrite`; `-k "gate and first_turn"`: `1 failed, 54 deselected`

After the last restore: `git diff --quiet HEAD -- rag && test -z "$(git status --porcelain -- rag)"` printed `rag clean`.

## Known limit (as worded in the test docstring)

`test_a_wrong_pick_between_two_names_in_the_window_is_a_known_limit`: "The user may have meant Raft, not Paxos. Both names are in the shown history, so no deterministic guard can tell a right pick from a wrong one, and the rewrite is accepted. This is a documented known limit (D-07, orchestrator resolution), mitigated by the clarify path and by the trace recording both the raw and the rewritten text, and measured by Phase 4's oracle arm."

## Deviations from Plan

- The module docstring says "no HTTP client" instead of "no TestClient", so the acceptance grep for `TestClient` prints 0 as the plan requires.
- Task 2's appended block was written with the Edit tool after a long shell heredoc failed to parse (CLAUDE.md: long heredocs get truncated); no content change.

No bug found in `rag/query/rewrite.py`; nothing under `rag/` was changed.
