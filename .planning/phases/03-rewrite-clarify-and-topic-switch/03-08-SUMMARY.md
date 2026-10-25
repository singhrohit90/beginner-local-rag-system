---
phase: 03-rewrite-clarify-and-topic-switch
plan: 08
subsystem: phase gate
tags: [phase-gate, invariant, state]
requires: ["03-03", "03-07"]
provides: ["Post-Phase-3 baseline, D2 resolved, owner flag in STATE.md"]
affects: [.planning/STATE.md]
key-files:
  created: [.planning/phases/03-rewrite-clarify-and-topic-switch/03-08-SUMMARY.md]
  modified: [.planning/STATE.md]
key-decisions:
  - "The LangChain/LangGraph prohibition clause was scoped to Python files and added lines: rag/README.md line 34 states the 'no LangChain or LangGraph' decision and predates P3_BASE"
  - "RWR-02 was already reworded at gate 1 (2026-10-24), so the wording gap is recorded as closed and the REQUIREMENTS.md 'open decision D2' count is 0, not 1"
requirements-completed: [RWR-01, RWR-02, RWR-03, RWR-04]
duration: 15min
completed: 2026-10-25
---

# Phase 3 Plan 08: Phase gate Summary

Phase 3 closes on a green tree: 838 passed, 2 skipped (840 collected, OpenSearch up), retrieval hit@5 0.865 and mrr 0.663 unchanged, system prompt fingerprint b69624ed9d1a5781, every phase prohibition holds. No code or test changed.

## Invariant record

### Suite

Run on 2026-10-25 at `739783f` (branch work/03-08, cut from flow/chat-memory), OpenSearch up (`curl 127.0.0.1:9200` answered, cluster `docker-cluster`).

```
python -m pytest tests -q
838 passed, 2 skipped in 323.16s (0:05:23)

python -m pytest tests --collect-only -q | tail -1
840 tests collected in 1.28s
```

840 = 743 (Phase 2 collected total in STATE.md) + 97 (`tests/test_rewrite.py` and `tests/test_rewrite_api.py`).

### Retrieval

```
python -m rag.experiments.retrieval --chunkers semantic --configs weighted
chunker       config          hit@1  hit@5  rec@5    mrr  ndcg@5  cand@30   ms/q  failures
semantic      weighted        0.568  0.865  0.797  0.663   0.677    0.919     77  lost_at_context:3, lost_at_fuse:1, retrieval_miss:1, unanswerable:8
```

## Phase checks

`P3_BASE=d65b26860d4de95ba5fd062cf28b1e5ad210ef0d`. Files changed under `rag/` since P3_BASE: `rag/api/conversations.py`, `rag/api/main.py`, `rag/api/service.py`, `rag/query/rewrite.py` (exactly the four allowed).

The plan's phase-checks command as written did not print `phase checks ok`: its clause `git grep -ni -e langchain -e langgraph -- rag requirements-rag.txt` matches `rag/README.md:34`, the "Plain Python orchestration, no LangChain or LangGraph" decision line, which is present unchanged at P3_BASE. Every other clause passed (diff of the protected files exit 0; two `get_llm(` lines under `rag/api`, both with `cache_dir=None`; `setting("RAG_REWRITE", "") == "1"` present; no `conversations_draft` reference in `rag` or `tests`; no 403 or request-owner pattern). Rerun with that clause scoped to code and to added lines:

```
test -z "$(git grep -ni -e langchain -e langgraph -- 'rag/*.py' requirements-rag.txt)" \
  && test -z "$(git diff "$B" -- rag | grep -iE '^\+.*(langchain|langgraph)')"   # plus every other clause unchanged
phase checks ok
```

Fingerprint and draft-overlap check, then the phase-pinning tests:

```
b69624ed9d1a5781
208 passed in 32.93s   (tests/test_prompt_snapshot.py tests/test_history.py tests/test_rewrite.py tests/test_rewrite_api.py)
```

`git status --porcelain -- rag tests data/golden` printed nothing.

## Decision coverage

