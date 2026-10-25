# Requirements: Local RAG System: Chat Memory

**Defined:** 2026-10-21
**Core Value:** A follow-up question with a pronoun retrieves the passages the standalone phrasing would, while a single-turn question produces exactly the prompt bytes and cached answer it produces today.

Source: `.planning/runs/20261021-1840-chat-memory/requirements-reconstructed.md` (R1-R10). Each REQ-ID below names the R-item it comes from. Research (`.planning/research/`) informed the wording and the Out of Scope reasons; it did not add v1 scope.

## v1 Requirements

Requirements for the chat-memory milestone. Each maps to roadmap phases.

### Conversation identity and history (R1, R2)

- [x] **CONV-01** (R1): `POST /v1/ask`, `/v1/ask/stream`, `/v1/documents/{id}/ask` and `/v1/documents/{id}/ask/stream` accept an optional `conversation_id`; when it is absent a new conversation is created and its id is returned in the response body and in the `final` SSE event
- [x] **CONV-02** (R1): A conversation belongs to the owner from `current_owner`; another owner's id (and an unknown or malformed id) returns 404, never 403, with the same body for every miss (test required)
- [x] **CONV-03** (R2): Each turn stores the user's message, the rewritten question (if any), the answer as shown (after the output filter), the document scope and a timestamp
- [x] **CONV-04** (R2): History is stored where a document delete removes it: single-document conversations under `data/uploads/<doc_id>/chat/` (in a subfolder so existing `chat/*.json` trace counts are unchanged); cross-document conversations either under a per-owner folder with the cross-document trace retention rule or refused for cross-document scope in this milestone (open decision D1, `.planning/research/SUMMARY.md`); deleting a document removes its conversation history (test required); `get_llm(..., cache_dir=None)` stays for every service LLM including any rewriter

### Rewrite before retrieval (R3, R4)

- [x] **RWR-01** (R3): A new `rag/query/rewrite.py` runs in or before `DocumentService._retrieve` (`rag/api/service.py:441`), before `RetrievalPipeline.run`; given the latest message and the last N turns it returns one standalone question that keeps the user's constraints, or the message unchanged when it is already standalone (cheap deterministic check first, model second; no model call on the first turn)
- [x] **RWR-02** (R3): Retrieval runs fresh on the rewritten question; the trace records both the original and the rewritten text; a rewrite failure falls back to the original message (fail-open) and is visible as `rewrite.status="fallback"` in the trace; errors outside the rewrite still surface as an HTTP status before any SSE byte is sent (D2 decided at gate 1, 2026-10-24)
- [x] **RWR-03** (R4): When two readings of a follow-up are equally plausible the system returns one clarifying question instead of guessing, through the normal response and SSE contract, and never two clarifications in a row
- [x] **RWR-04** (R4): A detected topic switch starts a clean history for the rewrite; the four named failure modes have tests with a deliberately bad fake rewrite: invented details, dropped constraints, wrong pronoun resolution, an earlier topic leaking into a new question

### Prompt, trust and budget (R5, R6, R7)

- [x] **PRMT-01** (R5): `build_prompts` (`rag/query/generate.py:51`) gains an optional history block of the last N turns holding questions and short answers, not full earlier answers; `SYSTEM_PROMPT` and `DOCUMENT_SYSTEM_PROMPT` are not changed
- [x] **PRMT-02** (R5): With no history the produced prompt is byte-identical to today's, so golden results and the LLM cache are unaffected (test: prompt equality on the golden set, snapshot committed before the first edit)
- [x] **PRMT-03** (R6): Stored turns go through `scan_text` and are shown and reused only after `filter_output`-style defanging (`rag/query/guard.py`), with stale `[S n]` citation markers stripped; the page renders history with `textContent`; streamed answers still go only through `StreamGuard`
- [x] **PRMT-04** (R7): History plus passages plus answer budget (including the reasoning model's 3000 thinking tokens, `docs/models.md`) fits the context window; a hard cap on turns/words per conversation is enforced before any model call with a clear error to the client; compaction is deferred (constants are open decision D3, pinned after the server's `max_model_len` is recorded)

### Evaluation (R8)

- [ ] **EVAL-01** (R8): A multi-turn golden set under `data/golden/` with at least a pronoun follow-up, a topic switch, an ambiguous follow-up and a standalone question inside a conversation, each with the human-written standalone question and PDF gold pages, loaded by its own loader (`load_golden` rejects unknown keys)
- [ ] **EVAL-02** (R8): An experiment under `rag/experiments/` scores retrieval on the rewritten query and the answer on the last turn, with rewriting on and off (and an oracle arm using the human standalone question), using identical teacher-forced histories per arm and the per-question fact checklist judge
- [ ] **EVAL-03** (R8): Rewriting ships on by default only if it shows a gain outside the noise band recomputed for the set's size; otherwise it ships off with the numbers recorded in the repo; the shipping rule is written down before the first run

