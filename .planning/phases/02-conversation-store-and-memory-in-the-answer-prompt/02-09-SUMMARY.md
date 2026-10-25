---
phase: 02-conversation-store-and-memory-in-the-answer-prompt
plan: 09
subsystem: phase-gate
tags: [conversations, chat-memory, phase-gate, invariants, owner-flag]
requires: ["02-05", "02-06", "02-08"]
provides:
  - "Post-Phase-2 baseline in .planning/STATE.md: 741 passed, 2 skipped (743 collected); retrieval hit@5 0.865, mrr 0.663"
  - "D-11 owner flag in this SUMMARY and in STATE.md"
affects: ["03"]
key-files:
  modified:
    - .planning/STATE.md
requirements-completed: [CONV-01, CONV-02, CONV-03, CONV-04, PRMT-01, PRMT-03, PRMT-04]
---

# Phase 2 Plan 09: Phase 2 gate

Measured the finished Phase 2 tree end to end and recorded the results. No file under `rag/` or `tests/` changed.

For the phase verifier: copy the "Invariant record" and "Owner flag" sections below verbatim into `02-VERIFICATION.md`.

## Invariant record

Tree: `ebcf8f4` (flow/chat-memory after wave 8; measured in worktree `work/02-09` before the STATE.md commit), 2026-10-25.

### OpenSearch

`python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9200', timeout=3); print('opensearch up')"` printed `opensearch up`. OpenSearch was **up**.

### Pytest

- `python -m pytest tests -q`: `741 passed, 2 skipped in 251.45s (0:04:11)`
- `python -m pytest tests --collect-only -q`: `743 tests collected in 1.17s`
- Phase 1 baseline (STATE.md): 702 passed, 2 skipped (704 collected; OpenSearch up). 704 + 39 = 743, as the plan required.

### Retrieval

`python -m rag.experiments.retrieval --chunkers semantic --configs weighted` (2026-10-25, commit `ebcf8f4`):

```
chunker       config          hit@1  hit@5  rec@5    mrr  ndcg@5  cand@30   ms/q  failures
semantic      weighted        0.568  0.865  0.797  0.663   0.677    0.919     75  lost_at_context:3, lost_at_fuse:1, retrieval_miss:1, unanswerable:8
```

hit@5 0.865 and mrr 0.663: unchanged.

## Phase checks

Prohibition check (P2_BASE=346cd43e71f9943432eafe38a03a690a658b2dc2):

```
B="$(grep -oE 'P2_BASE=[0-9a-f]{40}' .planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-01-SUMMARY.md | head -1 | cut -d= -f2)" && test -n "$B" && N="$(git diff --name-only "$B" -- rag)" && test -z "$(printf '%s\n' "$N" | grep -vxE 'rag/(query/history|api/(conversations|service|main))\.py')" && git diff --quiet "$B" -- requirements-rag.txt rag/api/static/index.html tests/snapshots tests/test_prompt_snapshot.py tests/test_history.py && test -z "$(grep -nE 'mkdir\([^)]*parents' rag/api/conversations.py)" && test "$(grep -ho 'get_llm(' rag/api/main.py rag/api/service.py rag/api/conversations.py | wc -l)" = 1 && grep -q 'get_llm(setting("RAG_LLM", "vllm:/models/gpt-oss-20b"), cache_dir=None)' rag/api/main.py && test -z "$(grep -nE 'HTTPException\(403|owner *= *request|request\.owner' rag/api/main.py)" && test "$(sed -n '/def ask_about/,/def ask(/p' rag/api/service.py | grep -c conversation)" = 0 && echo "phase checks ok"
```

Output: files changed under `rag/` since P2_BASE are exactly `rag/api/conversations.py`, `rag/api/main.py`, `rag/api/service.py`, `rag/query/history.py`; then `phase checks ok`.

Prompt fingerprint and Phase 1 snapshot:

