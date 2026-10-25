---
phase: 04-multi-turn-evaluation-and-the-default-decision
plan: 07
status: complete
requirements: [EVAL-02, EVAL-03]
---

# 04-07 Summary: offline tests of the multi-turn experiment

New file `tests/test_conversation_experiment.py` (37 tests, offline: `HashingEmbedder`, a three-page fixture,
`FakeLLM` rewriters, generators and judges, `tmp_path` for every file; no network, no sleep, no `data/processed`).

## Verification

- Task 1: `-k smoke_run` -> `1 passed`. Baseline after 04-04: the file did not exist.
- Task 2: the nine-name `-k` selection -> `9 passed`; `git status --porcelain -- rag runs data` empty.
- Task 3: module -> `37 passed`; `--collect-only -k rule_table` collects 14 cases; `git diff --quiet HEAD -- rag docs`
  exits 0; no email-like string in the file.

## Mutation proofs (not committed)

- `"passed": gain > band` -> `gain >= band` in `evaluate_rule`:
  `test_the_rule_table[n30_net3_fails_a]` fails with `assert rule["ship_on"] is ship_on` / `E assert True is False`.
- Oracle arm query changed from `item.standalone` to `item.message` in `run_arms`:
  `test_each_arm_retrieves_on_its_own_query` fails with
  `AssertionError: assert {'concat': 'W...that needed?'} == {'concat': 'W...e tree page?'}` (differing items).
- Both restored with `git checkout HEAD -- rag/experiments/conversation.py`; `git diff --quiet HEAD -- rag docs`
  exits 0 afterwards.

Full suite in the worktree: see `.planning/runs/20261021-1840-chat-memory/wave-p4-04-07-1.txt`.

## Commits

- 2ec28cc test(04-07): smoke-run the multi-turn experiment offline
- ce3b019 test(04-07): pin the arms, history, tables, fallback, clarify and answers
- 48669e8 test(04-07): pin the shipping rule, its guard and the regression arm

## Deviations

- The fixture's `a1` message is "Which one is it?" and `s1` uses evidence term "stream processors", as planned; the
  history test asserts four distinct answer prompts for `p1` (off, oracle, on, on_original) and, for a topic-switch
  item answered `NEW_TOPIC`, that off/oracle keep the history header while the on variants drop it (`on_original` is
  reused because slot, retrieval and empty history are identical).
- `test_the_rewriter_choice_table` adds an `inside_band_first_faster` case to the plan's list (7 cases).
