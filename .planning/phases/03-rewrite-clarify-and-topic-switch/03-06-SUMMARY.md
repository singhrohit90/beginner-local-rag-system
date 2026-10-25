---
phase: 03-rewrite-clarify-and-topic-switch
plan: 06
requirements: [RWR-01, RWR-02]
files_modified:
  - tests/test_rewrite_api.py
status: complete
---

# 03-06 Summary: service and route tests for the gate, the switch, the rewrite and the visible fallback

START=7bab2b1 (branch work/03-06, cut from flow/chat-memory); P3_BASE=d65b26860d4de95ba5fd062cf28b1e5ad210ef0d

## What was built

`tests/test_rewrite_api.py` (new): constants `RAFT_TURN`, `PRONOUN`, `OFF`, `SEVEN_KEYS`, `FOUR_KEYS`, `FAILURE_SHAPES`, `LEAKS`; helpers `rewriter(*replies)`, `rewrite_service(tmp_path, *replies, llm=None)`, `append_flagged_turn(...)`, `trace_of(service, doc_id, result)`, `spied_settings(monkeypatch, tmp_path)`; 13 test functions, 30 collected cases:

- RWR-01 / D-04 / D-05: `test_the_first_turn_makes_no_rewrite_call`, `test_a_long_marker_free_message_passes_unchanged_with_no_call`, `test_the_pronoun_follow_up_makes_exactly_one_rewrite_call` (raft.pdf and Paxos-notes.pdf both in the rewriter prompt, last line `Last message: ...`).
- D-01 / D-02: `test_with_the_switch_off_nothing_changes`, `test_the_switch_needs_a_rewriter`, `test_build_default_service_ships_the_switch_off`, `test_build_default_service_builds_the_rewriter_only_when_on` (5 cases).
- RWR-02 / D-10 / D-11: `test_a_pronoun_follow_up_is_rewritten_and_retrieval_runs_on_the_rewrite`, `test_the_trace_the_response_and_the_turn_record_both_texts`, `test_the_streamed_response_has_the_same_rewrite_and_kind_as_the_ordinary_one`.
- D-09: `test_a_rewriter_failure_is_a_visible_fallback_before_any_sse_byte` (7 shapes x ordinary/streamed = 14 cases), `test_a_real_ollama_client_that_is_down_gives_unavailable`, `test_the_real_ollama_request_for_a_rewrite_is_pinned`.

## Characterised fact (RESEARCH A2)

The real Ollama client's rewrite request: `sorted(payload["options"]) == ["num_ctx", "num_predict", "temperature"]`, `temperature` 0.0, `num_predict` 120, no `format` key, `messages[0] == {"role": "system", "content": REWRITE_SYSTEM_PROMPT}`, and `urlopen(..., timeout=600.0)` (the client's default timeout; the rewriter does not shorten it). Both are pinned with equality asserts.

## D-09 note

D2 is resolved fail-open with a visible flag: every failure shape (refused, cannot reach, ollama serve, TimeoutError, "timed out" text, empty, prose) gives HTTP 200, an answer on the raw message and `rewrite == {"status": "fallback", "reason": <code>, "rewritten_question": None}`; the body never contains `127.22.10.1` or `ollama serve`. On the stream the rewriter call has already happened when `ask_documents_stream` returns, before any event is read.

## Commits

- `b44604d` test(03-06): pin the rewrite call count and both recorded texts
- `aa3e702` test(03-06): pin the switch, its settings and retrieval on the rewrite
- `808b474` test(03-06): pin the visible fallback and the real Ollama request

## Verification

- Task 1 verify: `3 passed`. Task 2 verify: `14 passed`; Phase 2 regression `-k "switch_off or ships_the_switch_off or only_when_on or no_disk_cache or omits_cache_dir or busy"`: `11 passed, 29 deselected`. Task 3 verify: `30 passed`; `rag clean`.
- Fail-first (a), `rag/api/service.py`, `rag/api/main.py`, `rag/api/conversations.py` at P3_BASE: `30 failed in 2.11s`; restored, `rag clean`.
- Fail-first (b), `new_turn` mutated to always store `kind`: `-k switch_off_nothing` gave `1 failed, 29 deselected in 2.07s`; restored, `rag clean`.
- Extra mutation, `_retrieve` retrieving on the raw message instead of `result.question`: `2 failed, 28 passed` (the both-texts and retrieval-on-the-rewrite tests); restored, `rag clean`.
- `time.sleep` count 0; no `.env` read; Phase 2 test files unchanged.
- Full suite in the worktree: `826 passed, 2 skipped in 244.73s` (baseline 796 passed, 2 skipped).

## Deviations

- `spied_settings` replaces `rag.api.main._EMBEDDERS` with a fresh dict via monkeypatch instead of clearing it, so nothing loaded in the test outlives it.
- The streamed failure case seeds two conversations: one for the direct `ask_documents_stream` check, one for the HTTP stream route, so each request is a clean second turn.
- `FakeResponse` is imported from `tests/test_ollama.py` (not edited) instead of being redefined.
- The plan's `.env` acceptance grep was run with the Grep tool; the shell hook refuses any command containing the pattern.
