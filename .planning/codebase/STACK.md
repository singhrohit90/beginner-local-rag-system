---
last_mapped_commit: a53a2e9a053a09e28fd2a5cbe11629a8ded7d112
last_mapped_at: 2026-10-21
---
# Technology Stack

**Analysis Date:** 2026-10-21

## Languages

**Primary:**
- Python 3.10 (observed: `__pycache__` contains `cpython-310` bytecode; no `pyproject.toml`, `setup.py` or `.python-version` pins a version) - all pipeline, API, experiment and test code under `rag/` and `tests/`

**Secondary:**
- HTML/CSS/JavaScript (vanilla, no build step) - chat page `rag/api/static/index.html`
- Markdown and JSON Lines - golden question set `data/golden/ddia_questions.jsonl`, `data/golden/about_questions.jsonl`; document/chunk outputs under `data/processed/`

## Runtime

**Environment:**
- CPython 3.10 on Windows 11 (developer machine). Code is also written to run on Linux and macOS: `rag/ingestion/sandbox.py` switches between a Windows Job Object (via `ctypes`) and `RLIMIT_AS` on other platforms.
- Optional GPU for local embeddings and the cross-encoder (CUDA via `torch`, pulled in by `sentence-transformers`); CPU works.
- WSL2 Ubuntu-24.04 hosts Docker for OpenSearch (`docker-compose.yml`).

**Package Manager:**
- pip. Dependencies are listed in `requirements-rag.txt` (no version lock file; no `requirements.lock`, `poetry.lock` or `uv.lock` present).
- Lockfile: missing

## Frameworks

