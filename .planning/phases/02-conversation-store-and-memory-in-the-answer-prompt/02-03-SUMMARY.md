---
phase: 02-conversation-store-and-memory-in-the-answer-prompt
plan: 03
subsystem: api
tags: [conversation-store, owner-scope, delete-cascade, lease, caps]
requires: ["02-02"]
provides:
  - "rag/api/conversations.py: CONVERSATION_ID, DOCUMENT_ID, CONVERSATIONS_DIR, FORMAT_VERSION, NoSuchConversation, ConversationFull, ConversationBusy, owner_key, scope_of, new_turn, to_history_turns, Conversation, Lease, ConversationStore"
affects: [02-04, 02-05, 02-06, 02-07, 02-08]
tech-stack:
  added: []
  patterns: ["atomic write and retry copied from service.py (not imported)", "folders created one level at a time, never with parents"]
key-files:
  created:
    - rag/api/conversations.py
    - .planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-03-SUMMARY.md
  modified: []
key-decisions:
  - "Checkpoint D-01 (Task 1): owner-folder, taken by auto_select in the unattended flow run"
  - "append_turn re-reads the header before the liveness check, so alive() covers documents an earlier turn already named"
  - "A damaged file is never overwritten; the write is dropped and counted, and purge_document removes it on the owner's next delete"
requirements-completed: [CONV-02, CONV-03, CONV-04, PRMT-04]
completed: 2026-10-25
status: complete
actuals:
  tasks: 3
  commits: 2
---

# Phase 2 Plan 03: Conversation store

## Checkpoint

- Task 1 (checkpoint:decision, D-01): **owner-folder** selected (auto_select). Cross-document
  conversations live under `data/uploads/_conversations/{sha256(owner)[:16]}/`; single-document ones
  under `{doc_id}/chat/conversations/`.

## Commits

- a1d104a feat(02-03): add the conversation store with owner and scope binding
- cd210e4 feat(02-03): add the conversation caps and the delete cascade

## Verification

- Fail-first: before the module existed, all three plan verify commands failed with
  `ModuleNotFoundError: No module named 'rag.api.conversations'`.
- `store tracer ok`
- `late writer ok`
- `cascade and caps ok`
- `python -m pytest tests/test_history.py tests/test_api.py -q`: 106 passed
- `grep -nE 'mkdir\([^)]*parents'`, the API/framework/status-code grep and the `CONVERSATION_ID.match(` grep
  print nothing; the P2_BASE diff check shows only `rag/query/history.py` and `rag/api/conversations.py`
  changed under `rag/`.

## Public names as built

`CONVERSATION_ID`, `DOCUMENT_ID`, `CONVERSATIONS_DIR = "_conversations"`, `FORMAT_VERSION = 1`,
`NoSuchConversation`, `ConversationFull`, `ConversationBusy`, `owner_key(owner)`, `scope_of(doc_ids)`,
`new_turn(question, answer, doc_ids, query_id, rewritten=None)`, `to_history_turns(turns)`,
`Conversation(id, owner_key, scope_key, doc_ids, path, is_new)`, `Lease.release()`,
`ConversationStore(root, max_turns, max_words)` with `root`, `lock`, `max_turns`, `max_words`,
`dropped_writes`, `open`, `lease`, `load_turns`, `check_room`, `append_turn`, `purge_document`.

## Deviations

None. Full test suite not run in this plan (nothing imports the module yet; plan 02-04 wires it).
