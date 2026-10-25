---
phase: 02-conversation-store-and-memory-in-the-answer-prompt
verified: 2026-10-25T14:00:00Z
status: human_needed
score: 5/5 must-haves verified
covered_files:
  - .planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-01-PLAN.md
  - .planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-01-SUMMARY.md
  - .planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-02-PLAN.md
  - .planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-02-SUMMARY.md
  - .planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-03-PLAN.md
  - .planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-03-SUMMARY.md
  - .planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-04-PLAN.md
  - .planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-04-SUMMARY.md
  - .planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-05-PLAN.md
  - .planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-05-SUMMARY.md
  - .planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-06-PLAN.md
  - .planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-06-SUMMARY.md
  - .planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-07-PLAN.md
  - .planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-07-SUMMARY.md
  - .planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-08-PLAN.md
  - .planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-08-SUMMARY.md
  - .planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-09-PLAN.md
  - .planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-09-SUMMARY.md
  - docs/models.md
  - rag/api/conversations.py
  - rag/api/main.py
  - rag/api/service.py
  - rag/query/history.py
  - tests/test_api.py
  - tests/test_conversations.py
  - tests/test_stream_api.py
covered_digest: "v3:sha256:98b0f83466ae9ddf540da918dcd55576f013a25c1f5011f1b85077d51a62d308"
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Reconnect the PuTTY tunnel to 127.22.10.1:30007, run the one-off command in docs/models.md (Context window) to read max_model_len, then record the number in docs/models.md and in MODEL_CONTEXT_TOKENS in rag/query/history.py (currently the 8192 floor). Re-run the worst-case budget test and python -m rag.common.llm_check."
    expected: "The command prints (model id, max_model_len); docs/models.md names the number, model id and date; tests/test_history.py's MODEL_CONTEXT_TOKENS check and tests/test_conversations.py::test_worst_case_prompt_plus_3600_fits_the_recorded_context_window still pass."
    why_human: "ROADMAP success criterion 5 and PRMT-04 rest on the recorded context window. It is still the 8192-token floor, not a measurement: the tunnel forward resets (WinError 10054, 2026-10-25). The owner decided on 2026-10-25 to keep the floor and re-read before the merge gate (parked in STATE.md). This is a known owner decision, not a code gap; the 8192 floor is the conservative value, so a larger real window only loosens the caps."
  - test: "Review the Owner flag section below (D-11) and decide whether Phase 2 may retain answer text for every question the page asks until Phase 5 adds retention and a conversation_id on the page."
    expected: "Owner accepts, or asks for a retention rule or for traces-off to skip writing history."
    why_human: "Judgment-tier prohibition and a product/privacy decision. The code does what D-11 says; whether that retention is acceptable is the owner's call. Flagged unverified-prohibition: human review recommended."
  - test: "Judgment-tier prohibitions of plans 02-01, 02-03, 02-05 to 02-09 (no .env read, no probe retry loop, no logging of question/answer/owner/conversation id, no fixed sleep, no hook-flagged file named in a shell command)."
    expected: "Owner agrees these held."
    why_human: "Non-authoritative verdict. The verifier did not read .env. Evidence: rag/api/conversations.py logs only reason words and counts (lines 197-215, 240-243, 340); tests/test_conversations.py has no time.sleep (grep run by the verifier); the 02-01 probe ran once and the SUMMARY records one attempt."
---

# Phase 2: Conversation store and memory in the answer prompt Verification Report

**Phase Goal:** As a chat user, I want to ask a follow-up inside a conversation that the server remembers for me, so that the answer uses my earlier turns while my history stays private to me, disappears with its document, and fits the model's context window.
**Verified:** 2026-10-25
**Status:** human_needed
**Re-verification:** No, initial verification
**Tree:** `flow/chat-memory` HEAD `1342e83` (only `.planning/` files differ from the measured tree `ebcf8f4`; `git status` shows only the untracked `.planning/state.json`).

## Goal Achievement

### Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
| - | ----- | ------ | -------- |
| 1 | Asking without a `conversation_id` on each of the four ask routes returns a new id in the body and in the `final` SSE event; asking again with that id answers using earlier turns; the saved trace shows a history block of at most the last N turns with questions and shortened answers; a first turn's prompt equals Phase 1's snapshot | VERIFIED | `rag/api/main.py` adds `conversation_id: Optional[str] = Field(None, max_length=512)` to `AskRequest` (inherited by `AskAcrossRequest`) and passes `conversation_id=request.conversation_id` on all four routes (read at lines 379-405). `DocumentService._describe` returns `conversation_id` and `turn`, and the stream's `final` event is the `_describe` result. `_retrieve` renders `render_block(window(to_history_turns(turns), HISTORY_WINDOW_TURNS))`, passes it to `rag.answer/stream(history_block=...)` and records `trace.config["conversation"] = {id, turn, history_turns, dropped_turns}`. Ran `tests/test_api.py -k history_block_of_at_most` (nine turns: trace says `history_turns: 6, dropped_turns: 2`, prompt holds exactly 6 `User:` lines, oldest kept first) and `tests/test_stream_api.py` (four parametrized route cases, separate conversations): pass. First turn: block is `""`, so the Phase 1 byte path runs; `test_the_first_turn_sends_the_prompt_with_no_history_block` and `tests/test_prompt_snapshot.py` pass. Prompt fingerprint recomputed as `b69624ed9d1a5781`. |
| 2 | Another owner's id, an unknown id, a malformed id and an id from a different document scope all return the same 404 body (never 403), decided in the store lookup before any model call; each turn stores the message, the rewritten question if any, the answer as shown, the document scope and a timestamp | VERIFIED | `ConversationStore.open` raises the single `NoSuchConversation` for malformed (`CONVERSATION_ID.fullmatch`), missing, unreadable and header-mismatch (owner_key, scope_key, id, version) cases; the folder is derived from `owner_key(owner)` and the declared scope, and `guarded()` maps it to `404 "no such conversation"` with no id echoed. `grep` for `HTTPException(403`, `owner = request`, `request.owner` in `main.py`: none; owner comes only from `Depends(current_owner)`. `test_a_foreign_unknown_malformed_and_wrong_scope_id_get_the_same_404` asserts one body set across 13 miss cases on ordinary and stream routes, no `text/event-stream` content type, and the model never called; `test_an_id_up_to_512_characters...` pins 404 up to 512 and 422 at 513. `new_turn` stores `question, rewritten, answer, doc_ids, asked_at, query_id, scan`; `_remember` stores `result["answer"]` (after the output filter / StreamGuard replace) on success only. `test_a_turn_stores_the_message_the_shown_answer_the_scope_and_a_timestamp` passes. |
| 3 | Deleting a document removes the conversation history under it, including a delete racing an in-flight turn; cross-document scope per D1 is stored per owner and removed when any document in its scope is deleted; no service LLM uses the disk cache | VERIFIED | Single-document conversations live at `{doc}/chat/conversations/{id}.json` and go with the folder; cross-document ones at `_conversations/{owner_key}/` and `purge_document` removes any whose header or turns name the document (exact membership), plus unparseable and `.tmp` files. `DocumentService.delete` runs `_remove_tree` and `purge_document` under `self.conversations.lock`; `append_turn` re-reads, checks `alive(union)` under the same lock, and creates folders one level at a time (`mkdir(exist_ok=True)`, no `parents`; grep clean), so a deleted folder is never recreated. Tests (all ran and passed): `test_deleting_a_document_also_deletes_its_conversations` (asserts no `*.json` left under the root), `test_delete_purges_cross_document_conversations...`, `test_a_delete_during_a_turn_leaves_no_conversation_file` (one document / all documents x ordinary / streamed, gated model), `test_delete_is_serialised_with_a_conversation_write`. Cache: only one `get_llm(` call in `rag/api`, `get_llm(setting("RAG_LLM", ...), cache_dir=None)`; `test_every_llm_the_service_builds_has_no_disk_cache` (spy) and `test_no_get_llm_call_in_rag_api_omits_cache_dir_none` pass. The plan summaries record fail-first and mutation proofs (e.g. liveness check always passing: 4 failed). |
| 4 | A stored turn with an injected instruction or a stale `[S n]` marker reaches the next prompt only after scanning and defanging, with markers stripped; streamed answers still reach the client only through `StreamGuard` | VERIFIED | `to_history_turns` -> `render_block` -> `neutralize` (Phase 1 helper, unchanged: withheld notice, `RULES` spans replaced, `_CITATION` stripped, rescan, `filter_output`, whitespace collapse). `service.py` never builds a history block any other way. No edit to `rag/query/guard.py`, `generate.py`, `pipeline.py`, `prompt.py` or `static/index.html` since P2_BASE (git diff names only the four allowed `rag/` files). `test_an_injected_instruction_and_a_stale_marker_are_defanged_in_the_next_prompt` (standard, spotlight), `test_forged_role_lines_in_a_stored_turn_stay_on_one_line` and `test_a_hostile_streamed_answer_is_stored_as_the_withheld_notice` pass. The stream path is unchanged: `rag.stream` still yields guarded events and `_remember` stores the `final` result's `answer`. |
| 5 | A conversation that reaches the turn or word cap is refused with a clear error status before any model call and before any SSE byte, and a worst-case budget test shows history + passages + 3000 thinking tokens + answer budget fits the recorded context window | VERIFIED (against the 8192 floor; see human item 1) | `_retrieve` runs `check_room` (50 turns / 20000 stored words) and, for a non-empty block, `fits_context(system, user)` on the real `build_prompts` output, all before `retrieval.run`'s answer stage and inside the `guarded()` call; `ConversationFull` maps to `409 "this conversation is full; start a new conversation"`; the lease is released on any raise (`except BaseException`). `fits_context` = `ceil(words * 1.5) + THINKING_TOKENS (3000) + ANSWER_TOKENS (600) <= MODEL_CONTEXT_TOKENS (8192)`. Tests pass: `test_a_full_conversation_is_refused_before_any_model_call_or_sse_byte`, `test_the_stored_word_cap_refuses_the_next_turn`, `test_an_oversized_follow_up_is_refused_but_a_first_turn_is_not`, `test_worst_case_prompt_plus_3600_fits_the_recorded_context_window` (seven maximal turns windowed to six, 1999-character question, five 300-word passages, standard and spotlight; the 1000-word pathological question does not fit and is refused as a follow-up). The "recorded context window" is the documented 8192 floor, not a measured `max_model_len`. |

