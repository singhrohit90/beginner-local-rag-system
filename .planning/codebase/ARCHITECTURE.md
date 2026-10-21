---
last_mapped_commit: a53a2e9a053a09e28fd2a5cbe11629a8ded7d112
last_mapped_at: 2026-10-21
---
<!-- refreshed: 2026-10-21 -->

# Architecture

**Analysis Date:** 2026-10-21

## System Overview

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                     HTTP API and chat page (rag/api)                      │
│  main.py (routes, Origin/Host checks)  ->  service.py (DocumentService)   │
│  static/index.html (UI, textContent only)                                  │
└───────────────┬───────────────────────────────────────┬──────────────────┘
                │ upload / ingest (background)           │ ask / ask-stream
                ▼                                        ▼
┌──────────────────────────────┐        ┌─────────────────────────────────────┐
│ INGESTION (rag/ingestion)    │        │ QUERY (rag/query)                    │
│ pipeline.py orchestrates:    │        │ pipeline.py: RetrievalPipeline,      │
│  extract.py  (PDF -> pages)  │        │   RagPipeline                        │
│  chunk.py    (chunking/)     │ writes │  retrieve -> fusion -> rerank ->     │
│  index.py    (embed + store) │ ─────> │  select_context -> generate -> guard │
└──────────────────────────────┘ chunk  └──────────────┬──────────────────────┘
                                 store                 │ Trace
                                                       ▼
                ┌──────────────────────────────────────────────────────────┐
                │ rag/common: ChunkStore (memory or OpenSearch), Embedder,  │
                │ LLM providers, Trace, types, config                      │
                └──────────────────────────────────────────────────────────┘
                                                       │
                                                       ▼
                ┌──────────────────────────────────────────────────────────┐
                │ OBSERVE (rag/observe): retrieval_quality, generation_quality,│
                │ golden set; reads traces, never sits in the request path  │
                └──────────────────────────────────────────────────────────┘
