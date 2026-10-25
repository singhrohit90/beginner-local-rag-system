---
phase: 03-rewrite-clarify-and-topic-switch
plan: 07
requirements: [RWR-03, RWR-04]
files_modified:
  - tests/test_rewrite_api.py
status: complete
---

# 03-07 Summary: clarify, never-two-in-a-row, topic switch and the named bad rewrites through the service

START=511461f (branch work/03-07, cut from flow/chat-memory after the 03-06 merge); P3_BASE=d65b26860d4de95ba5fd062cf28b1e5ad210ef0d

## What was built

Additions to `tests/test_rewrite_api.py`: constants `TWO_NAMES_TURN`, `CLARIFY_LINE`, `PAGE_KEYS`, `NAMED_BAD_REWRITES`; helper `ask(service, client, doc_id, cid, message, streamed)`; 6 test functions, 12 collected cases (module total 42):

- RWR-03 / D-12: `test_a_clarifying_question_uses_the_normal_shape` (ordinary, streamed), `test_a_clarification_is_stored_with_its_kind`, `test_a_clarifying_question_with_a_link_falls_back` (ordinary, streamed).
- RWR-03 / D-13: `test_an_ambiguous_message_after_a_clarification_is_answered_not_clarified` (ordinary, streamed).
- RWR-04 / D-14: `test_a_topic_switch_starts_a_clean_history`.
- RWR-04 / D-08: `test_the_four_named_bad_rewrites_fall_back_through_the_service` (invented_details, dropped_constraints, wrong_pronoun, topic_leak; literals copied from `tests/test_rewrite.py` `BAD_REWRITES`).

## Commits

- `87ea682` test(03-07): pin the clarifying question's shape and storage
- `88411ef` test(03-07): pin one clarification at a time and the clean history after a topic switch
- `2ed9c04` test(03-07): pin the four named bad rewrites through the service

## Verification

- Task 1 verify: `3 passed, 30 deselected`. Task 2 verify: `8 passed, 30 deselected`. Task 3 module run: `42 passed`.
- Fail-first (a), `rag/api/service.py`, `rag/api/main.py`, `rag/api/conversations.py` at P3_BASE, new test ids only: `12 failed, 30 deselected in 2.01s`; restored, `rag clean`.
- Fail-first (b), `_rewrite` returning `win` instead of `[]` for new_topic: `-k clean_history` gave `1 failed, 41 deselected in 1.62s`; restored.
- Fail-first (c), `allow = True` in `_rewrite`: `-k not_clarified` gave `2 failed, 40 deselected in 2.81s`; restored, `rag clean`.
- Neighbours (`test_rewrite`, `test_rewrite_api`, `test_conversations`, `test_api`, `test_stream_api`, `test_history`, `test_prompt_snapshot`): `342 passed in 137.70s`, `neighbours ok`.
- `conversations_draft` count 0 in both test files (D-15).
- Full suite in the worktree: `838 passed, 2 skipped in 251.46s` (826 passed, 2 skipped after 03-06).

## Deviations

- `ask(...)` returns a fourth value, the raw response text, so the link test can check the whole body and every frame for `evil.example`.
- The topic-switch test uses the COMPACTION document (its message is about compaction); the plan says only "one document".
- `test_a_clarifying_question_with_a_link_falls_back` also asserts one rewriter call.
