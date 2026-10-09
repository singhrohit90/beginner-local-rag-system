# Backlog

Open items that are not built yet, with the reason each matters. Newest first inside each group.

## UI and API

- **The UI does not stream.** An answer, and the progress of an upload, appear all at once. Streaming needs:
  - an endpoint such as `POST /v1/documents/{id}/ask/stream` returning server-sent events (`StreamingResponse`);
  - a streaming call in `rag/common/llm.py` (`OpenAICompatLLM` waits for the whole reply today); the reasoning model sends its thinking separately, which must not be shown;
  - a decision about the output guard: `filter_output` judges the whole answer and can withhold it, which conflicts with showing words as they arrive (options: buffer until the check passes, or stream and retract);
  - citations are parsed at the end, so the page would link them when the stream finishes;
  - upload progress, the cheaper half, is already done (see below).
- **Duplicate uploads: done** for new uploads (same owner, same sha256 returns the existing document). Still open: uploads made before the hash existed are not recognised, and a caller-supplied `external_id` for a scraper (see `docs/auth_plan.md`).
- **Readable folder names.** Folders are a random id (`data/uploads/<id>/`); only the UI shows the real name.
- **Chat across several documents: done** (`POST /v1/ask`, one, several or all of the caller's documents). Cross-document questions are not saved as traces; decide how to keep them with a retention rule (see Security).
- **Upload progress: done** as a stage name (extracting, chunking, embedding) in `status.json` shown on the page. A percentage inside the embedding stage is not built.

## Security (see `docs/auth_plan.md`, `docs/mcp_risks.md`)

- Owner on every document and chunk is **done** and tested against both stores (a second user gets 404 for everything of the first user's, and never receives their passages). Still open: the owner comes from one placeholder function, `current_owner` in `rag/api/main.py`, that returns the single local user until Keycloak replaces it.
- Keycloak token validation; per-client identities for the page, a scraper and an MCP server.
- Retention for traces in `data/uploads/<id>/chat/` of documents that are not deleted.

## Retrieval and evaluation

- Approximate (HNSW) search in OpenSearch was not measured; only exact search was compared with the in-memory store.
- OpenSearch keyword search beat our in-memory BM25 by about 8 points on hit@5. Test whether stemming explains it by adding stemming to `rag/common/bm25.py`.
- Citation support and answer relevance checks in `rag/observe/generation_quality/`.
- Query rewriting and intent classification: only add them if the golden set shows a gain.
- Documents with images, tables and scans: the `Element` contract and OCR handlers (Stage 4 of the reorganisation plan).

## Running it

- WSL shuts down when nothing is attached, which stops OpenSearch. A background `wsl ... sleep` keeps it alive for now; a permanent fix means changing the WSL idle setting.
- The API runs on Windows because the model tunnel, the GPU and the files are there. Running it in a container needs the tunnel reachable from Docker.
- `docker-compose.yml` has the OpenSearch security plugin off; it is bound to `127.0.0.1` only. Enable security before anything else can reach it.
