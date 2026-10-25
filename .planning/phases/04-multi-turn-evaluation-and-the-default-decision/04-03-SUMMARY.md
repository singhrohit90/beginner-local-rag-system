---
phase: 04-multi-turn-evaluation-and-the-default-decision
plan: 03
status: complete
requirements: [EVAL-02, EVAL-03]
---

# 04-03 Summary: multi-turn experiment, part 1

`rag/experiments/conversation.py`: four arms (`off`, `on`, `oracle`, `concat`) on identical teacher-forced histories,
strict evidence-aware scoring (`strict_trace` + `score_hits`, `ValueError` without evidence terms), the `on` arm
through the shipped `needs_rewrite` / `rewrite_question`, false clarify = 0, fallback retrieves on the raw message,
clarify items scored apart, `CallCounter`, `preflight`, the regression arm (empty window and the non-gating
unrelated-turn variant), the rule guard (`rule_section`, `rule_status`, `scoring_refusal`), `--check-set`,
`--check-rule`, `--regression-only`, and `runs/conversation/<name>/report.json`. No arm ran over
`data/golden/ddia_conversations.jsonl` (the file does not exist yet).

## Verification

Tracer (scratchpad row from q015):

```
t001  pronoun_follow_up           off 1 oracle 1
discriminating 0/1 pronoun+constraint items miss with off
oracle misses 0
```

- `docstring rule ok`
- `meta ok` (tracer report, nine Task 1 keys)
- `smoke ok` (scratchpad `smoke_04_03.py`: rewritten pronoun item hits, clarify asked and named both, no second
  clarify, raising rewriter -> fallback on the raw message, preflight returns `ConnectionRefusedError`). Fail-first:
  against the Task 1 commit it fails with `ImportError: cannot import name 'preflight'`.
- `--check-rule`:
  `rule commit 9baf0f3334f3158aeafd77db5a07bdbbef9cd02c; committed yes; clean yes; unchanged yes; first commit has results no`
  (fail-first: on the Task 2 code `--check-rule` is not a mode and the run dies on the missing golden file).
- `--regression-only` (rewriter `ollama:qwen2.5:7b`, local Ollama up):

```
regression: 37/37 identical, rewriter calls 0
regression off hit@5 0.865 mrr 0.663
regression with one unrelated turn (not gating): gate fired 21, rewritten 16, hit@5 changed 6 of 37
```

- `meta ok` (regression report, eleven keys, `items` 45)
- `guard ok`
- `shell=True|os.system` count 0; `str(err)|{err}` count 0; `rag/query` unchanged since P4_BASE.

Note for the owner: after one unrelated turn the rewriter rewrote 16 of 37 standalone questions and changed hit@5 on
6. That variant is reported, not gating, but it is a sign of over-rewriting.

## Commits

- 82258e0 feat(04-03): add the multi-turn experiment retrieval arms
- d9cec36 feat(04-03): score the rewrite arm, clarify items and preflight
- bd4e769 feat(04-03): add the rule guard and the regression arm

## Deviations

- In default mode without the `on` arm requested, the regression keys hold `{"skipped": "the on arm was not
  requested"}` (no rewriter exists to replay with).
- Full suite: first run had one failure in `tests/test_api.py::test_a_delete_during_a_load_leaves_nothing_in_the_store[one document]`
  (an API timing test this plan does not touch); it passed 3 of 3 alone and the suite was re-run; the saved count is
  the re-run.
