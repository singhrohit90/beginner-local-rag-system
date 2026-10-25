---
phase: 02-conversation-store-and-memory-in-the-answer-prompt
plan: 06
subsystem: tests
tags: [conversations, chat-memory, streaming, tests, fail-first]
requires: ["02-04", "02-05"]
provides:
  - "Streaming-route tests for the conversation id round trip, separate conversations, refusals before any SSE byte, and the stored streamed answer"
affects: ["02-07", "02-08", "02-09"]
key-files:
  modified:
    - tests/test_stream_api.py
requirements-completed: [CONV-01, CONV-02, PRMT-03, PRMT-04]
---

# Phase 2 Plan 06: Streaming conversation tests in tests/test_stream_api.py

Appended under `# ---- conversations: the id on every route (phase 2) ----`: `ROUTES`, helper `answer_of`
(plus a small private `_route_url` mapping route names to URLs), and four tests collecting seven cases:

- `test_all_four_ask_routes_return_a_conversation_id_and_a_follow_up_uses_it` (4 cases, one per route)
- `test_questions_without_an_id_start_separate_conversations`
- `test_conversation_errors_arrive_before_any_model_call_or_sse_byte`
- `test_a_hostile_streamed_answer_is_stored_as_the_withheld_notice`

Imports added: `re`, `pytest`, `HISTORY_HEADER`. No existing test changed: `git diff 346cd43 -- tests/test_stream_api.py`
has no removed lines, so `test_the_streamed_response_equals_the_ordinary_one` is untouched. Collected tests in the file:
22 at P2_BASE, 29 now.

## Commits

| Task | Commit | Subject |
|------|--------|---------|
| 1 | 6d84fc6 | test(02-06): pin the conversation id on all four ask routes |
| 2 | 3b33e79 | test(02-06): pin conversation errors before any stream byte and the stored streamed answer |

## Fail-first proofs

P2_BASE=346cd43e71f9943432eafe38a03a690a658b2dc2 (`rag/api/service.py` and `rag/api/main.py` checked out at it,
restored with `git checkout HEAD -- ...`, `git diff --quiet HEAD -- rag` confirmed before each commit).

- Task 1, `-k "conversation_id_and_a_follow_up or separate_conversations"` at P2_BASE: `5 failed, 22 deselected in 3.73s`
- Task 2, `-k "before_any_model_call_or_sse_byte or stored_as_the_withheld_notice"` at P2_BASE: `2 failed, 27 deselected in 2.45s`
- Task 2 mutation, `NoSuchConversation` clause removed from `guarded()` in `rag/api/main.py`,
  `-k before_any_model_call_or_sse_byte`: `1 failed, 28 deselected in 1.73s` (`assert 502 == 404`)

## Verification

- `python -m pytest tests/test_stream_api.py tests/test_stream_guard.py -q`: `299 passed in 20.02s`
- Full suite: `python -m pytest tests -q`: `715 passed, 2 skipped in 191.73s` (708 + 7 new items)

## Deviations

- Added a private `_route_url` helper so the parametrized test maps a route name to its URL in one place.
- No fixed sleeps; all tests are synchronous.

## Self-Check: PASSED
