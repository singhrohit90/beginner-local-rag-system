---
phase: 01-safety-net-and-prompt-seam
plan: 01
subsystem: tests
tags: [snapshot, prompt-bytes, retrieval-invariant, safety-net]
requires: []
provides:
  - "tests/test_prompt_snapshot.py: 24 single-turn prompt cases and 45 golden user-prompt digests pinned on unedited code"
  - "tests/snapshots/prompts/: 24 case fixtures and golden_user_prompt_digests.json"
  - "Retrieval invariant run 1 of 2 on the unedited tree"
affects: [01-03, 01-04, 01-07]
tech-stack:
  added: []
  patterns: ["committed byte snapshots with no update switch; fixtures written as LF bytes, read with universal newlines"]
key-files:
  created: [tests/test_prompt_snapshot.py, tests/snapshots/prompts/standard__book__mix.txt, tests/snapshots/prompts/golden_user_prompt_digests.json]
  modified: []
key-decisions:
  - "Checkpoint Task 1: snapshot-first (auto-selected, D-04)"
requirements-completed: [PRMT-02]
completed: 2026-10-25
status: complete
actuals:
  tasks: 3
  commits: 1
plan_head_before: 939cffe
plan_head_after: 4b73d94
---

# Phase 1 Plan 01: Single-turn prompt snapshot Summary

The exact system and user prompt bytes for 24 single-turn cases, plus SHA-256 digests of the 45 golden user prompts, are committed from unedited prompt code. A one-character change makes the test fail. The first retrieval-invariant run reproduces hit@5 0.865 and mrr 0.663.

## Checkpoint

- Task 1 (checkpoint:decision): **snapshot-first** (auto-selected under the unattended run policy, per D-04).

## Commits

| Task | Name | Commit |
|------|------|--------|
| 2 | test(01-01): pin single-turn prompt bytes before the prompt seam | 4b73d94 |
| 3 | no commit (output recorded here) | - |

Snapshot SHA: **4b73d94**. It holds the test plus the 25 fixture files and nothing else (26 files). The verify gate passed.

## Verification

- `python -m pytest tests/test_prompt_snapshot.py -q`: `26 passed in 0.22s`, then `26 passed in 0.24s` (two runs in a row).
- Snapshot-commit gate (found by subject, 26 files, test plus fixtures only): passed.
- Seam-files gate (`git log 853f021..HEAD` and `git diff HEAD` on the four seam files are empty, no `.gitattributes`): passed.
- `grep -nE 'write_(text|bytes)|open\(' tests/test_prompt_snapshot.py`: no match. The test never writes a file.
- Digest manifest key count: 45.

### Mutation check

`sed` changed `Question: How does a follower` to `Question: Hou does a follower` in `standard__book__mix.txt`, and `grep -c` printed `1`. The result:

```
FAILED tests/test_prompt_snapshot.py::test_prompt_matches_committed_snapshot[standard__book__mix]
1 failed, 25 passed in 0.22s
```

After `git checkout --` restored the file, the run printed `26 passed in 0.09s`. `git status --short -- tests/test_prompt_snapshot.py tests/snapshots` is empty.

## Retrieval invariant, run 1 of 2 (unedited tree, D-15)

Date 2026-10-25, HEAD `4b73d94`. The seam files are unchanged since 853f021. Command: `python -m rag.experiments.retrieval --chunkers semantic --configs weighted`.

```
chunker       config          hit@1  hit@5  rec@5    mrr  ndcg@5  cand@30   ms/q  failures
semantic      weighted        0.568  0.865  0.797  0.663   0.677    0.919     59  lost_at_context:3, lost_at_fuse:1, retrieval_miss:1, unanswerable:8
```

Baseline for the files plan 01-03 affects: `python -m pytest tests/test_generation.py tests/test_security.py tests/test_stream_api.py -q` printed `64 passed in 11.60s`.

## Deviations

- Execution was split. The first executor committed 4b73d94 and was then cut off by a network error (ENOTFOUND) before it wrote the SUMMARY. The orchestrator finished the plan in the same worktree: the remaining verify gates, the mutation check, Task 3, and this SUMMARY. The mutation check was re-run here; whether the first executor also ran it is unknown, but the working tree was clean.
- The worktree's `data/processed` is a directory junction to the main checkout's gitignored data. Task 3 needs that data, and it is not tracked. It is not staged.

## Self-Check: PASSED
