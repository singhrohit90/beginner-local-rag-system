<!-- GSD:project-start source:PROJECT.md -->

## Project

**Local RAG System: Chat Memory**

A local, production-style retrieval-augmented generation (RAG) system built to learn by measuring: evaluation and security first, plain-Python orchestration, every answer traceable to the stage that produced it. It ingests PDFs, retrieves with hybrid dense + BM25 search, answers through a guarded LLM path, and serves a chat page and a `/v1` API for a single local owner.

This milestone adds **chat memory**. Today the chat page and the `/v1/ask*` API treat every question as standalone. After this work a user can ask a follow-up ("and how does that compare to the other book?") and get an answer that uses the conversation so far, without the pipeline's single-turn behaviour, scores or prompt changing.

**Core Value:** A follow-up question with a pronoun retrieves the passages the standalone phrasing would, while a single-turn question produces exactly the prompt bytes and cached answer it produces today.

### Constraints

- **Prompt stability**: `SYSTEM_PROMPT` in `rag/query/prompt.py` word for word; single-turn prompts byte-identical to today — golden results and the LLM cache depend on it
- **Retrieval invariant**: hit@5 0.865, mrr 0.663 on `--chunkers semantic --configs weighted` unchanged — proves the refactor did not touch single-turn retrieval
- **Security conventions** (`CLAUDE.md`): caller only from `current_owner`; 404 not 403 for another owner's resource; filter by `Scope.owner` inside the store; `textContent` never `innerHTML`; chunk ids `<doc_id>:<chunk_id>`; answers stream only through `StreamGuard`
- **No LLM disk cache for uploads**: `get_llm(spec, cache_dir=None)` stays — a delete must remove all derived text
- **Deletable storage**: conversation history must live where a document delete removes it — retention of document text is a stated security concern
- **Tech stack**: plain Python orchestration, no new framework; FastAPI + vanilla HTML page; pytest
- **Evaluation discipline**: use the per-question fact checklist and strict evidence-aware relevance; do not retry the holistic correctness judge or page-overlap-only relevance (unreliable); gaps under about 8 points are noise; rewriting ships on only if it shows a gain outside the noise band
- **Environment**: Windows 11, Git Bash; model server through a PuTTY tunnel; OpenSearch in WSL Docker (tests skip when it is down); multiprocessing scripts run from a file with `if __name__ == "__main__"`
- **Working rules**: commit messages via `git commit -F <file>`; prove a regression test fails on the old code (`git stash push -q -m <tag> -- rag`); Edit tool for backslash-heavy text; never name `rag/common/llm.py` or `tests/test_vllm.py` in a shell command; never read `.env`; timing-sensitive tests wait on a condition, not a fixed sleep
- **Branching**: the flow run owns the `flow/chat-memory` branch; no phase or milestone branches; no pushes or pull requests unless asked

<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->

## Technology Stack

## Languages

- Python 3.10 (observed: `__pycache__` contains `cpython-310` bytecode; no `pyproject.toml`, `setup.py` or `.python-version` pins a version) - all pipeline, API, experiment and test code under `rag/` and `tests/`
- HTML/CSS/JavaScript (vanilla, no build step) - chat page `rag/api/static/index.html`
- Markdown and JSON Lines - golden question set `data/golden/ddia_questions.jsonl`, `data/golden/about_questions.jsonl`; document/chunk outputs under `data/processed/`

## Runtime

- CPython 3.10 on Windows 11 (developer machine). Code is also written to run on Linux and macOS: `rag/ingestion/sandbox.py` switches between a Windows Job Object (via `ctypes`) and `RLIMIT_AS` on other platforms.
- Optional GPU for local embeddings and the cross-encoder (CUDA via `torch`, pulled in by `sentence-transformers`); CPU works.
- WSL2 Ubuntu-24.04 hosts Docker for OpenSearch (`docker-compose.yml`).
- pip. Dependencies are listed in `requirements-rag.txt` (no version lock file; no `requirements.lock`, `poetry.lock` or `uv.lock` present).
- Lockfile: missing

## Frameworks