**Score:** 5/5 truths verified (0 present-but-behavior-unverified). Behavior-dependent truths (delete race, lease release, caps, ordering) each have a named behavioral test that was run in this verification.

### Plan-level must-haves

| Plan | Truth | Status | Evidence |
| ---- | ----- | ------ | -------- |
| 02-01 | `P2_BASE` recorded; Phase 1 contract ok; context window in force written to docs/models.md and STATE.md | VERIFIED | `P2_BASE=346cd43e71f9943432eafe38a03a690a658b2dc2` present in `02-01-SUMMARY.md` and used by the phase check below. Value in force is the 8192 floor (see human item 1). |
| 02-02 | `THINKING_TOKENS`, `ANSWER_TOKENS`, `CONVERSATION_MAX_STORED_WORDS`, `estimate_prompt_tokens`, `fits_context`, `block_turns` in `rag/query/history.py`; Phase 1 constants and helpers unchanged | VERIFIED | Read the diff: only additions and one comment change; `tests/test_history.py` and `tests/test_prompt_snapshot.py` unchanged since P2_BASE and pass. |
| 02-03 | `rag/api/conversations.py` store with owner and scope binding, lease, caps, atomic writes, cascade; no `parents`, no HTTPException, no import of service | VERIFIED | Read in full (341 lines). Greps clean. |
| 02-04 | Service and routes wired; 404/409 mappings; delete under the store lock; budget refusal | VERIFIED | Read the full diff of `service.py` and `main.py`. |
| 02-05 to 02-08 | Tests appended without changing existing tests; fail-first proofs | VERIFIED | `git diff --stat P2_BASE HEAD -- tests` shows only additions to `tests/test_api.py` (106), `tests/test_stream_api.py` (98) and the new `tests/test_conversations.py` (525); `git diff --numstat` shows 0 deletions in all three test files. Suites re-run: 436 passed. The two `time.sleep` calls in `tests/test_stream_api.py` (lines 190, 299) pre-date the phase (2 in P2_BASE, none in the added hunks); `tests/test_conversations.py` has none. |
| 02-09 | Gate: full suite, retrieval invariant, snapshot, prohibition checks, STATE.md baseline, owner flag | VERIFIED | Invariant record and Owner flag copied verbatim below; verifier re-ran the prohibition check and the fingerprint. |

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `rag/api/conversations.py` | Owner-scoped, deletable conversation store | VERIFIED | Exists, substantive, imported by `service.py` and `main.py`, used on every ask path. |
| `rag/api/service.py` | `_retrieve` with conversation, `_remember`, `_alive`, delete cascade | VERIFIED | Wired; data flows from the stored file into the prompt (Level 4 below). |
| `rag/api/main.py` | `conversation_id` on four routes, 404/409 mapping | VERIFIED | Four `conversation_id=request.conversation_id` call sites. |
| `rag/query/history.py` | Budget helpers | VERIFIED | `fits_context` called by `service._retrieve`; `block_turns` used for the trace. |
| `tests/test_conversations.py`, additions to `tests/test_api.py`, `tests/test_stream_api.py` | Phase tests | VERIFIED | Run and pass. |
| `docs/models.md` Context window | Value in force | PARTIAL | Records the 8192 floor and the not-read outcome; no measured number (human item 1). |

