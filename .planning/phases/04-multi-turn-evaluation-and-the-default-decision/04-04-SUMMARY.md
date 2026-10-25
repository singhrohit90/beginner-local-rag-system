---
phase: 04-multi-turn-evaluation-and-the-default-decision
plan: 04
status: complete
requirements: [EVAL-02, EVAL-03]
---

# 04-04 Summary: multi-turn experiment, part 2

`rag/experiments/conversation.py` gains the D-06 statistics as pure functions (`noise_band`, `paired`, `sign_test_p`,
`oracle_gap_closed`, `nearest_rank`, `status_counts`, `gate_quality`, `category_table`, `summarise`), the committed
rule as code (`evaluate_rule`, `decision_line`), `instability` for `--repeats`, the answers arm (`run_answers`,
`answers_summary`, `slot_decision`) scored with `judge_facts` only, `choose_rewriter` (D-10), `render_results`
(counts, rates, reason codes and ids only) and `print_tables`. New flags: `--repeats`, `--answers`, `--llm`,
`--judge`, `--workers`, `--results`, `--compare`. A default run writes `report.json` and `results.md`. No arm ran over
the committed golden set.

## Verification

- `smoke ok` (Task 1: scratchpad `smoke_04_04.py`; results text starts `## Results`, every `RESULT_LABELS` entry starts
  a line, the last line is `Decision: ships off (...; provisional: items pending human review)`, no model text, n = 30
  net 3 fails and net 4 passes). Fail-first on the 04-03 code: `AttributeError: ... no attribute 'summarise'`.
- `rule table ok`
- `smoke ok` (Task 2, `smoke_04_04.py 2`: a second draw that clarifies on the pronoun item is listed as changed; `on`
  and `on_original` share one retrieval and differ only in the question line; every variant carries the history
  block; an abstention is scored False; `slot_decision(None, 10.0) == "unmeasured"`). Fail-first on the Task 1 commit:
  `AttributeError: ... no attribute 'instability'`.
- get_llm / judge grep check: exit 0 (3 `get_llm` calls, all `cache_dir=None`; no `judge_correctness`,
  `judge_faithfulness` or `score_answer`).
- `choice ok`; `--help` lists `--repeats --answers --llm --judge --workers --results --compare`. Fail-first:
  `ImportError: cannot import name 'choose_rewriter'` on the Task 2 commit.
- Extra scratch check of the compare branch: `compare ok` (inside the band the lower p50 wins and the rule is
  evaluated on the chosen run).
- Full suite in the worktree: 838 passed, 2 skipped.

## Commits

- fb37551 feat(04-04): evaluate the shipping rule and render the results
- 3f6ded5 feat(04-04): add repeats and the fact-checklist answers arm
- ed9233d feat(04-04): choose the rewriter by the pre-registered rule

## Deviations

- The Task 2 smoke uses a second draw that returns CLARIFY (a false clarify) for the changed-id check instead of a
  fallback: on the three-page fixture the raw message also hits, so a fallback does not change hit@5.
- The abstention case uses the book's refusal phrase ("I cannot answer this from the provided book.");
  `looks_like_abstention` does not treat "I don't know." as an abstention.
- `--answers` with no `on` arm records `answers_not_run` and skips the generator and judge entirely.
