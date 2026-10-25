# Backlog

Open items that are not built yet, with the reason each matters. Newest first inside each group.

## UI and API

- **Chat memory: done** (2026-10-26). Built: server-side conversations per owner behind `conversation_id` on every ask route (stored in the document's folder or the owner's conversations folder, removed when a document they touched is deleted), the history block in the answer prompt treated as untrusted text, the turn and word caps with a 409, the rewrite step behind `RAG_REWRITE` with one clarifying question and topic-switch detection, and the page keeping and resetting the id. Rewriting is measured and the decision is: ships off (failed: a, c, f; provisional: items pending human review). See `rag/README.md` Step 11, `docs/chat_memory_eval.md` and `interview/05_conversation_memory_and_cost.md`. Still open: the four items below (compaction, a reload-resume GET, the rewrite shown in the pipeline panel, a turn counter).
- **Compaction of long histories.** A rolling summary when the history passes about 70% of its budget. Today the window of recent turns and the hard cap stand in for it, and a full conversation is refused with a 409.
- **A reload-resume `GET` for one conversation**, so a page reload shows the history; the page keeps the id in memory only, so a reload starts a new conversation.
- **The rewritten question and the rewrite `fallback` flag** shown in the page's "What the pipeline saw" panel; the page ignores `rewrite` today.
- **A turn counter** and a warning before the cap is reached.
- **Cost and observability.** Per-question token counts and stage timings are recorded in the trace; there is no price table, no totals per owner, no time to first token, and no tracing tool. Planned order, set by the owner on 2026-10-10: finish the working chatbot, then observability (Langfuse or LangSmith, possibly as the next project), then tool calling. Decide self-hosting before sending prompts anywhere, because a trace holds the user's document text.

- **Streaming answers: done** (2026-10-10). `POST /v1/ask/stream` and `POST /v1/documents/{id}/ask/stream` return server-sent events. The model client's `generate_stream` (`rag/common/llm.py`) yields answer text only, keeps the thinking for debugging and never sends it, and closes the connection when the reader goes away so the model stops. `StreamGuard` (`rag/query/guard.py`) holds back anything that could be the start of a risky piece (an image or link, a tag, an entity, the canary, system-prompt text) until it is judged, so a blocked answer has not already leaked it; the whole-answer check still runs at the end and the page replaces the text if it fails. Design and reasons: `interview/04_system_design_and_streaming.md`, section 8. Still open: a Stop button, streaming for the "about the documents" path (it answers in one piece), and a percentage inside the embedding stage of an upload.
- **Duplicate uploads: done** for new uploads (same owner, same sha256 returns the existing document). Still open: uploads made before the hash existed are not recognised, and a caller-supplied `external_id` for a scraper (see `docs/auth_plan.md`).
- **Readable folder names.** Folders are a random id (`data/uploads/<id>/`); only the UI shows the real name.
- **Chat across several documents: done** (`POST /v1/ask`, one, several or all of the caller's documents). Cross-document questions are not saved as traces; decide how to keep them with a retention rule (see Security).
- **Upload progress: done** as a stage name (extracting, chunking, embedding) in `status.json` shown on the page. A percentage inside the embedding stage is not built.

## Security (see `docs/auth_plan.md`, `docs/mcp_risks.md`)

- Owner on every document and chunk is **done** and tested against both stores (a second user gets 404 for everything of the first user's, and never receives their passages). Still open: the owner comes from one placeholder function, `current_owner` in `rag/api/main.py`, that returns the single local user until Keycloak replaces it.
- Keycloak token validation; per-client identities for the page, a scraper and an MCP server.
- Retention for traces in `data/uploads/<id>/chat/` of documents that are not deleted.
- Conversation retention: a time limit for conversation files of documents that are never deleted, for cross-document conversations under the owner's `_conversations` folder (`data/uploads/_conversations/`), for conversations left behind by New conversation or a change of documents (there is no per-conversation delete), and for the one-turn conversation files that page questions created before the page sent an id.

## Retrieval and evaluation

- Approximate (HNSW) search in OpenSearch was not measured; only exact search was compared with the in-memory store.
- [x] OpenSearch keyword search beat our in-memory BM25 by about 8 points on hit@5. Tested: optional stemming in `rag/common/bm25.py` recovers about two thirds of it (+5.4 points) and all of the MRR gain; off by default. See `rag/README.md` Step 9.
- Citation support and answer relevance checks in `rag/observe/generation_quality/`.
- [x] Query rewriting for follow-ups: built behind `RAG_REWRITE` and measured on the multi-turn golden set (`data/golden/ddia_conversations.jsonl`); the decision in `docs/chat_memory_eval.md` is: ships off (failed: a, c, f; provisional: items pending human review).
- Intent classification: only add it if the golden set shows a gain.
- Documents with images, tables and scans: the `Element` contract and OCR handlers (Stage 4 of the reorganisation plan).

## Running it

- WSL shuts down when nothing is attached, which stops OpenSearch. A background `wsl ... sleep` keeps it alive for now; a permanent fix means changing the WSL idle setting.
- The API runs on Windows because the model tunnel, the GPU and the files are there. Running it in a container needs the tunnel reachable from Docker.
- `docker-compose.yml` has the OpenSearch security plugin off; it is bound to `127.0.0.1` only. Enable security before anything else can reach it.

## From the code review of the extraction limits (not fixed)

- [x] **Stemming is a global switch.** Done: `MemoryChunkStore(stem=False)` (and `from_chunkset`, `copy`) and `RetrievalPipeline.from_chunkset(..., stem=False)` pass it to every `BM25Index`; `--bm25-stem` sets it on the pipelines it builds, and `DEFAULT_STEM` is gone.
- [x] **Windows job handles.** Done: `_WindowsJob` in `rag/ingestion/sandbox.py` owns the handle (context manager, one `kernel32` setup with `argtypes`); the module-level dict and `_release_job` are gone.
- **`max_page_chars` bounds the output, not the work.** `page.get_text("dict")` has already built the whole page when the cut is made, and margin blocks use the same budget. The time and memory limits are the real protection.
- **The sandbox has only run on Windows.** On Linux and macOS the child sets `RLIMIT_AS` itself; if the system refuses, extraction fails with a message that says so. Run its tests on Linux before deploying there.

## Questions about the documents themselves (found in the UI, 2026-10-10)

- **"When should one use the definitive guide and when the reference guide?"** across two HBase books gave "I cannot answer this from the provided document", with passages about typographical conventions and transactions. The abstention is honest: no passage says how the two books differ, because that is a fact about the books, not in either book. Retrieval over text chunks cannot answer questions of this kind (compare two documents, what is this document for, who is it for, which one covers X).
- **Done 2026-10-10 as option 1, but kept out of the index** (see `docs/about_the_documents.md`): a profile per document and a separate `POST /v1/ask-about` that the user picks on the page. Still open: the 4 to 6 golden questions of this kind, and automatic routing.
- Options considered, cheapest first: (1) a short **document profile** written at ingestion (title, scope, audience, table of contents) and indexed as its own chunk with `kind: profile`, so such questions retrieve it; (2) for a comparison question over several documents, retrieve **per document** and answer from each side's passages; (3) intent routing, which is the LangGraph case in `rag/README.md`. Do (1) first and measure with 4 to 6 new golden questions of this kind before building the rest.
- Until then the abstention message could say what the system can do, for example "I can answer questions about what the documents contain; this asks about the documents themselves".