### Key Link Verification

| From | To | Via | Status |
| ---- | -- | --- | ------ |
| `main.py` routes | `DocumentService.ask/ask_documents/ask_documents_stream` | `conversation_id=request.conversation_id` | WIRED |
| `DocumentService._retrieve` | `ConversationStore.open/lease/load_turns/check_room` | direct calls, lease released on any raise | WIRED |
| `_retrieve` | `RagPipeline.answer/stream` | `history_block=info["history_block"]` | WIRED |
| `_remember` | `ConversationStore.append_turn(..., self._alive)` | success path only, before `final` is yielded | WIRED |
| `DocumentService.delete` | `ConversationStore.purge_document` | inside `with self.conversations.lock:` after `_remove_tree` | WIRED |
| `guarded()` | `NoSuchConversation` / `ConversationBusy` / `ConversationFull` | 404 / 409 / 409 | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `service._retrieve` | `turns` -> `block` | `ConversationStore.load_turns` reads the JSON file written by `append_turn` | Yes: `test_the_saved_trace_shows_a_history_block...` reads the prompt of turn 9 and finds questions 2 to 7 | FLOWING |
| `_describe` response | `conversation_id`, `turn` | `Conversation.id` from `open`, `len(turns) + 1` | Yes | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Conversation, stream, snapshot, history and guard suites | `python -m pytest tests/test_conversations.py tests/test_stream_api.py tests/test_prompt_snapshot.py tests/test_history.py tests/test_stream_guard.py -q` | 436 passed in 36.47s | PASS |
| Route-level conversation tests | `python -m pytest tests/test_api.py -q -k "history_block_of_at_most or same_404 or 512_characters or also_deletes_its_conversations or repeated_document_ids"` | 6 passed | PASS |
| System prompts unchanged | sha256 of the four prompt strings, first 16 hex | `b69624ed9d1a5781` | PASS |
| Phase prohibition check (command in `02-09-SUMMARY.md`) | run in this checkout | printed the four allowed `rag/` files, then `phase checks ok` | PASS |
| `CLAUDE.md` / `.claude/CLAUDE.md` unchanged since P2_BASE | `git diff --quiet 346cd43... -- CLAUDE.md .claude/CLAUDE.md` | exit 0 | PASS |
| Full suite and retrieval | not re-run by the verifier; the orchestrator reported on this tree: `741 passed, 2 skipped` (743 collected) and hit@5 0.865, mrr 0.663 | matches the recorded invariant record below | PASS (orchestrator evidence) |
| Model server | `python -m rag.common.llm_check` | cannot run: tunnel forward resets | SKIP (human item 1) |

### Probe Execution

No probes declared. SKIPPED.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| CONV-01 | 02-04, 02-05, 02-06, 02-08, 02-09 | Optional `conversation_id` on the four ask routes; new id returned in body and `final` event | SATISFIED | Truth 1. |
| CONV-02 | 02-03, 02-04, 02-05, 02-06, 02-09 | Owner from `current_owner`; foreign, unknown, malformed id gives the same 404 | SATISFIED | Truth 2. |
| CONV-03 | 02-03, 02-04, 02-07, 02-09 | Turn holds message, rewritten question, answer as shown, scope, timestamp | SATISFIED | Truth 2 (`rewritten` stays `None` until Phase 3, as the requirement allows "if any"). |
| CONV-04 | 02-03, 02-04, 02-05, 02-07, 02-08, 02-09 | History stored where a document delete removes it; `cache_dir=None` stays | SATISFIED | Truth 3. D1 resolved as the per-owner folder (D-01 owner-folder). |
| PRMT-01 | 02-02, 02-04, 02-05, 02-07, 02-09 | History block of last N turns with short answers, system prompts unchanged | SATISFIED | Truths 1 and 4; fingerprint unchanged. |
| PRMT-03 | 02-04, 02-06, 02-07, 02-09 | Stored turns scanned and defanged, markers stripped; page uses `textContent`; streaming via `StreamGuard` | SATISFIED | Truth 4. `index.html` unchanged by this phase (page changes are Phase 5). |
| PRMT-04 | 02-01, 02-02, 02-03, 02-04, 02-06, 02-08, 02-09 | History + passages + answer budget fits the window; hard cap before any model call with a clear error | SATISFIED (floor) | Truth 5; the window is the 8192 floor pending human item 1. |

