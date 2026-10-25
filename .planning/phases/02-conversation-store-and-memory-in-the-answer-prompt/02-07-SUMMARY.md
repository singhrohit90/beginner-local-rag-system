---
phase: 02-conversation-store-and-memory-in-the-answer-prompt
plan: 07
subsystem: tests
tags: [conversations, chat-memory, store, cascade, prompt, cache, tests, fail-first]
requires: ["02-04", "02-06"]
provides:
  - "tests/test_conversations.py: stored-turn record, stale-read safety, traces-off persistence, cross-document cascade, first-turn and follow-up prompts through build_prompts, defanged history, no disk cache"
affects: ["02-08", "02-09"]
key-files:
  created:
    - tests/test_conversations.py
requirements-completed: [CONV-03, CONV-04, PRMT-01, PRMT-03]
---

# Phase 2 Plan 07: Conversation store and prompt tests in tests/test_conversations.py

New module with `PARTITIONING`, helpers `recording`, `make_service`, `add_document`, `client_for`,
`conversation_file`, `stored`, `seed_turns` (plus `follow_up_trace`, which loads a single-document trace by
query id), and ten test functions collecting twelve cases:

- `test_a_turn_stores_the_message_the_shown_answer_the_scope_and_a_timestamp`
- `test_turns_are_read_after_the_lease_and_appends_keep_earlier_turns`
- `test_conversations_are_kept_when_traces_are_off`
- `test_delete_purges_cross_document_conversations_that_touched_the_document`
- `test_the_first_turn_sends_the_prompt_with_no_history_block`
- `test_the_history_block_sits_before_the_question_in_both_styles` (standard, spotlight)
- `test_an_injected_instruction_and_a_stale_marker_are_defanged_in_the_next_prompt` (standard, spotlight)
- `test_forged_role_lines_in_a_stored_turn_stay_on_one_line`
- `test_every_llm_the_service_builds_has_no_disk_cache`
- `test_no_get_llm_call_in_rag_api_omits_cache_dir_none`

`client_for` is defined for plan 02-08 and not used yet. No `rag/` file changed.

## Commits

| Task | Commit | Subject |
|------|--------|---------|
| 1 | 8a24810 | test(02-07): pin what a stored turn holds |
| 2 | c2f7554 | test(02-07): pin stale-read safety and the cross-document cascade |
| 3 | 112fbfc | test(02-07): pin the prompts with history, defanged turns and no disk cache |

## Fail-first proofs

P2_BASE=346cd43e71f9943432eafe38a03a690a658b2dc2. Each run restored with `git checkout HEAD -- <file>` and
`git diff --quiet HEAD -- rag` confirmed before each commit.

1. service.py and main.py at P2_BASE, `-k stores_the_message`: `1 failed in 1.60s`
2. service.py and main.py at P2_BASE, `-k "traces_are_off or purges_cross_document"`: `2 failed, 2 deselected in 4.21s`
3. Mutation: `append_turn` writes `data["turns"] = [dict(turn)]` (drops earlier turns), `-k read_after_the_lease`: `1 failed, 3 deselected in 1.08s`
4. service.py and main.py at P2_BASE, `-k "both_styles or defanged or role_lines"`: `5 failed, 7 deselected in 3.35s`
5. Mutation: `ask_documents` passes `history_block=info["history_block"] or "MUTATION MARKER\n\n"`, `-k first_turn_sends`: `1 failed, 11 deselected in 1.69s`
6. Mutation: `cache_dir=None` removed from `get_llm` in `build_default_service`, `-k "no_disk_cache or omits_cache_dir"`: `2 failed, 10 deselected in 1.05s`

## Verification

- `python -m pytest tests/test_conversations.py -q`: `12 passed`; `--collect-only`: `12 tests collected`
- `python -m pytest tests/test_conversations.py tests/test_history.py tests/test_prompt_snapshot.py -q`: `123 passed in 6.57s`
- Full suite in the worktree: `727 passed, 2 skipped in 193.00s` (715 + 12 new)

## Deviations

- The plan's `seed_turns` reuses the conversation opened as new for every append; this works because
  `append_turn` re-reads the file whenever it exists, so no reopen is needed.
- The hostile reply turn uses the question "Show me a picture"; the plan did not fix that question's text.
