---
phase: 01-safety-net-and-prompt-seam
plan: 07
subsystem: planning
tags: [invariants, retrieval, pytest-baseline, phase-checks]
requires: ["01-03", "01-04", "01-05", "01-06"]
provides:
  - "Invariant record: retrieval run 2 of 2, full-suite result, collect-only counts, phase checks"
  - ".planning/STATE.md: post-Phase-1 pytest baseline line"
affects: [phase-2-memory-in-prompt]
tech-stack:
  added: []
  patterns: []
key-files:
  created: [.planning/phases/01-safety-net-and-prompt-seam/01-07-SUMMARY.md]
  modified: [.planning/STATE.md]
key-decisions:
  - "OpenSearch was up, yet the run still skipped 2 tests; the baseline records 702 passed, 2 skipped as printed"
requirements-completed: [PRMT-02]
duration: 10min
completed: 2026-10-25
status: complete
actuals:
  tasks: 2
  commits: 1
plan_head_before: c82b0a3
plan_head_after: 37cc325
---

# Phase 1 Plan 07: Invariant record Summary

Both invariants were re-run on the edited tree and recorded. Retrieval is unchanged, the full suite passes, all 593 pre-phase tests still collect, and STATE.md carries the new baseline for Phase 2.

## Commits

- `37cc325` docs(01-07): record the phase 1 invariants for later phases

## Invariant record

Phase verifier: copy this "Invariant record" section verbatim into `01-VERIFICATION.md` (D-14).

### Retrieval invariant (D-15)

Command: `python -m rag.experiments.retrieval --chunkers semantic --configs weighted`. This command never builds a prompt or calls an LLM, so it proves retrieval (and that the edited `rag.query.pipeline` imports) only; the prompt proof is the snapshot test (RESEARCH Pitfall 7).

Run 1 of 2 (before the seam), 2026-10-25, HEAD `4b73d94`:

```
chunker       config          hit@1  hit@5  rec@5    mrr  ndcg@5  cand@30   ms/q  failures
semantic      weighted        0.568  0.865  0.797  0.663   0.677    0.919     59  lost_at_context:3, lost_at_fuse:1, retrieval_miss:1, unanswerable:8
```

Run 2 of 2 (after the seam), 2026-10-25, HEAD `c82b0a3`:

```
chunker       config          hit@1  hit@5  rec@5    mrr  ndcg@5  cand@30   ms/q  failures
semantic      weighted        0.568  0.865  0.797  0.663   0.677    0.919     76  lost_at_context:3, lost_at_fuse:1, retrieval_miss:1, unanswerable:8
```

Every column except ms/q (timing) is identical.

### Pytest (D-14)

OpenSearch: up (`urllib.request.urlopen('http://127.0.0.1:9200', timeout=3)` printed `opensearch up`), 2026-10-25, HEAD `c82b0a3`.

- Before Phase 1: `591 passed, 2 skipped` (593 collected)
- After Phase 1: `python -m pytest tests -q` -> `702 passed, 2 skipped in 207.83s (0:03:27)`
- `python -m pytest tests --collect-only -q --ignore=tests/test_prompt_snapshot.py --ignore=tests/test_history.py` -> `593 tests collected in 1.05s`
- `python -m pytest tests --collect-only -q` -> `704 tests collected in 1.12s`

### Phase checks

```
$ python -c "...sha256(SYSTEM_PROMPT+DOCUMENT_SYSTEM_PROMPT+SPOTLIGHT_ADDENDUM+NAIVE_SYSTEM_PROMPT)[:16]"
b69624ed9d1a5781

$ git diff --name-only 853f021 -- rag
rag/query/generate.py
rag/query/history.py
rag/query/pipeline.py
rag/query/prompt.py
rag/security/defenses.py

$ test ! -e .gitattributes && echo "no .gitattributes"
no .gitattributes

$ git log --format='%h %s' -1 -- tests/snapshots
4b73d94 test(01-01): pin single-turn prompt bytes before the prompt seam

$ git diff --quiet 853f021 -- CLAUDE.md .claude/CLAUDE.md; echo $?
0

$ grep -cE 'pytest baseline after Phase 1 is [0-9]+ passed' .planning/STATE.md
1
```

Nothing under `rag/api` or `rag/common` changed since `853f021`; the fingerprint matches; the fixtures were last changed by the 01-01 commit.

## STATE.md

The standing-constraint bullet now reads: "pytest baseline after Phase 1 is 702 passed, 2 skipped (704 collected; OpenSearch up on 2026-10-25); before Phase 1 it was 591 passed, 2 skipped (593 collected); retrieval invariant hit@5 0.865, mrr 0.663, unchanged after the Phase 1 seam."

## Deviations

- The run was executed in worktree `.claude/worktrees/01-07` with a directory junction from its `data/processed` to the main checkout's `data/processed` (gitignored index needed by the retrieval run); the junction was removed afterwards.
- The plan expected the skip count to differ with OpenSearch up; it printed 2 skipped, same as the down-state expectation. Recorded as printed; the skip reasons were not inspected.

## For Phase 2

- Compare against 702 passed, 2 skipped (704 collected) with OpenSearch up.
- `MODEL_CONTEXT_TOKENS` still uses the 8192 floor; re-read max_model_len (docs/models.md, Context window) before pinning D3.