All seven IDs of the phase appear in at least one plan's `requirements:` and in `.planning/REQUIREMENTS.md`. REQUIREMENTS.md maps exactly these seven to Phase 2 (PRMT-02 is Phase 1), so there are no orphaned requirements. REQUIREMENTS.md still shows the seven as `[ ]` / Pending and ROADMAP.md still lists the Phase 2 plans as `[ ]`; the orchestrator should tick them.

### Anti-Patterns Found

None blocking. No `TBD`/`FIXME`/`XXX`/`TODO` introduced in the four `rag/` files or the three test files touched by the phase (greps run on the changed files). No stubs: every function on the request path does real work.

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `rag/api/service.py` | `_remember` in the stream `events()` | `append_turn` can raise `PermissionError` after its 2 s retry; in the stream that becomes an `error` event after tokens were sent, in the ordinary route a 502 | Info | Rare disk failure; the conversation is freed by the `finally` blocks. Not a goal gap. |
| `rag/api/main.py` | `guarded` | The prompt-budget refusal reuses "this conversation is full; start a new conversation" even when one long question is the cause | Info | Already recorded in the Owner flag; wording deferred to Phase 5. |

### Human Verification Required

1. **Read max_model_len through the tunnel.** Test: reconnect the PuTTY tunnel to 127.22.10.1:30007, run the one-off command in `docs/models.md` (Context window), record the number in `docs/models.md` and `MODEL_CONTEXT_TOKENS` in `rag/query/history.py`, then re-run the worst-case budget test and `python -m rag.common.llm_check`. Expected: the number is recorded and the budget tests still pass. Why human: the tunnel forward resets (WinError 10054); the owner parked this for the merge gate and kept the 8192 floor. Known owner decision, not a gap.
2. **Owner flag (D-11).** Review the Owner flag section below and accept or change the retention behaviour until Phase 5.
3. **Judgment-tier prohibitions** (non-authoritative, `unverified-prohibition: human review recommended`): no `.env` read, no probe retry loop, no text/owner/id logging, no fixed sleep, no hook-flagged file named in a shell command. The verifier did not read `.env`.

### Gaps Summary

No failing must-have. All five ROADMAP success criteria and all seven requirement IDs are backed by code that was read and by named tests that were run. The phase is `human_needed` rather than `passed` only because the recorded context window is still the 8192 floor (owner decision, parked for the merge gate), and because the D-11 retention flag and the judgment-tier prohibitions ask for human review. Known flaky test, not a phase gap: `tests/test_api.py::test_a_delete_during_a_load_leaves_nothing_in_the_store[one document]`.

---

_Verified: 2026-10-25_
_Verifier: Claude (gsd-verifier)_

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

## Owner flag

Conversation files are kept when `keep_traces` is off, because history is functional state (D-11). They live until a document in their scope is deleted. Until Phase 5 the page sends no `conversation_id` (D-06 creates a new conversation for every question without one), so every question asked on the page writes an orphan one-turn conversation file that is never continued, and the files grow by one per page question. That includes all-documents questions, whose answers no trace keeps today, so Phase 2 retains answer text the server did not keep before, in `data/uploads/_conversations/{owner_key}/`, until a document one of its turns resolved is deleted. There is no retention period yet; that is a Phase 5 docs and backlog item (CONTEXT.md Deferred). The prompt-budget refusal reuses the "this conversation is full; start a new conversation" 409 (D-16) even when the cause is one long question; clearer wording is left for Phase 5 to decide.

`python -m rag.common.llm_check` belongs to the flow verification gate (it needs the tunnel) and was not run by this plan; the tunnel forward was resetting (WinError 10054) on 2026-10-25, and `max_model_len` stays parked for the merge gate with `MODEL_CONTEXT_TOKENS` at the 8192 floor.