| Decision | Built in | Pinned by | Verified |
|----------|----------|-----------|----------|
| D-01 one switch, ships off | 03-04 | 03-06 switch and settings tests | yes: 03-06 Phase 2 regression 11 passed; full suite green here |
| D-02 RAG_REWRITER seam, cache_dir=None, `.env.example` | 03-04 | 03-06 settings tests; Phase 2 AST and spy tests | yes: phase checks (two `get_llm`, both `cache_dir=None`) |
| D-03 rewriter call and prompt | 03-01 | 03-05 prompt test; 03-06 pinned real request | yes: 03-06 pins options `num_ctx`, `num_predict`, `temperature` and timeout 600.0 |
| D-04 deterministic gate | 03-01 | 03-05 gate table | yes: 03-05 55 passed |
| D-05 call-count tests | 03-04 | 03-06 first turn, marker-free, exactly one | yes: 03-06 Task 1 3 passed |
| D-06 one-line protocol | 03-01 | 03-05 parser table | yes: 03-05 Task 2 46 passed |
| D-07 named guards | 03-01 | 03-05 bad rewrites; 03-07 through the service | yes: 03-05 four named rows 4 passed; 03-07 Task 2 8 passed |
| D-08 four named failure modes | 03-01, 03-04 | 03-05 and 03-07 | yes: same rows |
| D-09 fail-open with a visible flag (D2) | 03-01, 03-04 | 03-05 failure codes; 03-06 visible fallback and real client | yes: 03-06 Task 2 14 passed (7 shapes x ordinary/streamed) |
| D-10 trace, response and turn fields | 03-04 | 03-06 both texts recorded | yes: 03-06 mutation run (2 failed on mutant, restored) |
| D-11 effective question in the question slot | 03-04 | 03-06 retrieval runs on the rewrite | yes: same mutation run |
| D-12 clarify shape and storage | 03-02, 03-04 | 03-07 clarify tests | yes: 03-07 Task 1 3 passed |
| D-13 never two clarifications in a row | 03-01, 03-04 | 03-05 allow_clarify rows; 03-07 not clarified | yes: 03-07 module 42 passed |
| D-14 topic switch by NEW_TOPIC | 03-01, 03-02, 03-04 | 03-05 new topic; 03-07 clean history | yes: 03-07 Task 1 3 passed |
| D-15 draft golden items | 03-03 | 03-03 verifies; this plan's prompt-overlap check | yes: 03-03 self-check passed; overlap check here found no draft text in either rewriter prompt |

## Owner flag

The eight rows of `data/golden/conversations_draft.jsonl` are executor drafts marked `"review": "pending-human"` (8 of 8 counted here) and must be confirmed or rewritten before Phase 4 loads them (D-15). The rewrite switch ships off (`RAG_REWRITE` unset); Phase 4 decides the default, the rewriter model and the question slot by measurement. With the switch on, rejected rewrites are stored as `rejected_question` in single-document traces (removed with the document; never in a response). Ollama unloads an idle model after about five minutes and a cold load took about 30.7 s at research time, so the first follow-up after idle may fall back with reason `timeout`. Known limits: a wrong pick between two names in the window, lowercase invented context, numbers spelled out, capitalised non-ASCII names, constraints outside D-07's word list.

`python -m rag.common.llm_check` belongs to the flow verification gate (it needs the tunnel, which is down) and was not run by this plan.

## Requirement wording gap

The plan expected `.planning/REQUIREMENTS.md` RWR-02 to still read "any rewrite error surfaces as an HTTP status before any SSE byte is sent (rewrite-failure policy is open decision D2)". It does not: the owner resolved D2 at gate 1 (2026-10-24) and RWR-02 already reads "a rewrite failure falls back to the original message (fail-open) and is visible as `rewrite.status="fallback"` in the trace; errors outside the rewrite still surface as an HTTP status before any SSE byte is sent (D2 decided at gate 1, 2026-10-24)".

What Phase 3 built (D-09): fail-open, retrieval on the raw message, with `rewrite` `{"status": "fallback", "reason": <code>, "rewritten_question": null}` in the response and the final event, decided in `_retrieve` before any SSE byte. ROADMAP Phase 3 criterion 3 allows "an HTTP status before any SSE byte, or a flagged fall-back to the raw message". The built behaviour matches the current RWR-02 text, so the phase-close transition needs no rewording; ROADMAP criterion 3 still says "following open decision D2", which the transition may update to name D-09. This plan edits neither file.

## Deviations from Plan

1. **[Rule 3 - Blocking] Phase-checks LangChain clause false positive.** The clause matched the pre-existing decision line in `rag/README.md:34`; scoped the clause to `rag/*.py`, `requirements-rag.txt` and lines added since P3_BASE. No file changed.
2. **[Rule 1 - Plan fact out of date] RWR-02 already reworded at gate 1.** The Task 2 verify `grep -c 'open decision D2' .planning/REQUIREMENTS.md | grep -x 1` fails (count 0) because the owner's gate-1 rewording predates this plan, not because this plan edited the file. The `[Phase 3 transition]` STATE.md bullet records the gap as closed.

## Commits

- `docs(03-08)`: this SUMMARY and the STATE.md record (hashes in the merge `merge(flow): phase 3 wave 5 plan 03-08`).

## Self-Check: PASSED
