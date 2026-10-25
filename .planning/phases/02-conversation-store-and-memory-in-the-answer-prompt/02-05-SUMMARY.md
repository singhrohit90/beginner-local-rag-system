---
phase: 02-conversation-store-and-memory-in-the-answer-prompt
plan: 05
subsystem: tests
tags: [conversations, chat-memory, tests, fail-first]
requires: ["02-04"]
provides:
  - "Route-level tests for the history window, the single 404, the 512-character limit, the delete cascade and duplicate document ids"
affects: ["02-06", "02-07", "02-08", "02-09"]
key-files:
  modified:
    - tests/test_api.py
requirements-completed: [CONV-01, CONV-02, CONV-04, PRMT-01]
---

# Phase 2 Plan 05: Conversation tests in tests/test_api.py

Five tests (six collected items: the 404 test runs on the memory and OpenSearch legs of `two_users`) and the
`NO_SUCH_CONVERSATION` constant appended to `tests/test_api.py` under
`# ---- conversations: memory across questions (phase 2) ----`. Imports added: `re`, `owner_key`,
`HISTORY_WINDOW_TURNS`. No existing test changed (`git diff P2_BASE -- tests/test_api.py` has no removed lines).

## Commits

| Task | Commit | Subject |
|------|--------|---------|
| 1 | cfe80af | test(02-05): pin the history window in the saved trace |
| 2 | bfe53dc | test(02-05): pin one 404 for every conversation miss |
| 3 | 9b318c3 | test(02-05): pin that conversations are deleted with their document |

## Fail-first proofs

P2_BASE=346cd43e71f9943432eafe38a03a690a658b2dc2 (`rag/api/service.py` and `rag/api/main.py` checked out at it,
restored with `git checkout HEAD -- ...`, `git diff --quiet HEAD -- rag` confirmed before each commit).

- Task 1, `-k history_block_of_at_most` at P2_BASE: `1 failed, 73 deselected in 1.59s` (KeyError: no conversation_id)
- Task 2, `-k "same_404 or 512_characters"` at P2_BASE: `3 failed, 74 deselected in 5.09s` (OpenSearch up, both legs failed; no passes)
- Task 3, `-k "also_deletes_its_conversations or repeated_document_ids"` at P2_BASE: `2 failed, 77 deselected in 3.05s`
- Task 3 mutation, `purge_document` line removed from `DocumentService.delete`, `-k also_deletes_its_conversations`:
  `1 failed, 78 deselected in 1.66s`

## Verification

- `python -m pytest tests/test_api.py -q`: `79 passed in 85.24s` (OpenSearch was up; no skips), including the
  unchanged `test_only_single_document_questions_are_saved_as_traces` and `test_deleting_a_document_also_deletes_its_traces`
- Full suite: `python -m pytest tests -q`: `708 passed, 2 skipped in 214.31s` (702 + 6 new items)

## Deviations

- Task 1 adds one assertion beyond the plan: the kept questions 2 to 7 appear in the prompt oldest first (the
  "turns keep completion order" truth).
- No fixed sleeps; all tests are synchronous.

## Self-Check: PASSED
