# Phase 2: Conversation store and memory in the answer prompt - Context

**Gathered:** 2026-10-22
**Status:** Ready for planning
**Mode:** `--auto` (every gray area took the recommended option; each pick is recorded as an assumption below)

<domain>
## Phase Boundary

A server-side, owner-scoped, deletable conversation store, and the history block from Phase 1 wired into the answer prompt, with the rewrite still absent. Delivers: an optional `conversation_id` on the four ask routes (`POST /v1/ask`, `/v1/ask/stream`, `/v1/documents/{id}/ask`, `/v1/documents/{id}/ask/stream`), returned in the response body and the `final` SSE event; a new `rag/api/conversations.py` store (ids, paths, owner and scope check, cap check, delete cascade); `DocumentService._retrieve` loading the window and passing `render_block(window(turns))` as `history_block` to `RagPipeline.answer/stream`; one stored turn per successful answer; identical 404 for every miss; a hard cap refused before any model call and any SSE byte; `get_llm(..., cache_dir=None)` proven for every service LLM.

Requirements: CONV-01, CONV-02, CONV-03, CONV-04, PRMT-01, PRMT-03, PRMT-04. Not in this phase: the rewriter, clarifying questions, topic switch (Phase 3); the page (Phase 5: the page keeps sending no id, so today's page behaviour is unchanged); `/v1/ask-about` (stays stateless); a `GET` for one conversation and an explicit conversation delete (v2: CONV-05, CONV-06).

</domain>

<decisions>
## Implementation Decisions

### Carried forward from Phase 1 (locked there, not re-asked)
- The seam is `history_block: str = ""` on the builders and per call on `RagPipeline.answer(trace, history_block="")` / `.stream(trace, history_block="")`; an empty block returns today's bytes (Phase 1 D-06, D-07).
- `rag/query/history.py` holds `HistoryTurn`, `window`, `neutralize`, `render_block` and the budget constants; `rag/query/` stays pure (no I/O, no owner) (Phase 1 D-09).
- `SYSTEM_PROMPT`, `DOCUMENT_SYSTEM_PROMPT`, `SPOTLIGHT_ADDENDUM`, `NAIVE_SYSTEM_PROMPT` wording is not touched (Phase 1 D-08).

### D1 — cross-document conversation storage
- **D-01:** Cross-document conversations are stored (D1 Option A), not refused. Single-document conversations (the request's declared `doc_ids` is an explicit list of exactly one id, which includes every `/v1/documents/{id}/ask*` call) live at `data/uploads/<doc_id>/chat/conversations/<conversation_id>.json`; every other scope (several ids, or `null` = all) lives at `data/uploads/_conversations/<owner_key>/<conversation_id>.json` with `owner_key = sha256(owner)[:16]`. The location is decided by the declared scope, not the resolved document count. `_conversations` never matches `DOC_ID` (`^[0-9a-f]{12}$`), so every existing directory scan skips it, and it is already under the gitignored `data/uploads/`. — **Reversibility:** one-way — the on-disk layout is read by the delete cascade and by every later phase; moving it later needs a migration of existing conversation files. [auto: recommended — ARCHITECTURE.md recommends it; cross-document scope is the page's default flow, so refusing would leave memory absent where users chat most]
- **D-02:** Delete cascade: deleting a document removes its folder (single-document conversations go with it, no new code) and then calls `ConversationStore.purge_document(owner, doc_id)`, which removes every cross-document conversation file of that owner whose recorded scope (header `doc_ids` union, plus every turn's resolved `doc_ids`) contains the id. Whole-file removal, never redaction. A deleted-document test and an in-flight race test (delete while a turn is being answered; the deleted folder is not recreated, the cross-document file is not rewritten) are required. [auto: recommended]
- **D-03:** The conversation writer never creates parent folders with `parents=True` under a document folder; it writes only if the document folder still exists and the id is not in `DocumentService._deleting`, re-checked inside the store lock immediately before the write. A late writer after a delete drops the turn silently from storage (the answer is still returned) and logs a count, never document text. [auto: recommended — Pitfall 6]

### Conversation identity and lookup
- **D-04:** Ids are server-generated `secrets.token_hex(16)` (32 lowercase hex). The request field is `conversation_id: Optional[str] = Field(None, pattern=r"^[0-9a-f]{32}$")` on `AskRequest` (inherited by `AskAcrossRequest`). A malformed id must produce the same 404 body as an unknown id, so validation of the pattern happens in the store, not as a Pydantic 422: the request field is `Optional[str]` with `max_length=64`, and `ConversationStore` rejects anything that does not match `^[0-9a-f]{32}$` with `NoSuchConversation` before the value touches a path. [auto: recommended — CONV-02 requires one body for every miss]
- **D-05:** A conversation is bound to the owner and to the scope it started with (scope key: the sorted declared `doc_ids` tuple, or `"all"`). Lookup is by (owner, location implied by the request scope, id, scope key); another owner's id, an unknown id, a malformed id and an id from a different scope all raise `NoSuchConversation`, mapped in `guarded()` (`rag/api/main.py`) to `HTTPException(404, "no such conversation")` — one body for all four. The lookup runs inside `_retrieve`, before retrieval and before any model call. [auto: recommended]
- **D-06:** Absent `conversation_id` creates a new conversation (no file is written until the first turn succeeds). The id is returned as `"conversation_id"` in the JSON response and in the `final` SSE event's data. `tests/test_stream_api.py::test_the_streamed_response_equals_the_ordinary_one` is updated to ignore `conversation_id` (the two calls create two conversations). [auto: recommended]

### File format and concurrency
- **D-07:** One JSON file per conversation, `{"header": {...}, "turns": [...]}`, rewritten atomically (temp file plus `os.replace`, retried on Windows `PermissionError`, the `_atomic_write` pattern copied into `rag/api/conversations.py`, not imported from `service.py`). Header: `id`, `owner_key`, `scope_key`, `doc_ids`, `created_at`, `version: 1`. Chosen over append-only JSONL because ARCHITECTURE.md recommends it, it reuses an existing repo pattern, and the cap keeps files small. [auto: recommended]
- **D-08:** Concurrent requests on one conversation: a per-conversation lock is taken in `_retrieve` (non-blocking acquire) and held until the turn is persisted or the stream ends; a second request on the same id while the first holds it gets `ConversationBusy`, mapped to `HTTPException(409, "conversation is busy, retry when the previous answer is finished")` before any SSE byte. The lock is released in the stream's `finally`, so a client that disconnects frees it. [auto: recommended — option listed first in ROADMAP; keeps every window complete]

### What a turn stores (CONV-03)
- **D-09:** Each stored turn: `question` (the user's message as sent), `rewritten` (`null` in this phase), `answer` (the answer as shown: `trace.answer` after the output filter; a withheld answer is stored as the withheld text the caller saw), `doc_ids` (resolved scope of this turn), `asked_at` (UTC ISO 8601 via `datetime.now(timezone.utc)`), `query_id`, and `scan` (the `scan_text` rule names found in question and answer at write time). Citations are not stored (v2 CONV-07). [auto: recommended]
- **D-10:** A turn is persisted only on the success path, immediately before the `final` event is yielded (streaming) or the response is returned (ordinary), so a failed, aborted or errored turn is never stored. [auto: recommended]
- **D-11:** Conversation files are kept even when `keep_traces=False`: history is functional state, not a trace. Flagged to the owner in the phase summary. [auto: recommended — research lean; flagged]

### History in the prompt (PRMT-01, PRMT-03)
- **D-12:** `_retrieve` loads the stored turns, converts them to `HistoryTurn`s, takes `window(turns, HISTORY_WINDOW_TURNS)`, runs every question and answer through `neutralize` (scan, defang, strip `[S n]`, collapse whitespace, truncate to `HISTORY_QUESTION_MAX_WORDS` / `HISTORY_ANSWER_MAX_WORDS`), and passes `render_block(...)` as `history_block` to `RagPipeline.answer/stream`. Retrieval itself still runs on the raw latest message in this phase. A first turn passes `history_block=""`, so its prompt equals Phase 1's snapshot. [auto: recommended]
- **D-13:** The trace records `trace.config["conversation"] = {"id", "turn", "history_turns", "dropped_turns"}` (`dropped_turns` = turns outside the window or dropped by the 400-word block cap). `Trace` dataclass and old trace files are untouched. [auto: recommended]
- **D-14:** Streamed answers still reach the client only through `StreamGuard` (unchanged code path); the stored answer is the post-filter `trace.answer`. [locked by CLAUDE.md]

### Budget and hard cap (PRMT-04, D3)
- **D-15 (D3 pinned):** Keep Phase 1's Option A numbers: `HISTORY_WINDOW_TURNS = 6`, `HISTORY_BLOCK_MAX_WORDS = 400`, `HISTORY_ANSWER_MAX_WORDS = 40`, `HISTORY_QUESTION_MAX_WORDS = 60`, `CONVERSATION_MAX_TURNS = 50`, `TOKENS_PER_WORD = 1.5`, and `MODEL_CONTEXT_TOKENS` from `docs/models.md` (the 8192 floor if Phase 1 could not read `max_model_len`). If Phase 1 recorded a larger real `max_model_len`, the constants still stay at Option A in this phase (raising them is a measured change for later). Add `CONVERSATION_MAX_STORED_WORDS = 20000` as the word side of the hard cap. — **Reversibility:** reversible — constants in one module. [auto: recommended — Option A is safe at the 8192 floor]
- **D-16:** The hard cap is checked in `_retrieve` before retrieval and before any model call: a conversation with `CONVERSATION_MAX_TURNS` stored turns, or whose stored words reach `CONVERSATION_MAX_STORED_WORDS`, raises `ConversationFull`, mapped in `guarded()` to `HTTPException(409, "this conversation is full; start a new conversation")` before any SSE byte. A second check refuses the request with the same 409 when the computed prompt budget (`(system words + passage words + history block words + question words) * TOKENS_PER_WORD + 3000 + 600`) would exceed `MODEL_CONTEXT_TOKENS`; this covers a long live question (the API allows 2000 characters). A worst-case budget test at the caps is required. [auto: recommended]

### Cache and isolation (CONV-04)
- **D-17:** `get_llm(..., cache_dir=None)` stays for every LLM the service builds; a spy test monkeypatches `rag.common.llm.get_llm` (by dotted string in Python, never named in a shell command) during `build_default_service` and asserts every call had `cache_dir=None`. [auto: recommended]

### Module split
- **D-18:** New code lives in `rag/api/conversations.py` (`ConversationStore`, `NoSuchConversation`, `ConversationFull`, `ConversationBusy`); `rag/api/service.py` wires it (`DocumentService(..., conversations=None)` builds one from `self.root`); `rag/api/main.py` adds the request field, the response passthrough and the three exception mappings. Tests: new `tests/test_conversations.py` (store unit tests) and additions to `tests/test_api.py` / `tests/test_stream_api.py` (route-level). [auto: recommended]

### Claude's Discretion
- Exact class and method names inside `ConversationStore` beyond those listed (`open`, `append_turn`, `purge_document` are suggestions).
- Error message wording for 404/409 (must be one fixed string per status, no id echoed).
- Where in `_describe` the `conversation_id` and `turn` fields are added.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scope and requirements
- `.planning/REQUIREMENTS.md` — CONV-01..04, PRMT-01, PRMT-03, PRMT-04; Out of Scope table
- `.planning/ROADMAP.md` §"Phase 2" — success criteria 1-5, open decisions D1 and D3 and the smaller points
- `.planning/PROJECT.md` §Constraints and §Key Decisions

### Phase 1 outputs this phase builds on
- `.planning/phases/01-safety-net-and-prompt-seam/01-CONTEXT.md` — seam shape, history helpers, D3 provisional constants
- `.planning/phases/01-safety-net-and-prompt-seam/01-03-PLAN.md`, `01-05-PLAN.md` — exact seam signatures and `history.py` symbols
- `docs/models.md` "Context window" section (written by Phase 1 plan 01-02) — the `MODEL_CONTEXT_TOKENS` source

### Design and research
- `.planning/research/ARCHITECTURE.md` — store layout (lines ~120-150), scope binding, cascade, request flow steps 1-13, error mapping
- `.planning/research/PITFALLS.md` — Pitfalls 5 (owner and enumeration), 6 (delete and resurrection), 7 (cache leak), 8 (concurrency), 9 (errors before SSE), 12 (overflow), 19 (Windows files)
- `.planning/research/SUMMARY.md` §"Open Decisions" D1, D3 and the smaller points
- `interview/05_conversation_memory_and_cost.md` — design: server-side history, untrusted history, budget formula

### Code
- `rag/api/main.py` — `AskRequest` (line ~123), `AskAcrossRequest`, `guarded()` (line ~316), `stream_request`, `current_owner`, `build_default_service` (`get_llm(..., cache_dir=None)` line ~167)
- `rag/api/service.py` — `DOC_ID`, `_dir`, `_atomic_write`, `delete`, `_deleting`, `_ready_documents`, `_retrieve` (line ~441), `_describe`, `ask_documents`, `ask_documents_stream`
- `rag/query/pipeline.py` — `RagPipeline.answer`, `.stream` (seam from Phase 1)
- `rag/query/history.py` — created in Phase 1
- `rag/query/guard.py` — `scan_text`, `filter_output`, `StreamGuard`
- `tests/test_api.py`, `tests/test_stream_api.py` — `make_client`, trace-count globs on `chat/*.json`, `test_the_streamed_response_equals_the_ordinary_one`

### Conventions
- `.planning/codebase/TESTING.md`, `.planning/codebase/CONVENTIONS.md`, `CLAUDE.md` (security conventions; never name the hook-flagged files in a command)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `DocumentService._atomic_write` (temp file + `os.replace` with Windows retry) — copy the pattern into `rag/api/conversations.py`
- `DocumentService._remove_tree` — the delete already removes `data/uploads/<doc_id>/` including `chat/`
- `DocumentService._deleting` set and `_load_lock` — the race guard the writer re-checks
- `guarded()` in `rag/api/main.py` — the single place errors become HTTP statuses before streaming; `BadUpload` already maps to 409
- `make_client(tmp_path, llm=FakeLLM(...))` in `tests/test_api.py` — route tests; `current_owner` override to act as two owners

### Established Patterns
- Service raises domain exceptions; routes map them (`NotFound` -> 404, `BadUpload` -> 409, other -> 502)
- Every directory scan filters on `DOC_ID.match`, so a non-hex folder name is invisible to `list()`, `list_in()` and `_recover_interrupted()`
- Traces for single-document asks go to `data/uploads/<doc_id>/chat/*.json`; tests count them with `glob("*.json")`, so conversation files go one level down in `chat/conversations/`
- `_retrieve` runs everything before the model, so streaming errors become statuses before any byte

### Integration Points
- `_retrieve` (steps: ready documents -> conversation open/scope check -> cap check -> window/neutralize/render -> retrieval) returns the history block with `rag, trace, info`
- `ask_documents` / `ask_documents_stream` call `rag.answer(trace, history_block=...)` / `rag.stream(trace, history_block=...)`, then persist the turn before returning / before yielding `final`
- `DocumentService.delete` calls `purge_document` after the store delete

</code_context>

<specifics>
## Specific Ideas

- The four-way 404 test (foreign owner, unknown, malformed, wrong scope) asserts the response bodies are byte-equal.
- The cap tests assert the 409 arrives before any model call (a `FakeLLM` call counter stays at zero) and, for the stream route, before any SSE byte (status 409, not a 200 stream with an `error` event).
- An injected instruction and a stale `[S3]` in a stored answer must not appear verbatim in the next turn's prompt (assert on `trace.prompt`).

</specifics>

<deferred>
## Deferred Ideas

- `GET /v1/conversations/{id}` to resume after reload (v2 CONV-05) and explicit single-conversation delete (v2 CONV-06)
- Per-turn citations stored with each turn (v2 CONV-07)
- Retention/TTL for conversations of documents never deleted — same backlog item as trace retention (Phase 5 docs)
- Raising the history caps to a measured larger `max_model_len` — later, by measurement
- Page plumbing for the id and "New conversation" — Phase 5 (PAGE-01)

</deferred>

---

*Phase: 02-conversation-store-and-memory-in-the-answer-prompt*
*Context gathered: 2026-10-22 (auto mode)*
