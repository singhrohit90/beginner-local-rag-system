---
phase: 02-conversation-store-and-memory-in-the-answer-prompt
plan: 08
subsystem: tests
tags: [conversations, chat-memory, delete, lease, caps, budget, tests, fail-first]
requires: ["02-04", "02-07"]
provides:
  - "tests/test_conversations.py: GatedLLM; delete-during-turn, delete/write serialisation, busy 409, lease release on close, failure and drop, turn and word caps, follow-up budget refusal, worst-case budget"
affects: ["02-09"]
key-files:
  modified:
    - tests/test_conversations.py
requirements-completed: [CONV-01, CONV-04, PRMT-04]
---

# Phase 2 Plan 08: Lifetime, concurrency, cap and budget tests in tests/test_conversations.py

Added `GatedLLM(FakeLLM)` (blocks inside `generate` and `generate_stream` until released; 30-second ceiling)
and ten test functions collecting fourteen cases:

- `test_a_delete_during_a_turn_leaves_no_conversation_file` (one document / all documents x ordinary / streamed)
- `test_delete_is_serialised_with_a_conversation_write`
- `test_a_second_request_on_a_busy_conversation_gets_409` (ordinary, streamed)
- `test_closing_the_stream_frees_the_conversation_and_stores_nothing`
- `test_a_failed_turn_is_not_stored_and_frees_the_conversation`
- `test_an_unstarted_stream_frees_the_conversation_when_dropped`
- `test_a_full_conversation_is_refused_before_any_model_call_or_sse_byte`
- `test_the_stored_word_cap_refuses_the_next_turn`
- `test_an_oversized_follow_up_is_refused_but_a_first_turn_is_not`
- `test_worst_case_prompt_plus_3600_fits_the_recorded_context_window`

No `rag/` file changed.

## Commits

| Task | Commit | Subject |
|------|--------|---------|
| 1 | 9bbb8e2 | test(02-08): pin that a delete during a turn leaves no conversation behind |
| 2 | b3adf4c | test(02-08): pin the conversation lease on every path and the delete lock |
| 3 | 3e718b7 | test(02-08): pin the conversation caps and the prompt budget |
| style | 1e0f58a | test(02-08): keep the delete-race test lines within 120 characters |

## Fail-first proofs

P2_BASE=346cd43e71f9943432eafe38a03a690a658b2dc2. Each run restored with `git checkout HEAD -- <file>` and
`git diff --quiet HEAD -- rag` confirmed before each commit.

1. service.py and main.py at P2_BASE, `-k delete_during_a_turn`: `4 failed, 12 deselected in 2.68s`
2. Mutation: liveness check in `append_turn` always passes, `-k delete_during_a_turn`: `2 failed, 2 passed, 12 deselected in 3.13s` (the "all documents" cases)
3. Mutation: liveness always passes and the folder is created with `parents=True`, `-k delete_during_a_turn`: `4 failed, 12 deselected in 3.17s`
4. service.py and main.py at P2_BASE, `-k "serialised or busy_conversation or frees_the_conversation or unstarted_stream"`: `6 failed, 16 deselected in 3.95s`
5. Mutation: `with self.conversations.lock:` removed from `DocumentService.delete` (two lines dedented), `-k serialised`: `1 failed, 21 deselected in 2.34s`
6. Mutation: `weakref.finalize(generator, lease.release)` removed, `-k unstarted_stream`: `1 failed, 21 deselected in 1.82s`
7. service.py and main.py at P2_BASE, `-k "is_refused_before_any_model_call or stored_word_cap or oversized_follow_up"`: `3 failed, 23 deselected in 2.77s`
8. Mutation: `ANSWER_TOKENS = 6000` in `rag/query/history.py`, `-k worst_case`: `1 failed, 25 deselected in 1.14s`

## Worst-case estimates (prompt estimate + 3600 reserve, MODEL_CONTEXT_TOKENS = 8192)

- Seven maximal turns (window of six), five 300-word passages, 1999-character question:
  standard `7220`, spotlight `7415` tokens; both fit 8192.
- Pathological 1000-word spotlight question with the same history: `8315` tokens; does not fit at the 8192 floor.

## Verification

- `python -m pytest tests/test_conversations.py -q`: `26 passed in 15.48s`
- `grep -nE 'time\.sleep\(' tests/test_conversations.py`: nothing
- Full suite in the worktree: `741 passed, 2 skipped in 208.55s` (727 + 14 new). A first full run had
  `1 failed, 740 passed, 2 skipped`: `tests/test_api.py::test_a_delete_during_a_load_leaves_nothing_in_the_store[one document]`
  (not touched by this plan); it passed five isolated reruns and the second full run. Flaky under load, not investigated.

## Deviations

- `test_delete_is_serialised_with_a_conversation_write` also asserts `(service.root / a).is_dir()` while the write is
  held. Without it the lock mutation (proof 5) stayed green: `purge_document` takes the store lock by itself, so the
  delete still blocked and the end state was correct. The folder removal is the step only the delete's own
  `with store.lock:` holds back; the assertion can only weaken the old-code proof, never fail correct code.
- The serialisation test starts the deleter after `entered` is set (inside the `try`), so the release in `finally`
  always runs.
