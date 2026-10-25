---
status: testing
phase: 02-conversation-store-and-memory-in-the-answer-prompt
source: [02-VERIFICATION.md]
started: 2026-10-25T00:00:00Z
updated: 2026-10-25T00:00:00Z
---

## Current Test

number: 1
name: Read max_model_len from the model server and record it
expected: |
  The command prints (model id, max_model_len); docs/models.md names the number, model id and date; tests/test_history.py's MODEL_CONTEXT_TOKENS check and tests/test_conversations.py::test_worst_case_prompt_plus_3600_fits_the_recorded_context_window still pass.
awaiting: user response

## Tests

### 1. Reconnect the PuTTY tunnel to 127.22.10.1:30007, run the one-off command in docs/models.md (Context window) to read max_model_len, then record the number in docs/models.md and in MODEL_CONTEXT_TOKENS in rag/query/history.py (currently the 8192 floor). Re-run the worst-case budget test and python -m rag.common.llm_check.
expected: The command prints (model id, max_model_len); docs/models.md names the number, model id and date; tests/test_history.py's MODEL_CONTEXT_TOKENS check and tests/test_conversations.py::test_worst_case_prompt_plus_3600_fits_the_recorded_context_window still pass.
result: [pending]

### 2. Review the Owner flag section (D-11) and decide whether Phase 2 may retain answer text for every question the page asks until Phase 5 adds retention and a conversation_id on the page.
expected: Owner accepts, or asks for a retention rule or for traces-off to skip writing history.
result: [pending]

### 3. Judgment-tier prohibitions of plans 02-01, 02-03, 02-05 to 02-09: no .env read, no probe retry loop, no logging of question/answer/owner/conversation id, no fixed sleep, no hook-flagged file named in a shell command.
expected: Owner agrees these held.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