### Chat page (R9)

- [ ] **PAGE-01** (R9): `rag/api/static/index.html` keeps the conversation id across questions, resets it on "new conversation" or a change of selected documents, and handles a stale id (404) by starting a new conversation
- [ ] **PAGE-02** (R9): The clarifying question (RWR-03) is shown as an ordinary assistant turn, rendered with `textContent`

### Docs and notes (R10)

- [ ] **DOCS-01** (R10): `rag/README.md` gains a Step 11 for chat memory; `docs/backlog.md` marks the item done and adds compaction and conversation retention; `interview/05_conversation_memory_and_cost.md` is relabelled from "designed" to "built" only for what is built and measured, with the recorded numbers

## v2 Requirements

Deferred to a later milestone. Tracked but not in the current roadmap ("Later (roadmap, not this run)" in the requirements document, plus research-recommended additions).

### Memory and cost (from the requirements document)

- **MEM-01**: Compaction of long histories (rolling summary at about 70% of the history budget)
- **COST-01**: Cost and token totals per request
- **COST-02**: Tracing (Langfuse or LangSmith); self-hosting decision first because traces hold document text
- **COST-03**: Tool calling (after tracing, per the owner's planned order in `docs/backlog.md`)

### Platform (from the requirements document)

- **PLAT-01**: Keycloak replacing `current_owner`
- **PLAT-02**: The API in Docker

### UI, API and extraction backlog (from the requirements document)

- **BKLG-01**: Stop button
- **BKLG-02**: Streaming for the about path
- **BKLG-03**: Tables, images, OCR
- **BKLG-04**: HNSW measurement
- **BKLG-05**: Automatic routing to the about path
- **BKLG-06**: The remaining `docs/backlog.md` items

### Research-recommended additions (not in the requirements document; `.planning/research/FEATURES.md`)

- **CONV-05**: `GET` for one conversation so a page reload resumes the history
- **CONV-06**: Explicit delete of a single conversation
- **CONV-07**: Per-turn citations (document, PDF page, chunk id) stored with each turn
- **CONV-08**: Rewritten question shown in the page's "what the pipeline saw" panel

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Any change to `SYSTEM_PROMPT` or `DOCUMENT_SYSTEM_PROMPT` wording | The golden-set results and the LLM cache depend on them word for word (`CLAUDE.md`); history enters the user prompt as an optional block instead |
| LangChain or LangGraph | Plain-Python orchestration by design (`rag/README.md` "Design decisions"); no new framework |
| Client-supplied history | The client sends only the new message and the conversation id; client-sent history is user-controlled and cannot be trusted (`interview/05_conversation_memory_and_cost.md`) |
| Vector or semantic memory stores (Mem0, Zep, Letta), SQLite or Redis for history | A per-conversation file under the document folder is enough for the cap this milestone enforces and is removed by the existing delete (`.planning/research/STACK.md`) |
| Summariser or rolling-summary model | Compaction is deferred (MEM-01); a hard cap replaces it in this milestone |
| Tokenizer package for budgeting | Word budget with a calibrated tokens-per-word factor avoids a new dependency (`.planning/research/STACK.md`) |
| LLM disk cache for anything derived from uploads | A delete must remove all derived text; `get_llm(spec, cache_dir=None)` stays |
| Conversation list sidebar, auto titles, suggested follow-ups, export, branching, cross-conversation memory | Differentiators not in the requirements document; deferred (`.planning/research/FEATURES.md`) |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CONV-01 | Phase 2 | Complete |
| CONV-02 | Phase 2 | Complete |
| CONV-03 | Phase 2 | Complete |
| CONV-04 | Phase 2 | Complete |
| RWR-01 | Phase 3 | Complete |
| RWR-02 | Phase 3 | Complete |
| RWR-03 | Phase 3 | Complete |
| RWR-04 | Phase 3 | Complete |
| PRMT-01 | Phase 2 | Complete |
| PRMT-02 | Phase 1 | Complete |
| PRMT-03 | Phase 2 | Complete |
| PRMT-04 | Phase 2 | Complete |
| EVAL-01 | Phase 4 | Pending |
| EVAL-02 | Phase 4 | Pending |
| EVAL-03 | Phase 4 | Pending |
| PAGE-01 | Phase 5 | Pending |
| PAGE-02 | Phase 5 | Pending |
| DOCS-01 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0

---
*Requirements defined: 2026-10-21*
*Last updated: 2026-10-21 after roadmap creation (traceability filled)*
