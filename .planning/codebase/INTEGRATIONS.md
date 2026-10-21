---
last_mapped_commit: a53a2e9a053a09e28fd2a5cbe11629a8ded7d112
last_mapped_at: 2026-10-21
---
# External Integrations

**Analysis Date:** 2026-10-21

## APIs & External Services

**LLM generation (reasoning model):**
- On-prem vLLM server serving `gpt-oss-20b`, OpenAI-compatible chat completions
  - Endpoint: `{REMOTE_URL}/chat/completions`; default `http://127.22.10.1:30007/v1` (reached through a PuTTY SSH tunnel that binds to `127.22.10.1`, not localhost)
  - Client: `OpenAICompatLLM` in `rag/common/llm.py` (stdlib `urllib`, JSON over HTTP, streaming via `generate_stream`, retries on 429/5xx/timeouts, one retry with a larger budget when a reply is cut off during thinking)
  - Auth: `REMOTE_API_KEY` (optional, sent as bearer header; unused unless the server requires one)
  - Also lists models via `GET {REMOTE_URL}/models` (`list_models`)
  - Health check: `python -m rag.common.llm_check` (`rag/common/llm_check.py`)
  - Spec in code: `vllm:/models/gpt-oss-20b`

**LLM judge (local):**
- Ollama HTTP server on `http://localhost:11434`, model `qwen2.5:7b`
  - Client: `OllamaLLM` in `rag/common/llm.py`; default timeout 600 s
  - Auth: none
  - Used only in evaluation (`rag/observe/generation_quality/judge.py`, `calibrate_judge.py`), never in the product answer path

**Hosted LLM (optional):**
- Google Gemini API (`gemini-3.5-flash-lite` in experiments)
  - SDK: `google-genai`, imported lazily in `GeminiLLM` (`rag/common/llm.py`)
  - Auth: `GEMINI_API_KEY` from environment or `.env`
  - Limits: free tier around 20 requests per day per model, which is why it is not the default (`docs/models.md`); `GeminiLLM` retries up to 6 times

**Model downloads (Hugging Face Hub):**
- `sentence-transformers/all-mpnet-base-v2` - embedder, fetched on first use by `SentenceTransformer(...)` in `rag/common/embed.py`
- `cross-encoder/ms-marco-MiniLM-L-6-v2` - optional reranker, fetched by `CrossEncoder(...)` in `rag/query/rerank.py`
- Auth: none (public models). Network is needed once; afterwards models load from the local cache.

**Prompt-injection test fixtures:**
- `rag/security/fixtures.py` contains example attacker URLs (`https://attacker.example/...`) as text only; nothing calls them.

## Data Storage

**Vector and keyword database:**
- OpenSearch 2.17.1 (single node, Docker image `opensearchproject/opensearch:2.17.1`)
  - Defined in: `docker-compose.yml` (service `opensearch`, project `rag`, published as `127.0.0.1:9200:9200`)
  - Connection: `RAG_OPENSEARCH_URL` (default `http://127.0.0.1:9200`), read in `rag/api/main.py`; experiment scripts take `--opensearch-url`
  - Client: `opensearch-py` (`OpenSearch(hosts=[url], http_compress=True, timeout=30, max_retries=3, retry_on_timeout=True)`) in `rag/common/opensearch_store.py`
  - Security: DISABLE_SECURITY_PLUGIN=true, no TLS, no login. Acceptable only because the port is bound to loopback. Each owner has separate indexes (`rag/README.md`).
  - Selected by `RAG_STORE=opensearch`; default `RAG_STORE=memory` keeps chunks in process (`rag/common/chunk_store.py` `MemoryChunkStore`)
  - Start: `cat docker-compose.yml | wsl -d Ubuntu-24.04 -- docker compose -f - up -d opensearch` (`CLAUDE.md`)
  - Health: `curl -s http://127.0.0.1:9200`; tests skip OpenSearch cases when it is down

**Local file storage:**
- Filesystem only, no cloud bucket.
  - Uploads: `data/uploads/<doc_id>/` (source PDF, `status.json` with `owner`, pages, TOC, chunks, index) - `rag/api/service.py`
  - Book pipeline outputs: `data/processed/` (chunks, embeddings cache in `data/processed/index/`)
  - LLM response cache: `data/processed/llm_cache/` via `CachedLLM` (`rag/common/llm.py`). Disabled for uploads (`cache_dir=None` in `rag/api/main.py`) so deleted document text is not kept.
  - Traces and eval reports: `runs/`

**Caching:**
- Disk cache of LLM replies keyed on prompt, model and settings (`CachedLLM`); no Redis or memcached.
- Embedding cache on disk (`data/processed/index/`).

## Authentication & Identity

**Auth Provider:**
- None implemented. The API has no login.
  - Owner identity is a placeholder: `current_owner` in `rag/api/main.py` is the only function that will supply the caller's identity. Upload records carry `owner` in `status.json`.
  - Planned: Keycloak (JWT validation with JWKS, issuer and audience from `KEYCLOAK_ISSUER` and `KEYCLOAK_AUDIENCE`, authorization-code flow with PKCE in the page). Not yet in code; see `docs/auth_plan.md`.
- Request checks in place (`rag/api/main.py`):
  - `TrustedHostMiddleware` with `RAG_ALLOWED_HOSTS` (default `127.0.0.1,localhost`)
  - Origin check on state-changing requests: an `Origin` header must match the server origin or `RAG_ALLOWED_ORIGINS`; requests with no `Origin` (programs) pass

## Monitoring & Observability

**Error Tracking:**
- None. No Sentry, Datadog or similar SDK in the code.

**Logs:**
- Python `logging`, configured in `rag/common/log.py`. Third-party loggers (`httpx`, `httpcore`, `google_genai`, `huggingface_hub`, etc.) are quieted there.
- Per-question traces written as JSON via `rag/common/trace.py` into `runs/`.

## CI/CD & Deployment

**Hosting:**
- None. Runs on the developer's Windows 11 machine, with the API on `127.0.0.1` and OpenSearch in WSL2 Docker.

**CI Pipeline:**
- None detected (no `.github/workflows/`, `.gitlab-ci.yml`, or similar in the tracked files).

## Environment Configuration

**Required env vars:**
- None strictly required (`.env.example`: "Nothing here is required").
- Commonly set: `RAG_LLM`, `RAG_JUDGE`, `REMOTE_URL` (tunnel address), `GEMINI_API_KEY` (only for Gemini runs), `RAG_STORE` and `RAG_OPENSEARCH_URL` (for OpenSearch), `RAG_ALLOWED_HOSTS`, `RAG_ALLOWED_ORIGINS`, `RAG_NONCE_KEY` (optional, fixed value only for repeatable runs).

**Secrets location:**
- `.env` at the repo root, gitignored. Loaded through `rag/common/secrets.py` (environment first, then `.env`). Contents are not recorded in this document.
- Committed template: `.env.example` (no values).
- Only `GEMINI_API_KEY` and the optional `REMOTE_API_KEY` are secrets; `RAG_NONCE_KEY` is treated as one too.

## Webhooks & Callbacks

**Incoming:**
- None. The API exposes only its own routes (upload, status, list, ask/stream, delete) and the static page at `/`; no inbound webhooks. Routes are defined in `rag/api/main.py`.

**Outgoing:**
- None. The only outbound calls are the model requests above (vLLM, Ollama, Gemini) and Hugging Face model downloads.

---

*Integration audit: 2026-10-21*