**Core:**
- FastAPI `>=0.110` - web API and static page serving, `rag/api/main.py`
- Starlette (transitive via FastAPI) - `TrustedHostMiddleware` host allowlist, `StreamingResponse` for streamed answers
- Uvicorn `>=0.29` - ASGI server; run as `uvicorn rag.api.main:app` (the project's documented port is 18642, see `CLAUDE.md`)
- Pydantic (transitive via FastAPI) - request models in `rag/api/main.py`
- Plain Python orchestration for the RAG pipelines (no LangChain/LangGraph; decision recorded in `rag/README.md`)

**Testing:**
- pytest `>=8` - test runner; tests in `tests/` (e.g. `tests/test_api.py`, `tests/test_stream_guard.py`, `tests/test_security.py`)
- httpx `>=0.27` - used by FastAPI's `TestClient` in API tests only

**Build/Dev:**
- No build tool, linter or formatter config detected (no `ruff`, `black`, `mypy` or `flake8` config files in the repository root)
- Python `-m` entry points for every stage (e.g. `python -m rag.ingestion.pipeline`, `python -m rag.experiments.retrieval`), documented in `rag/README.md`

## Key Dependencies

**Critical:**
- `pymupdf` `>=1.24` (import name `pymupdf`) - PDF text extraction with bookmarks, `rag/ingestion/extract.py`, `rag/ingestion/sandbox.py`. Text layer only; no OCR or layout model (`docs/models.md`, `docs/extraction.md`).
- `numpy` `>=1.26` - vectors and exact cosine search, `rag/common/store.py`, `rag/common/bm25.py`, `rag/common/chunk_store.py`, `rag/common/embed.py`, `rag/ingestion/chunking/semantic.py`
- `sentence-transformers` `>=3` - local embedder (`all-mpnet-base-v2`, `rag/common/embed.py`), semantic chunker, and cross-encoder reranker (`cross-encoder/ms-marco-MiniLM-L-6-v2`, `rag/query/rerank.py`). Lazy-imported, so tests run without it. Pulls in `torch` and `transformers`.
- `opensearch-py` `>=2.4` - client for the vector database, `rag/common/opensearch_store.py`. Only needed when `RAG_STORE=opensearch`.

**Optional provider SDK:**
- `google-genai` - Gemini provider, lazy-imported inside `GeminiLLM` in `rag/common/llm.py`. Commented out in `requirements-rag.txt`; install only when using `gemini:` models. Not used in the default path (`docs/models.md`).

**Infrastructure:**
- `python-multipart` `>=0.0.9` - multipart form parsing for PDF uploads (`UploadFile` in `rag/api/main.py`)
- `anyio` (transitive) - `run_in_threadpool`/`iterate_in_threadpool` used by the API
- Standard library only for HTTP clients: `urllib.request`, `urllib.error`, `http.client` in `rag/common/llm.py` (no `requests` or `openai` package; the OpenAI-compatible and Ollama calls are hand-written JSON over HTTP)
- `hashlib`, `zlib` - cache keys and feature hashing (`rag/common/embed.py` `HashingEmbedder`, `rag/common/llm.py` `CachedLLM`)

**Container image:**
- `opensearchproject/opensearch:2.17.1` - single-node vector and keyword store, defined in `docker-compose.yml` (project name `rag`)

## Model Runtimes (external to the Python env)

- On-prem vLLM server running `gpt-oss-20b` (reasoning model) - OpenAI-compatible `/v1/chat/completions`, reached through an SSH tunnel. Default `RAG_LLM` is `vllm:/models/gpt-oss-20b`. Client: `OpenAICompatLLM` in `rag/common/llm.py`. Defaults in code: `DEFAULT_REMOTE_URL = "http://127.22.10.1:30007/v1"`.
- Ollama (local) serving `qwen2.5:7b` as the judge - default `RAG_JUDGE` is `ollama:qwen2.5:7b`. Client: `OllamaLLM` in `rag/common/llm.py`, default host `http://localhost:11434`.
- Google Gemini API (hosted, optional, `gemini-3.5-flash-lite` in experiments) - `GeminiLLM` in `rag/common/llm.py`. Dropped from the default path because of the free-tier daily quota.
- Local models downloaded by sentence-transformers from Hugging Face on first use: `sentence-transformers/all-mpnet-base-v2` (embedder, 384-token limit), `cross-encoder/ms-marco-MiniLM-L-6-v2` (reranker, optional).

## Configuration

**Environment:**
- Settings come from environment variables or a gitignored `.env` file at the repo root. `.env.example` is the committed template with no values.
- Helper that reads secrets: `rag/common/secrets.py` (environment first, then `.env`; documented as never logging or defaulting a key).
- Variables read in code:
  - `RAG_LLM`, `RAG_JUDGE`, `RAG_EMBEDDER` - provider specs (`rag/api/main.py`, `rag/experiments/*.py`, `rag/security/indirect.py`)
  - `RAG_STORE` - `memory` (default) or `opensearch` (`rag/api/main.py`)
  - `RAG_OPENSEARCH_URL` - default `http://127.0.0.1:9200` (`rag/api/main.py`)
  - `RAG_ALLOWED_HOSTS`, `RAG_ALLOWED_ORIGINS` - API host and origin allowlists (`rag/api/main.py`)
  - `RAG_NONCE_KEY` - spotlight prompt nonce (documented in `.env.example`)
  - `REMOTE_URL`, `REMOTE_API_KEY` (optional), `REMOTE_MODEL`, `REMOTE_REASONING_BUDGET`, `REMOTE_REASONING_EFFORT` - vLLM client (`rag/common/llm.py`)
  - `GEMINI_API_KEY` - Gemini client (`rag/common/llm.py`); the value lives only in the gitignored `.env`
- Tuning constants live in code, not env: `rag/common/config.py` (paths, `HEADER_FRACTION = 0.10`, `FOOTER_FRACTION`, `REPEAT_THRESHOLD = 0.2`).

**Paths (from `rag/common/config.py`):**
- `data/raw/` - source PDFs (gitignored)
- `data/processed/` - extraction output, chunks, embedding index in `data/processed/index/`, LLM cache in `data/processed/llm_cache/` (gitignored)
- `data/uploads/<doc_id>/` - API uploads: `source.pdf`, `status.json`, `pages.jsonl`, `toc.json`, `chunks/`, `index/` (gitignored)
- `data/golden/` - committed golden question sets
- `runs/` - per-query traces and eval reports (gitignored)

**Build:**
- No build configuration. `requirements-rag.txt` is the only dependency declaration.
- `docker-compose.yml` - OpenSearch service only; publishes `127.0.0.1:9200` and disables the security plugin for development (not for shared networks).
- `.gitignore` - ignores `.env`, `.venv`, `data/raw/`, `data/processed/`, `data/uploads/`, `runs/`, `__pycache__/`, `.pytest_cache/`.

## Platform Requirements

**Development:**
- Python 3.10+ with `pip install -r requirements-rag.txt`; `pip install sentence-transformers` for the semantic chunker and embedder (pulls `torch`).
- Docker (in WSL2 on the developer machine) for OpenSearch when `RAG_STORE=opensearch`.
- An SSH tunnel (PuTTY) to the vLLM host for the default generator; Ollama on localhost for the judge.
- Tests run offline with `python -m pytest tests -q`; OpenSearch tests skip when the database is down.

**Production:**
- Not deployed. The API is for localhost only (`127.0.0.1`), with no authentication yet (`docs/auth_plan.md`).
- Target described in the docs: Keycloak-based authentication and an OpenSearch security-enabled cluster before any shared use.

---

*Stack analysis: 2026-10-21*