```
python -c "import hashlib; from rag.query.prompt import SYSTEM_PROMPT as A, DOCUMENT_SYSTEM_PROMPT as B; from rag.security.defenses import SPOTLIGHT_ADDENDUM as C, NAIVE_SYSTEM_PROMPT as D; print(hashlib.sha256((A+B+C+D).encode('utf-8')).hexdigest()[:16])" | grep -x b69624ed9d1a5781 && python -m pytest tests/test_prompt_snapshot.py tests/test_history.py tests/test_conversations.py -q 2>&1 | tail -1 | grep -E '^[0-9]+ passed' | grep -vE 'failed|error'
```

Output: `b69624ed9d1a5781`, then `137 passed in 14.54s`.

`git diff --quiet "$P2_BASE" -- CLAUDE.md .claude/CLAUDE.md` exited 0 (neither file changed in Phase 2).

## Decision coverage

| Decision | Built in | Proven by |
|----------|----------|-----------|
| D-01 layout (one-way; checkpoint auto_select owner-folder) | 02-03, 02-04 | 02-05 cascade and duplicate-id tests; 02-07 cascade test |
| D-02 cascade, D-03 no resurrection | 02-03, 02-04 | 02-05 cascade; 02-07 purge; 02-08 delete during a turn, delete serialised with a write |
| D-04 ids (refined: max_length=512), D-05 one 404, D-06 new id when absent | 02-03, 02-04 | 02-05 same 404 and 512/513; 02-06 four routes and separate conversations |
| D-07 file format, D-09 turn fields, D-10 success-only persistence, D-11 kept without traces | 02-03, 02-04 | 02-07 turn record and traces off; 02-08 failed turn and closed stream |
| D-08 lease | 02-03, 02-04 | 02-08 busy, closed, failed and unstarted streams |
| D-12 history block, D-13 trace record, D-14 StreamGuard | 02-04 | 02-05 window in the trace; 02-07 prompts, defang, role lines; 02-06 stored streamed answer |
| D-15 numbers, D-16 caps and budget | 02-01, 02-02, 02-03, 02-04 | 02-08 caps, oversize follow-up, worst case |
| D-17 no disk cache | unchanged code, 02-04 grep | 02-07 spy and AST guard |
| D-18 module split | 02-03, 02-04 | the phase prohibition checks above |

## Owner flag

Conversation files are kept when `keep_traces` is off, because history is functional state (D-11). They live until a document in their scope is deleted. Until Phase 5 the page sends no `conversation_id` (D-06 creates a new conversation for every question without one), so every question asked on the page writes an orphan one-turn conversation file that is never continued, and the files grow by one per page question. That includes all-documents questions, whose answers no trace keeps today, so Phase 2 retains answer text the server did not keep before, in `data/uploads/_conversations/{owner_key}/`, until a document one of its turns resolved is deleted. There is no retention period yet; that is a Phase 5 docs and backlog item (CONTEXT.md Deferred). The prompt-budget refusal reuses the "this conversation is full; start a new conversation" 409 (D-16) even when the cause is one long question; clearer wording is left for Phase 5 to decide.

`python -m rag.common.llm_check` belongs to the flow verification gate (it needs the tunnel) and was not run by this plan; the tunnel forward was resetting (WinError 10054) on 2026-10-25, and `max_model_len` stays parked for the merge gate with `MODEL_CONTEXT_TOKENS` at the 8192 floor.

## Commits

| Task | Commit | Subject |
|------|--------|---------|
| 2 | df3c9b3 | docs(02-09): record the phase 2 invariants and owner flag |

Task 1 only measures; it has no commit of its own.

## Deviations from Plan

None. Note: `tests/test_api.py::test_a_delete_during_a_load_leaves_nothing_in_the_store[one document]` is a known flaky test (failed once under load in an earlier wave, passed on reruns); it passed in this run.

## Self-Check: PASSED
