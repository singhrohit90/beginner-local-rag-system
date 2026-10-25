---
phase: 04-multi-turn-evaluation-and-the-default-decision
plan: 10
status: complete
requirements: [EVAL-01, EVAL-02, EVAL-03]
---

# 04-10 Summary: Phase 4 gate

Run on 2026-10-25 (UTC) at 49dc92e in worktree `work/04-10`, OpenSearch up (HTTP 200 on the local port).
Gate outputs saved under `.planning/runs/20261021-1840-chat-memory/phase-04-gate/`.

## Invariant record

Suite:

- `python -m pytest tests -q` -> `917 passed, 2 skipped in 260.90s (0:04:20)`
- `python -m pytest tests --collect-only -q | tail -1` -> `919 tests collected in 1.19s`
  (Phase 3 total 840 + 39 `tests/test_golden_conversations.py` cases + 40 `tests/test_conversation_experiment.py` cases)

Retrieval (`python -m rag.experiments.retrieval --chunkers semantic --configs weighted`):

```
semantic      weighted        0.568  0.865  0.797  0.663   0.677    0.919     43  lost_at_context:3, lost_at_fuse:1, retrieval_miss:1, unanswerable:8
```

Regression (`python -m rag.experiments.conversation --regression-only --name p4-gate`):

```
regression: 37/37 identical, rewriter calls 0
regression off hit@5 0.865 mrr 0.663
regression with one unrelated turn (not gating): gate fired 21, rewritten 16, hit@5 changed 6 of 37
```

## Phase checks

```
rule commit 9baf0f3334f3158aeafd77db5a07bdbbef9cd02c; committed yes; clean yes; unchanged yes; first commit has results no
rule-first
P4_BASE=3744d3c325c9100ba59f928f15471c1c07417b1d
rag/experiments/conversation.py
rag/observe/golden_conversations.py
phase checks ok
b69624ed9d1a5781
```

Model checks:

- `python -m rag.common.llm_check ollama:qwen2.5:7b` -> `OK    ollama:qwen2.5:7b  2.7s  tokens in/out 27/14  finish=stop`
- `python -m rag.common.llm_check` -> `FAIL  cannot reach the model server ... ([WinError 10061] ... actively refused it)`
  (tunnel down; recorded, not a failure)

## Decision coverage

| Decision | Built in | Pinned by | Verified |
|----------|----------|-----------|----------|
| D-01 golden schema | 04-01, 04-05 | 04-06 reject table and committed-set tests | suite green |
| D-02 size and discrimination | 04-05 | `--check-set` lines in 04-05-SUMMARY.md and MULTITURN_REVIEW.md | recorded in 04-05 |
| D-03 executor drafts pending review | 04-05 | 04-06 committed-set test; rule (f); owner flag | (f) failed in Results; owner flag in STATE.md |
| D-04 own loader, load_golden unchanged | 04-01 | 04-06 `test_load_golden_is_untouched`; P4_BASE diff | phase checks ok |
| D-05 one command, four arms, teacher-forced history | 04-03 | 04-07 own-query and history tests | suite green; p4-qwen ran off/on/oracle/concat |
| D-06 outputs and answer scoring | 04-03, 04-04 | 04-07 smoke, tables, fallback, clarify, answers tests | suite green; answers unmeasured live (tunnel) |
| D-07 rule committed first | 04-02, 04-03, 04-04 | 04-07 rule table and guard tests; rule-first check | rule-first printed |
| D-08 committed results | 04-04, 04-08 | 04-09 `test_the_results_file_records_every_decision` | passes |
| D-09 regression arm | 04-03 | 04-07 regression tests; `--regression-only` | 37/37 identical, 0 calls |
| D-10 rewriter model by measurement | 04-04, 04-08, 04-09 | 04-07 choice table; `test_the_rewriter_default_matches_the_recorded_choice` | passes (qwen, not compared) |
| D-11 question slot by measurement | 04-04, 04-08, 04-09 | 04-07 answers test; 04-09 slot branch | not triggered (unmeasured) |
| D-12 judge and correlation flag | 04-04 | 04-07 fact-checklist test; Results line | "not applicable (answers not run)" |
| D-13 default follows the rule | 04-09 | `test_the_default_matches_the_recorded_decision` | passes; switch off |
| D-14 live models optional, blocker recorded | 04-03, 04-04, 04-08 | 04-07 unreachable-model test; STATE.md blocker | `[Phase 4]: arms not run` bullet present |

## Edge coverage

| Probe item | Resolution | Where |
|------------|------------|-------|
| EVAL-01 adjacency, empty, ordering | resolved (explicit) as truths | 04-01; tests in 04-06 |
| EVAL-02 unclassified | unresolved by the probe; flagged assumption | 04-03; behaviour covered by 04-07 tests |
| EVAL-03 adjacency, empty, ordering | resolved (explicit) as truths | 04-04; tests in 04-07 |

Seven probe items: six authored as truths, one flagged; none dropped.

## Owner flag

Every row of `data/golden/ddia_conversations.jsonl` (34 items) is an executor draft pending human review
(`data/golden/MULTITURN_REVIEW.md`). The decision is the committed line `Decision: ships off (failed: a, c, f;
provisional: items pending human review)` and is provisional. After review the owner reruns
`python -m rag.experiments.conversation --check-set`, the scored run (`--repeats 3 --answers`, plus the gpt-oss
comparison when the tunnel is up) and `--results`, appends the new Results, and
`test_the_default_matches_the_recorded_decision` then forces the default to follow. Arms not run in 04-08: answers
(generator unreachable) and the gpt-oss rewriter comparison (tunnel down). Rewriter and judge are both qwen when the
answers arm runs with defaults (D-12).

## STATE.md commit

7bcaeb4 docs(04-10): record the Phase 4 baseline, decision and owner flag
