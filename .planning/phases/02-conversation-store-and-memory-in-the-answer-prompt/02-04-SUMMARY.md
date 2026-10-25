---
phase: 02-conversation-store-and-memory-in-the-answer-prompt
plan: 04
subsystem: api
tags: [conversations, chat-memory, fastapi, sse]
requires: ["02-03"]
provides:
  - "conversation_id on the four /v1/ask* routes; conversation_id and turn in the body and the final SSE event"
  - "DocumentService conversations store, _alive, _remember, delete cascade, prompt-budget refusal"
affects: ["02-05", "02-06", "02-07", "02-08", "02-09"]
key-files:
  modified:
    - rag/api/service.py
    - rag/api/main.py
requirements-completed: [CONV-01, CONV-02, CONV-03, CONV-04, PRMT-01, PRMT-03, PRMT-04]
---

# Phase 2 Plan 04: Wire conversations into the ask routes

Conversations are wired into the request path: every conversation check runs in `DocumentService._retrieve`
before any model call, the history window reaches the answer prompt through the Phase 1 seam, the turn is
stored on success only, and a document delete removes every conversation it touched.

## Commits

| Task | Commit | Subject |
|------|--------|---------|
| 1 | 9b341b0 | feat(02-04): answer a follow-up from a stored conversation on the document route |
| 2 | 1e24514 | feat(02-04): keep conversations on every ask route and free them on every exit |
| 3 | a639ec9 | feat(02-04): remove conversations with their documents and refuse oversize follow-ups |

## Verification

Each one-line check failed before its task (KeyError on conversation_id; AssertionError for cascade and caps)
and passed after:

- Task 1: `tracer ok`; `tests/test_api.py tests/test_stream_api.py tests/test_prompt_snapshot.py`: 173 passed
- Task 2: `four routes ok`; `leases ok`; `tests/test_api.py tests/test_stream_api.py tests/test_stream_guard.py`: 365 passed
- Task 3: `cascade ok`; `caps ok`; api, stream, snapshot, history and stream-guard suites: 476 passed;
  only the four Phase 2 modules differ from P2_BASE under `rag/`; prompt fingerprint `b69624ed9d1a5781`
- Full suite: `python -m pytest tests -q`: 702 passed, 2 skipped
- `grep -c 'conversation_id=request.conversation_id' rag/api/main.py`: 4
- `grep -n 'get_llm(' rag/api/*.py`: one line, the existing `cache_dir=None` call in `build_default_service`
- No `HTTPException(403`, `owner = request` or `request.owner` in `rag/api/main.py`

## Decisions as built

- **D-04 refined:** `AskRequest.conversation_id: Optional[str] = Field(None, max_length=512)`, inherited by
  `AskAcrossRequest`; any malformed id up to 512 characters reaches the store and gets 404
  `"no such conversation"`; longer is a 422.
- **Open Question 7:** the prompt-budget check (`build_prompts` with the block, then `fits_context`) runs only
  when the history block is non-empty; the turn and word caps (`check_room`) run on every turn of an existing
  conversation. Both refusals are 409 `"this conversation is full; start a new conversation"`.
- **Open Question 8:** duplicate `doc_ids` are folded by `scope_of` (plan 02-03); relied on here.
- **D-11:** conversation files are written whether or not `keep_traces` is on (history is functional state).
  The owner should be told this in the phase summary (plan 02-09).
- `conversation_id` and `turn` sit right after `query_id` in the response.

## Deviations

- Acceptance grep `grep -nE 'if (not )?conversation_id\b' rag/api/service.py rag/api/conversations.py` prints
  `rag/api/conversations.py:192: if conversation_id is None:` (plan 02-03 code). That is the intended `is None`
  test, not a truthiness test; `rag/api/service.py` has no match. Not changed.
- Acceptance `awk '/def ask_documents_stream/,0' ... | grep -nE '_remember\(|"event": "final"'` lists the
  pre-existing docstring line `{"event": "final", ...}` first; in the code `_remember(` (line 29 of the range)
  comes before the `yield {"event": "final", ...}` (line 30). Ordering intent met.
- `test_the_streamed_response_equals_the_ordinary_one` passes unchanged, as the plan predicted.

## Self-Check: PASSED