- FastAPI `>=0.110` - web API and static page serving, `rag/api/main.py`
- Starlette (transitive via FastAPI) - `TrustedHostMiddleware` host allowlist, `StreamingResponse` for streamed answers
- Uvicorn `>=0.29` - ASGI server; run as `uvicorn rag.api.main:app` (the project's documented port is 18642, see `CLAUDE.md`)
- Pydantic (transitive via FastAPI) - request models in `rag/api/main.py`
- Plain Python orchestration for the RAG pipelines (no LangChain/LangGraph; decision recorded in `rag/README.md`)
- pytest `>=8` - test runner; tests in `tests/` (e.g. `tests/test_api.py`, `tests/test_stream_guard.py`, `tests/test_security.py`)
- httpx `>=0.27` - used by FastAPI's `TestClient` in API tests only
- No build tool, linter or formatter config detected (no `ruff`, `black`, `mypy` or `flake8` config files in the repository root)
- Python `-m` entry points for every stage (e.g. `python -m rag.ingestion.pipeline`, `python -m rag.experiments.retrieval`), documented in `rag/README.md`

## Key Dependencies

- `pymupdf` `>=1.24` (import name `pymupdf`) - PDF text extraction with bookmarks, `rag/ingestion/extract.py`, `rag/ingestion/sandbox.py`. Text layer only; no OCR or layout model (`docs/models.md`, `docs/extraction.md`).
- `numpy` `>=1.26` - vectors and exact cosine search, `rag/common/store.py`, `rag/common/bm25.py`, `rag/common/chunk_store.py`, `rag/common/embed.py`, `rag/ingestion/chunking/semantic.py`
- `sentence-transformers` `>=3` - local embedder (`all-mpnet-base-v2`, `rag/common/embed.py`), semantic chunker, and cross-encoder reranker (`cross-encoder/ms-marco-MiniLM-L-6-v2`, `rag/query/rerank.py`). Lazy-imported, so tests run without it. Pulls in `torch` and `transformers`.
- `opensearch-py` `>=2.4` - client for the vector database, `rag/common/opensearch_store.py`. Only needed when `RAG_STORE=opensearch`.
- `google-genai` - Gemini provider, lazy-imported inside `GeminiLLM` in `rag/common/llm.py`. Commented out in `requirements-rag.txt`; install only when using `gemini:` models. Not used in the default path (`docs/models.md`).
- `python-multipart` `>=0.0.9` - multipart form parsing for PDF uploads (`UploadFile` in `rag/api/main.py`)
- `anyio` (transitive) - `run_in_threadpool`/`iterate_in_threadpool` used by the API
- Standard library only for HTTP clients: `urllib.request`, `urllib.error`, `http.client` in `rag/common/llm.py` (no `requests` or `openai` package; the OpenAI-compatible and Ollama calls are hand-written JSON over HTTP)
- `hashlib`, `zlib` - cache keys and feature hashing (`rag/common/embed.py` `HashingEmbedder`, `rag/common/llm.py` `CachedLLM`)
- `opensearchproject/opensearch:2.17.1` - single-node vector and keyword store, defined in `docker-compose.yml` (project name `rag`)

## Model Runtimes (external to the Python env)

- On-prem vLLM server running `gpt-oss-20b` (reasoning model) - OpenAI-compatible `/v1/chat/completions`, reached through an SSH tunnel. Default `RAG_LLM` is `vllm:/models/gpt-oss-20b`. Client: `OpenAICompatLLM` in `rag/common/llm.py`. Defaults in code: `DEFAULT_REMOTE_URL = "http://127.22.10.1:30007/v1"`.
- Ollama (local) serving `qwen2.5:7b` as the judge - default `RAG_JUDGE` is `ollama:qwen2.5:7b`. Client: `OllamaLLM` in `rag/common/llm.py`, default host `http://localhost:11434`.
- Google Gemini API (hosted, optional, `gemini-3.5-flash-lite` in experiments) - `GeminiLLM` in `rag/common/llm.py`. Dropped from the default path because of the free-tier daily quota.
- Local models downloaded by sentence-transformers from Hugging Face on first use: `sentence-transformers/all-mpnet-base-v2` (embedder, 384-token limit), `cross-encoder/ms-marco-MiniLM-L-6-v2` (reranker, optional).

## Configuration

- Settings come from environment variables or a gitignored `.env` file at the repo root. `.env.example` is the committed template with no values.
- Helper that reads secrets: `rag/common/secrets.py` (environment first, then `.env`; documented as never logging or defaulting a key).
- Variables read in code:
- Tuning constants live in code, not env: `rag/common/config.py` (paths, `HEADER_FRACTION = 0.10`, `FOOTER_FRACTION`, `REPEAT_THRESHOLD = 0.2`).
- `data/raw/` - source PDFs (gitignored)
- `data/processed/` - extraction output, chunks, embedding index in `data/processed/index/`, LLM cache in `data/processed/llm_cache/` (gitignored)
- `data/uploads/<doc_id>/` - API uploads: `source.pdf`, `status.json`, `pages.jsonl`, `toc.json`, `chunks/`, `index/` (gitignored)
- `data/golden/` - committed golden question sets
- `runs/` - per-query traces and eval reports (gitignored)
- No build configuration. `requirements-rag.txt` is the only dependency declaration.
- `docker-compose.yml` - OpenSearch service only; publishes `127.0.0.1:9200` and disables the security plugin for development (not for shared networks).
- `.gitignore` - ignores `.env`, `.venv`, `data/raw/`, `data/processed/`, `data/uploads/`, `runs/`, `__pycache__/`, `.pytest_cache/`.

## Platform Requirements

- Python 3.10+ with `pip install -r requirements-rag.txt`; `pip install sentence-transformers` for the semantic chunker and embedder (pulls `torch`).
- Docker (in WSL2 on the developer machine) for OpenSearch when `RAG_STORE=opensearch`.
- An SSH tunnel (PuTTY) to the vLLM host for the default generator; Ollama on localhost for the judge.
- Tests run offline with `python -m pytest tests -q`; OpenSearch tests skip when the database is down.
- Not deployed. The API is for localhost only (`127.0.0.1`), with no authentication yet (`docs/auth_plan.md`).
- Target described in the docs: Keycloak-based authentication and an OpenSearch security-enabled cluster before any shared use.

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

## Naming Patterns

- Modules are short `snake_case` nouns or verbs naming one step: `rag/query/fusion.py`, `rag/query/select_context.py`, `rag/ingestion/clean.py`, `rag/observe/retrieval_quality/metrics.py`.
- Each pipeline stage is one module; the orchestrator only chooses order and what to skip: `rag/query/pipeline.py`, `rag/ingestion/pipeline.py`.
- Package folders carry an `__init__.py` (`rag/api/__init__.py`, `rag/query/__init__.py`, and so on). Tests are `tests/test_<area>.py` (`tests/test_stream_guard.py`, `tests/test_retrieval.py`). Test helpers that run in child processes live in a plain module, not in the test file: `tests/sandbox_targets.py`.
- Experiments and tools are run with `python -m`, so each has a `__main__` guard (14 modules, for example `rag/experiments/retrieval.py`).
- `snake_case`, verb-first: `dense_search`, `keyword_search`, `select_context`, `filter_output`, `load_chunkset`, `load_trace`.
- Private helpers start with a single underscore: `_close_when_idle` in `rag/api/main.py`, `_PROMPT_ECHO` in `rag/query/guard.py`, `_run_extract` in tests.
- Route handlers in `rag/api/main.py` are named for the action (`upload`, `ask`, and so on) and stay thin; the work goes through `DocumentService` in `rag/api/service.py`.
- `snake_case`. Module-level constants in `UPPER_SNAKE_CASE`: `DEFAULT_MAX_UPLOAD_BYTES`, `LOCAL_OWNER`, `STATES` in `rag/api/service.py`; `HEADER_FRACTION` in `rag/common/config.py`; `USABLE_CONFIGS` and `STATIC` in `rag/api/main.py`.
- Loop and math variables are short (`i`, `r`, `k`, `hits`, `scored`) when the scope is a few lines; anything that crosses a function boundary uses a full name (`chunk_id`, `page_start`, `owner`).
- The logger is always `logger = logging.getLogger("rag.<area>")` (see `rag/api/main.py`, `rag/api/service.py`).
- Dataclasses for records passed between stages: `Page`, `Chunk`, `Hit` in `rag/common/types.py`; `StageRecord`, `Trace` in `rag/common/trace.py`; `ChunkSet` in `rag/ingestion/chunking/base.py`. Use `@dataclass(frozen=True)` for value objects (`Scope` in `rag/common/chunk_store.py`, `units.py` in `rag/ingestion/chunking/units.py`, fixtures in `rag/security/fixtures.py`).
- Exception classes are named for the failure in one word and inherit from `Exception`: `NotFound`, `BadUpload`, `TooLarge(BadUpload)` in `rag/api/service.py`.
- Typing uses `typing` generics, not PEP 604 unions. Write `Optional[str]`, `List[Hit]`, `Dict[str, Any]`, as in `rag/common/types.py`. `from typing import ...` appears in 22 modules; `X | None` appears in none. Do not introduce `|` unions, to match.
- Pluggable parts are `typing.Protocol` or small classes with a `name` attribute, for example `RecursiveChunker.name = "recursive"` in `rag/ingestion/chunking/recursive.py` and `Embedder.name` read in `rag/query/pipeline.py`.

## Code Style

- No formatter configuration is committed (no `pyproject.toml`, `.editorconfig`, `setup.cfg`, or `ruff`/`black` config in the repo). Follow the existing layout by hand.
- Line length is loose: the longest line in `rag/` and `tests/` is 229 characters and 77 lines exceed 120. Keep new lines at or under 120 characters. Long string tables (`tests/test_stream_guard.py`, `rag/security/fixtures.py`) are the accepted exception.
- Multi-line calls put one argument per line with a trailing comma when the call wraps (see `RagPipeline` construction in `rag/query/pipeline.py`); short calls stay on one line. Some lines pack several keyword arguments with a hanging indent, as in `ContextConfig(...)` in `rag/query/pipeline.py`.
- Double quotes for strings; f-strings for messages (`f"unknown fusion {config.fusion!r}"`). Use `!r` in error messages to show the bad value.
- Blank lines: two between top-level definitions in modules, one between methods.
- No linter is configured or enforced in the repository. Keep imports used and the code free of unused variables; the existing code has no `# noqa` suppressions.
- Do not add `from __future__ import annotations` (0 modules use it).

## Import Organization

- None. Imports are always fully qualified from the package root `rag` (for example `from rag.query.configs import RetrievalConfig`). Relative imports are not used in `rag/` or `tests/`.
- `rag/ingestion/chunking/__init__.py` re-exports the strategies (`RecursiveChunker`, `ParentChildChunker`), and `tests/test_retrieval.py` imports from there. Import from the package `__init__` for chunkers; import from the defining module for everything else.

## Error Handling

- Configuration or input that is wrong at the call site raises `ValueError` with the bad value in the message: `raise ValueError(f"unknown fusion {config.fusion!r}")` in `rag/query/pipeline.py`. This is the most common raise in the code (28 sites).
- Missing runtime prerequisite raises `RuntimeError` (14 sites), for example a config that asks for a reranker that was not given.
- The API maps domain exceptions to HTTP status in the route, not in the service. `rag/api/main.py` converts `BadUpload` to 400, `TooLarge` to 413, `NotFound` to 404, and unknown chunker to 422 with `HTTPException(status, detail)`. The service layer in `rag/api/service.py` raises `NotFound`, `BadUpload`, `TooLarge` and never `HTTPException`.
- Return 404 for another owner's document, not 403 (CLAUDE.md security rule); the store filters by `Scope.owner`, so a missing and a foreign document take the same path.
- Catch the narrowest type that the call can raise: `except json.JSONDecodeError`, `except urllib.error.URLError as err`, `except (OSError, ValueError)`.
- `except Exception as err` appears 10 times. Use it only at a boundary that must not crash the caller (a background ingestion job, a judge call in an experiment) and log or record the error with the text of `err`, never silently.
- Do not swallow errors into `None` returns. Failure is either an exception or an explicit state (`STATES = ("queued", "processing", "ready", "failed")` in `rag/api/service.py`).
- Pipeline failures are recorded on the `Trace.error` field (`rag/common/trace.py`) so the observe layer can attribute them. Do not hide an error from the trace.

## Logging

- Use the module logger `logging.getLogger("rag.<area>")`; never call `logging.basicConfig` in a module.
- Use `print()` only in command-line entry points that write a table or report to stdout: `rag/experiments/retrieval.py`, `rag/observe/golden_tools/find_pages.py`, `rag/ingestion/chunking/build.py` (about 16 modules). Library and service code uses the logger.
- Log counts and decisions, not document text or answer text. Uploaded content and the canary string must not reach logs.

## Comments

- Module docstrings describe what the module does and how it fits the flow, in plain sentences; they are long and explanatory (`rag/query/pipeline.py`, `rag/api/main.py`).
- Comments explain *why* a choice was made, often with a pointer to the decision doc: see `# With one document in scope there is nothing to flood...` in `rag/query/pipeline.py`, and the `docs/auth_plan.md` reference in the `rag/api/main.py` docstring.
- Trailing comments give units and meaning on constants: `page_no: int  # 1-based PDF page index (NOT the printed page number)` in `rag/common/types.py`.
- Do not write comments that restate the code.
- Triple-double-quoted, one-line summary for simple functions (`"""Who is calling. There is no login yet..."""`), a short paragraph for classes that carry a design rule (`RecursiveChunker` in `rag/ingestion/chunking/recursive.py`).
- Private helpers may have no docstring.
- Type information is in the signature, not in docstrings. No `:param:` or Google-style sections are used.

## Function Design

- Keyword arguments with defaults for configuration (`RecursiveChunker(size=200, overlap=30, code_max=400)` in `rag/ingestion/chunking/recursive.py`; `RagPipeline(..., style="standard", output_filter=True, subject="book")`).
- Pass the `Scope` (owner plus document ids) explicitly into every store call; never rely on a global current owner in service code. The only owner source is `current_owner()` in `rag/api/main.py`.
- Return dataclasses (`Chunk`, `Trace`, `ChunkSet`) or plain lists of `Hit` rather than dicts when the shape is stable. Use `.to_dict()` only at the serialization boundary.
- Stages return their hits so calls chain: `trace.record(...)` returns `hits` (see `rag/common/trace.py`).

## Module Design

- Only the `chunking` package re-exports its strategies from `__init__.py`. Other packages keep `__init__.py` empty or minimal.
- Do not add a new barrel to hide internals; the orchestrator-plus-steps layout is the documented structure (`rag/README.md`, "Layout").
- The two pipelines communicate only through the chunk store (`rag/common/chunk_store.py`). Query code reads chunks through `ChunkStore`, never reads ingestion files directly.
- Only `rag/common/llm.py` knows how a model provider is called. Other modules take an `LLM` object or a spec string.
- Only the `rag/query/guard.py` `StreamGuard` may release streamed answer text.

## Project Behaviour That Must Not Drift

- `SYSTEM_PROMPT` in `rag/query/prompt.py` stays word for word. The golden-set results and the LLM disk cache depend on it. Uploads use `DOCUMENT_SYSTEM_PROMPT`.
- Page numbers are PDF page indexes (1-based) everywhere. For the DDIA book, printed page + 22.
- Treat gaps under about 8 points as noise on the 37 answerable golden questions (one question is 2.7 points).
- Never pass `cache_dir=None` for uploaded documents to the LLM cache; `get_llm(spec, cache_dir=None)` keeps the text after a delete.
- Upload chunk ids are `<doc_id>:<chunk_id>` and unique within an owner.
- In `rag/api/static/index.html`, insert untrusted text with `textContent`, never `innerHTML`.
- Stream answers only through `StreamGuard`, and show them as text.

## Adding New Code: Checklist

<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

## System Overview

```text

```

## Pattern Overview

- Orchestrators only choose order and skip stages; logic lives in step modules (for example `rag/query/fusion.py`, `rag/query/select_context.py`).
- The ingestion pipeline and the query pipeline share no code paths except `rag/common/` types and the chunk store. The chunk store is "the only link" (`rag/README.md`, diagram).
- Every query writes a `Trace` (`rag/common/trace.py`). Each stage records its hits, so evaluation can attribute a wrong answer to a stage.
- Stages are switched by named configs (`rag/query/configs.py`, `RetrievalConfig`). A disabled stage leaves no trace entry.
- Storage is pluggable behind one interface: `ChunkStore` (`rag/common/chunk_store.py`) with `MemoryChunkStore` and `OpenSearchChunkStore` (`rag/common/opensearch_store.py`). Selected by `RAG_STORE` (`memory` default, or `opensearch`).
- Multi-tenancy is enforced in the store: every read takes a `Scope` (owner plus optional document ids) and the filter is applied inside the query, not after it (`rag/common/chunk_store.py` docstring).

## Layers

- Purpose: Data objects and infrastructure that both pipelines use.
- Location: `rag/common/`
- Contains: `types.py` (`Page`, `Chunk`, `Hit`), `trace.py` (`Trace`), `config.py` (paths and extraction thresholds), `chunk_store.py`, `opensearch_store.py`, `store.py` (numpy vectors, exact cosine search), `bm25.py`, `stem.py`, `embed.py`, `llm.py` (model providers), `llm_check.py`, `secrets.py`, `log.py`.
- Depends on: standard library, numpy, optional provider SDKs.
- Used by: ingestion, query, observe, api, experiments.
- Purpose: Turn an uploaded or local PDF into cleaned pages, a chunk set, and a vector index.
- Location: `rag/ingestion/`
- Contains: `pipeline.py` (orchestrator `ingest()`), `extract.py` (pages and PDF bookmarks), `clean.py` (header/footer removal), `chunk.py` (strategy picker), `chunking/` (five strategies plus `base.py`, `units.py`, `document.py`, `build.py`, `stats.py`), `index.py` (embed and cache vectors), `profile.py` (document profile for "about the documents"), `sandbox.py` (child-process extraction with time and memory limits), `export_text.py`.
- Depends on: `rag/common/` (embed, store, config, types).
- Used by: `rag/api/service.py` (uploads), experiments, CLI.
- Purpose: Answer a question from the indexed chunks, with guards on untrusted text.
- Location: `rag/query/`
- Contains: `pipeline.py` (`RetrievalPipeline`, `RagPipeline`), `retrieve.py` (`dense_search`, `keyword_search`), `fusion.py` (RRF and weighted min-max), `rerank.py` (cross-encoder, optional), `select_context.py` (dedupe, parents, word budget), `generate.py` (prompt building, citation parsing, abstention detection), `prompt.py` (`SYSTEM_PROMPT`, `DOCUMENT_SYSTEM_PROMPT`), `guard.py` (`scan_chunks`, `filter_output`, `StreamGuard`), `configs.py` (named configs), `about.py` (answers about documents from their profiles).
- Depends on: `rag/common/`, and `rag/ingestion/chunking/base.py` (`ChunkSet` type).
- Used by: `rag/api/service.py`, `rag/experiments/`, `rag/observe/`.
- Purpose: Score traces and answers; never called on the request path.
- Location: `rag/observe/`
- Contains: `golden.py` (question loader), `retrieval_quality/` (`metrics.py`, `run_eval.py`, `diagnose.py`), `generation_quality/` (`judge.py`, `answers.py`, `calibrate_judge.py`), `golden_tools/` (question-writing helpers).
- Depends on: `rag/query/`, `rag/common/trace.py`.
- Used by: `rag/experiments/`, tests.
- Purpose: Poisoned fixtures and the injection test harness.
- Location: `rag/security/` (`fixtures.py`, `defenses.py`, `indirect.py`).
- Depends on: `rag/query/`. Used by: a CLI run only; the guards that run in production live in `rag/query/guard.py`.
- Purpose: HTTP surface and the chat page. Routes only; behaviour lives in service code.
- Location: `rag/api/`
- Contains: `main.py` (FastAPI app factory `create_app`, routes, request models, `current_owner`, `LimitUploadBody`), `service.py` (`DocumentService`), `static/index.html`.
- Depends on: `rag/ingestion`, `rag/query`, `rag/common`.
- Used by: uvicorn, the browser.
- Purpose: Scripts that run a full comparison and print a table.
- Location: `rag/experiments/` (`retrieval.py`, `answer.py`, `about.py`).
- Depends on: all of the above.

## Data Flow

### Ingestion Path (CLI or upload)

### Primary Query Request Path

### Streaming Path

### Ask-About-Documents Path

- Per-document state is files on disk: `data/uploads/<doc_id>/` holds `source.pdf`, `status.json`, `pages.jsonl`, `toc.json`, `chunks/`, `index/`, `chat/`. `DocumentService` guards writes with locks (`_status_lock`, `_load_lock`, `_create_lock`, `_ingest_lock`) and atomic file replacement.
- Vectors and chunks live in memory (`MemoryChunkStore`, rebuilt from `data/uploads/` at startup) or in OpenSearch (`RAG_STORE=opensearch`, indexes `rag_c_*`, `rag_p_*` per owner).

## Key Abstractions

- Purpose: Read and write chunks and vectors for a given owner and scope.
- Examples: `rag/common/chunk_store.py` (`MemoryChunkStore`), `rag/common/opensearch_store.py` (`OpenSearchChunkStore`).
- Pattern: Strategy/adapter. `tests/test_chunk_store.py` runs the same checks against both implementations.
- Purpose: Owner plus optional document ids, required on every read.
- Examples: `rag/common/chunk_store.py`.
- Pattern: Filter passed into the store; enforced inside the query.
- Purpose: Output of ingestion step 2; a list of `Chunk` with page ranges and metadata.
- Examples: `rag/ingestion/chunking/base.py`, `recursive.py`, `fixed.py`, `heading.py`, `parent_child.py`, `semantic.py`, `document.py`.
- Pattern: Strategy chosen by name via `make_chunker()` in `rag/ingestion/chunk.py`; valid names are `fixed`, `recursive`, `heading`, `parent_child`, `semantic`.
- Purpose: Named switches and parameters for one retrieval run (dense, bm25, fusion method, weights, rerank, top_k, word budget, scanner, per-source cap).
- Examples: `rag/query/configs.py` (`CONFIGS` dict). The API offers only configs that do not need a reranker (`USABLE_CONFIGS` in `rag/api/main.py`).
- Purpose: The record of what each stage returned, and the unit of a retrieved passage (`rag/common/types.py`).
- Pattern: Each stage calls `trace.record(name, kind, hits)` with `kind` either `retrieve` or `transform`.
- Purpose: Model providers behind one call interface (`generate`, streaming via `stream_answer`); embedders for `st:` (sentence-transformers) and other specs.
- Examples: `rag/common/llm.py`, `rag/common/embed.py`. Chosen by spec string such as `gemini:<model>`, `ollama:<model>`, `fake`.
- Pattern: Factory by string spec (`get_llm`, `get_embedder`).
- Purpose: Cross-encoder rescoring of the fused list.
- Examples: `rag/query/rerank.py`. Not loaded by the API service (`build_default_service` in `rag/api/main.py`), so rerank configs are unavailable there.

## Entry Points

- Location: `rag/api/main.py` (`create_app`, `app` for uvicorn `rag.api.main:app`).
- Triggers: `uvicorn rag.api.main:app --port 18642` (`RAG_STORE=opensearch` for the vector database).
- Responsibilities: routes under `/v1`, Host allowlist (`TrustedHostMiddleware`), Origin check on state-changing requests, upload size limit.
- Location: `rag/ingestion/pipeline.py` (`main`, run as `python -m rag.ingestion.pipeline`).
- Triggers: manual run on `data/raw/*.pdf`.
- Responsibilities: extract, chunk, and index one PDF end to end.
- `rag/ingestion/extract.py`, `rag/ingestion/chunking/build.py`, `rag/observe/golden_tools/find_pages.py`, `rag/common/llm_check.py`.
- `rag/experiments/retrieval.py` (retrieval table), `rag/experiments/answer.py` (answer scoring), `rag/experiments/about.py`.
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

### Trusting the keyword scanner as the only defence

### Streaming text without the guard

### Reading the owner from the request

## Error Handling

- `NotFound`, `BadUpload`, `TooLarge` in `rag/api/service.py`; mapped to 404, 400, and 413 in `rag/api/main.py`. Another owner's document is 404.
- Model failure during ask returns 502 with the reason (`rag/README.md` Step 8). A failure during streaming sends an `error` event.
- Startup recovery: documents left `queued` or `processing` are marked `failed` with "interrupted by a server restart" (`_recover_interrupted` in `rag/api/service.py`).
- Ingestion with no extractable text raises `ValueError` (`rag/ingestion/pipeline.py`).

## Cross-Cutting Concerns

<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-fast` for a trivial task inline, with no subagents and no PLAN.md
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