```

## Pattern Overview

**Overall:** Two linear pipelines joined only by a shared chunk store, with an observability layer that scores recorded traces. Each pipeline is a short orchestrator that calls single-purpose step modules in a fixed order. There is no framework (no LangChain or LangGraph); the design is documented in `rag/README.md` ("Design decisions").

**Key Characteristics:**
- Orchestrators only choose order and skip stages; logic lives in step modules (for example `rag/query/fusion.py`, `rag/query/select_context.py`).
- The ingestion pipeline and the query pipeline share no code paths except `rag/common/` types and the chunk store. The chunk store is "the only link" (`rag/README.md`, diagram).
- Every query writes a `Trace` (`rag/common/trace.py`). Each stage records its hits, so evaluation can attribute a wrong answer to a stage.
- Stages are switched by named configs (`rag/query/configs.py`, `RetrievalConfig`). A disabled stage leaves no trace entry.
- Storage is pluggable behind one interface: `ChunkStore` (`rag/common/chunk_store.py`) with `MemoryChunkStore` and `OpenSearchChunkStore` (`rag/common/opensearch_store.py`). Selected by `RAG_STORE` (`memory` default, or `opensearch`).
- Multi-tenancy is enforced in the store: every read takes a `Scope` (owner plus optional document ids) and the filter is applied inside the query, not after it (`rag/common/chunk_store.py` docstring).

## Layers

**Common (shared types, config, adapters):**
- Purpose: Data objects and infrastructure that both pipelines use.
- Location: `rag/common/`
- Contains: `types.py` (`Page`, `Chunk`, `Hit`), `trace.py` (`Trace`), `config.py` (paths and extraction thresholds), `chunk_store.py`, `opensearch_store.py`, `store.py` (numpy vectors, exact cosine search), `bm25.py`, `stem.py`, `embed.py`, `llm.py` (model providers), `llm_check.py`, `secrets.py`, `log.py`.
- Depends on: standard library, numpy, optional provider SDKs.
- Used by: ingestion, query, observe, api, experiments.

**Ingestion:**
- Purpose: Turn an uploaded or local PDF into cleaned pages, a chunk set, and a vector index.
- Location: `rag/ingestion/`
- Contains: `pipeline.py` (orchestrator `ingest()`), `extract.py` (pages and PDF bookmarks), `clean.py` (header/footer removal), `chunk.py` (strategy picker), `chunking/` (five strategies plus `base.py`, `units.py`, `document.py`, `build.py`, `stats.py`), `index.py` (embed and cache vectors), `profile.py` (document profile for "about the documents"), `sandbox.py` (child-process extraction with time and memory limits), `export_text.py`.
- Depends on: `rag/common/` (embed, store, config, types).
- Used by: `rag/api/service.py` (uploads), experiments, CLI.

**Query:**
- Purpose: Answer a question from the indexed chunks, with guards on untrusted text.
- Location: `rag/query/`
- Contains: `pipeline.py` (`RetrievalPipeline`, `RagPipeline`), `retrieve.py` (`dense_search`, `keyword_search`), `fusion.py` (RRF and weighted min-max), `rerank.py` (cross-encoder, optional), `select_context.py` (dedupe, parents, word budget), `generate.py` (prompt building, citation parsing, abstention detection), `prompt.py` (`SYSTEM_PROMPT`, `DOCUMENT_SYSTEM_PROMPT`), `guard.py` (`scan_chunks`, `filter_output`, `StreamGuard`), `configs.py` (named configs), `about.py` (answers about documents from their profiles).
- Depends on: `rag/common/`, and `rag/ingestion/chunking/base.py` (`ChunkSet` type).
- Used by: `rag/api/service.py`, `rag/experiments/`, `rag/observe/`.

**Observe (evaluation):**
- Purpose: Score traces and answers; never called on the request path.
- Location: `rag/observe/`
- Contains: `golden.py` (question loader), `retrieval_quality/` (`metrics.py`, `run_eval.py`, `diagnose.py`), `generation_quality/` (`judge.py`, `answers.py`, `calibrate_judge.py`), `golden_tools/` (question-writing helpers).
- Depends on: `rag/query/`, `rag/common/trace.py`.
- Used by: `rag/experiments/`, tests.

**Security:**
- Purpose: Poisoned fixtures and the injection test harness.
- Location: `rag/security/` (`fixtures.py`, `defenses.py`, `indirect.py`).
- Depends on: `rag/query/`. Used by: a CLI run only; the guards that run in production live in `rag/query/guard.py`.

**API (web):**
- Purpose: HTTP surface and the chat page. Routes only; behaviour lives in service code.
- Location: `rag/api/`
- Contains: `main.py` (FastAPI app factory `create_app`, routes, request models, `current_owner`, `LimitUploadBody`), `service.py` (`DocumentService`), `static/index.html`.
- Depends on: `rag/ingestion`, `rag/query`, `rag/common`.
- Used by: uvicorn, the browser.

**Experiments:**
- Purpose: Scripts that run a full comparison and print a table.
- Location: `rag/experiments/` (`retrieval.py`, `answer.py`, `about.py`).
- Depends on: all of the above.

## Data Flow

### Ingestion Path (CLI or upload)

1. `rag/ingestion/pipeline.py` `ingest()` extracts pages and bookmarks to `<out_dir>/<stem>.pages.jsonl` and `<stem>.toc.json` (`rag/ingestion/extract.py`). API uploads pass an `extractor` that runs in a child process (`rag/ingestion/sandbox.py`).
2. `Document.from_files` loads the pages, `make_chunker(name).chunk(document)` produces a `ChunkSet`, saved under `chunks/<strategy>.jsonl` (`rag/ingestion/chunk.py`, `rag/ingestion/chunking/`).
3. `get_index()` / `index_document()` (`rag/ingestion/index.py`) embeds chunks and writes vectors (cached on disk, rebuilt only when chunks change).
4. Upload-specific: `rag/ingestion/profile.py` writes a document profile; `DocumentService` writes `status.json` with states `queued`, `processing`, `ready`, `failed`.

### Primary Query Request Path

1. `POST /v1/documents/{id}/ask` or `POST /v1/ask` in `rag/api/main.py`. The owner comes only from `current_owner()`.
2. `DocumentService` (`rag/api/service.py`) builds a `Scope` and calls `RagPipeline.run()` (`rag/query/pipeline.py`).
3. `RetrievalPipeline.run()` calls `dense_search` (`rag/query/retrieve.py`, embedding the question) and/or `keyword_search`, each recorded as a trace stage (`dense`, `bm25`).
4. `fusion.rrf` or `fusion.weighted` merges the two lists (stage `fuse`). Optional `Reranker.score` (stage `rerank`) when the config enables it.
5. Parents are fetched for `parent_child` chunks when `use_parents` is set. `select_context` dedupes, applies the scanner, the per-source cap, and the word budget (stage `context`).
6. `RagPipeline.answer()` calls `answer_from_context` (`rag/query/generate.py`) with the prompt from `rag/query/prompt.py`, then `filter_output` (`rag/query/guard.py`) when the output filter is on.
7. The answer, citations (`[S n]`), usage, and prompt are written into the same `Trace`, which the service saves under `data/uploads/<doc_id>/chat/` (uploads) or `runs/` (experiments).

### Streaming Path

1. `POST /v1/ask/stream` and `POST /v1/documents/{id}/ask/stream` call `RagPipeline.stream()`.
2. Tokens from `stream_answer` pass through `StreamGuard` (`rag/query/guard.py`) before being yielded. Held-back text is released only when judged safe.
3. A final `("final", replace)` event carries the checked answer. The API sends server-sent events (`event: token`, `event: final`, `event: error`); closing the connection closes the model stream.

### Ask-About-Documents Path

1. `POST /v1/ask-about` calls `answer_about` (`rag/query/about.py`), which reads document profiles instead of passages. The main query pipeline and its prompt are not used.

**State Management:**
- Per-document state is files on disk: `data/uploads/<doc_id>/` holds `source.pdf`, `status.json`, `pages.jsonl`, `toc.json`, `chunks/`, `index/`, `chat/`. `DocumentService` guards writes with locks (`_status_lock`, `_load_lock`, `_create_lock`, `_ingest_lock`) and atomic file replacement.
- Vectors and chunks live in memory (`MemoryChunkStore`, rebuilt from `data/uploads/` at startup) or in OpenSearch (`RAG_STORE=opensearch`, indexes `rag_c_*`, `rag_p_*` per owner).

## Key Abstractions

**`ChunkStore` (interface):**
- Purpose: Read and write chunks and vectors for a given owner and scope.
- Examples: `rag/common/chunk_store.py` (`MemoryChunkStore`), `rag/common/opensearch_store.py` (`OpenSearchChunkStore`).
- Pattern: Strategy/adapter. `tests/test_chunk_store.py` runs the same checks against both implementations.

**`Scope`:**
- Purpose: Owner plus optional document ids, required on every read.
- Examples: `rag/common/chunk_store.py`.
- Pattern: Filter passed into the store; enforced inside the query.

**`ChunkSet` and chunker strategies:**
- Purpose: Output of ingestion step 2; a list of `Chunk` with page ranges and metadata.
- Examples: `rag/ingestion/chunking/base.py`, `recursive.py`, `fixed.py`, `heading.py`, `parent_child.py`, `semantic.py`, `document.py`.
- Pattern: Strategy chosen by name via `make_chunker()` in `rag/ingestion/chunk.py`; valid names are `fixed`, `recursive`, `heading`, `parent_child`, `semantic`.

**`RetrievalConfig`:**
- Purpose: Named switches and parameters for one retrieval run (dense, bm25, fusion method, weights, rerank, top_k, word budget, scanner, per-source cap).
- Examples: `rag/query/configs.py` (`CONFIGS` dict). The API offers only configs that do not need a reranker (`USABLE_CONFIGS` in `rag/api/main.py`).

**`Trace` and `Hit`:**
- Purpose: The record of what each stage returned, and the unit of a retrieved passage (`rag/common/types.py`).
- Pattern: Each stage calls `trace.record(name, kind, hits)` with `kind` either `retrieve` or `transform`.

**`LLM` and `Embedder`:**
- Purpose: Model providers behind one call interface (`generate`, streaming via `stream_answer`); embedders for `st:` (sentence-transformers) and other specs.
- Examples: `rag/common/llm.py`, `rag/common/embed.py`. Chosen by spec string such as `gemini:<model>`, `ollama:<model>`, `fake`.
- Pattern: Factory by string spec (`get_llm`, `get_embedder`).

**`Reranker`:**
- Purpose: Cross-encoder rescoring of the fused list.
- Examples: `rag/query/rerank.py`. Not loaded by the API service (`build_default_service` in `rag/api/main.py`), so rerank configs are unavailable there.

## Entry Points

**Web API:**
- Location: `rag/api/main.py` (`create_app`, `app` for uvicorn `rag.api.main:app`).
- Triggers: `uvicorn rag.api.main:app --port 18642` (`RAG_STORE=opensearch` for the vector database).
- Responsibilities: routes under `/v1`, Host allowlist (`TrustedHostMiddleware`), Origin check on state-changing requests, upload size limit.

**Ingestion CLI:**
- Location: `rag/ingestion/pipeline.py` (`main`, run as `python -m rag.ingestion.pipeline`).
- Triggers: manual run on `data/raw/*.pdf`.
- Responsibilities: extract, chunk, and index one PDF end to end.

**Step modules (CLI):**
- `rag/ingestion/extract.py`, `rag/ingestion/chunking/build.py`, `rag/observe/golden_tools/find_pages.py`, `rag/common/llm_check.py`.

**Experiments:**
- `rag/experiments/retrieval.py` (retrieval table), `rag/experiments/answer.py` (answer scoring), `rag/experiments/about.py`.

**Security tests:**
- `rag/security/indirect.py` (`python -m rag.security.indirect`).

## Architectural Constraints

- **Threading:** The API runs FastAPI with a threadpool for blocking work (`run_in_threadpool`, `iterate_in_threadpool`). Ingestion runs in background threads and is serialised by `_ingest_lock` because the embedder shares the GPU (`rag/api/service.py`). Streaming uses worker threads; `_close_when_idle` in `rag/api/main.py` waits for a running generator before closing it.
- **Global state:** `DocumentService` holds the in-memory store and locks as instance state (`rag/api/service.py`). `MemoryChunkStore` is process-local, so the memory store is not shared across server processes. Module-level constants in `rag/common/config.py` (paths, extraction thresholds).
- **Circular imports:** None observed in the modules read. `rag/query/pipeline.py` imports `rag.ingestion.chunking.base` for `ChunkSet` only, so query depends on ingestion's type module.
- **Owner identity:** `current_owner()` in `rag/api/main.py` is the only source of the caller. It returns `LOCAL_OWNER` until authentication is added (`docs/auth_plan.md`).
- **Extraction isolation:** API uploads extract in a child process with time and memory limits (`rag/ingestion/sandbox.py`). Windows Job Object path is the one exercised so far.
- **Prompt stability:** `SYSTEM_PROMPT` in `rag/query/prompt.py` must not change; golden-set results and the LLM cache depend on it (`CLAUDE.md`).

## Anti-Patterns

### Using the LLM disk cache for uploads

**What happens:** Uploaded-document answers could be cached on disk through the LLM provider's cache directory.
**Why it's wrong:** Deleting the document would not remove the cached text.
**Do this instead:** Call `get_llm(spec, cache_dir=None)` for uploads, as `rag/api/service.py` and the API path already do (`CLAUDE.md`, `rag/README.md` Step 8).

### Trusting the keyword scanner as the only defence

**What happens:** `scan_chunks` in `rag/query/guard.py` is a rule list that removes instruction-like passages.
**Why it's wrong:** A rule list is easy to bypass; `rag/README.md` (Step 7) says the scanner is one layer only.
**Do this instead:** Keep the output filter (`filter_output`) and the per-source cap on, and add checks in the same layer as the existing ones rather than replacing them.

### Streaming text without the guard

**What happens:** Yielding raw model tokens directly to the client.
**Why it's wrong:** Text already sent cannot be recalled (`rag/README.md` Step 8).
**Do this instead:** Route every streamed token through `StreamGuard` in `RagPipeline.stream()` (`rag/query/pipeline.py`).

### Reading the owner from the request

**What happens:** Taking the caller from a header or body field.
**Why it's wrong:** A caller could read another owner's documents.
**Do this instead:** Use `Depends(current_owner)` or the call to `current_owner()` in `rag/api/main.py`; return 404 for another owner's document.

## Error Handling

**Strategy:** Typed service exceptions mapped to HTTP codes in the route layer; ingestion failures recorded in `status.json`.

**Patterns:**
- `NotFound`, `BadUpload`, `TooLarge` in `rag/api/service.py`; mapped to 404, 400, and 413 in `rag/api/main.py`. Another owner's document is 404.
- Model failure during ask returns 502 with the reason (`rag/README.md` Step 8). A failure during streaming sends an `error` event.
- Startup recovery: documents left `queued` or `processing` are marked `failed` with "interrupted by a server restart" (`_recover_interrupted` in `rag/api/service.py`).
- Ingestion with no extractable text raises `ValueError` (`rag/ingestion/pipeline.py`).

## Cross-Cutting Concerns

**Logging:** `setup_logging()` from `rag/common/log.py`; module loggers named `rag.ingestion`, `rag.api`.
**Validation:** Document ids must match `^[0-9a-f]{12}$` (`DOC_ID` in `rag/api/service.py`) before they become a path. Upload size is limited by `LimitUploadBody` (`rag/api/main.py`) and by page count (`DEFAULT_MAX_PAGES`).
**Authentication:** None yet. `current_owner()` returns the local owner; `docs/auth_plan.md` describes the planned replacement. Host and Origin checks guard the browser path.

---

*Architecture analysis: 2026-10-21*
