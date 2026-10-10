# System design, deployment and streaming

Interview questions about how the whole system fits together, how it runs, how it would scale, and how you stream an answer safely. Retrieval is in `01_retrieval_and_chunking.md`, evaluation in `02_generation_and_evaluation.md`, security in `03_security.md`.

Labels used below: **Built** means it exists in this repo and has tests. **Designed** means written down but not built. **General** means interview knowledge with no code here.

---

## 1. Walk me through the architecture

**Short answer.** Two pipelines. Ingestion turns a PDF into clean pages, then chunks, then vectors in a store. The query pipeline retrieves from dense and keyword search, fuses and optionally reranks, selects context, generates with citations, and runs an output guard. A thin web API sits on top, with owner isolation. Evaluation is a separate layer that reads the traces the pipelines write.

**Go deeper.**
- Each pipeline is a short orchestrator over single-purpose step modules, so each step can be run, tested and replaced alone.
- The seam between the query side and storage is the `ChunkStore` interface. There is an in-memory store for experiments and tests, and an OpenSearch store for real use. The same contract tests run against both.
- Every question writes a trace (stage names, hits, scores, timings), and the evaluation layer scores traces, not live calls.

**In this repo (Built).**
- Ingestion: `rag/ingestion/pipeline.py` calls `rag/ingestion/extract.py`, `rag/ingestion/chunk.py`, `rag/ingestion/index.py`.
- Query: `rag/query/pipeline.py` has `RetrievalPipeline` and `RagPipeline`; steps are `retrieve.py`, `fusion.py`, `rerank.py`, `select_context.py`, `generate.py`, `guard.py`.
- Store interface and the in-memory store: `rag/common/chunk_store.py`. OpenSearch store: `rag/common/opensearch_store.py`.
- Trace: `rag/common/trace.py`. Evaluation: `rag/observe/`.
- Web API: `rag/api/service.py` (work), `rag/api/main.py` (routes), `rag/api/static/index.html` (page).
- Reading order for a newcomer: `rag/README.md`, "Read in this order".

**Follow-ups.** Where would you add caching? Where does a request spend its time? (Stage timings are in the trace and shown on the page.)

---

## 2. Why plain Python and not LangChain or LangGraph?

**Short answer.** The pipeline is a fixed sequence with a few switches, so a plain function chain is easier to read, test and measure than a framework graph. I would move to LangGraph when the flow gets real branching: routing between tools, loops (retry, self-check), persistent state, or human approval.

**Go deeper.**
- A framework earns its cost when you need what it provides: state checkpoints, retries, tracing hooks, tool routing, human-in-the-loop. A linear retrieve-then-generate flow needs none of these.
- Costs of adopting early: more abstraction between you and the prompt, harder step-by-step tests, upgrades that change behaviour. Costs of not adopting: you write the glue yourself.
- Evaluation matters more than orchestration choice: you need your own traces either way.

**In this repo.** Decision and the case for revisiting it: `rag/README.md`, "Design decisions". Automatic routing of questions about the documents themselves (see section 10) is the first realistic LangGraph use. **General** for the framework comparison.

**Follow-ups.** What would the graph nodes be? (classify intent, retrieve, generate, check, maybe retry with a rewritten query.)

---

## 3. How did you separate ingestion, query and evaluation, and why?

**Short answer.** They change at different speeds and fail differently. Ingestion is slow and run once per document, the query path is latency-sensitive, and evaluation is offline and compares configurations. Keeping them apart lets me change a chunker without touching generation and re-score the same questions.

**In this repo (Built).** Layout table in `rag/README.md` ("Layout"). The retrieval invariant check after every refactor: `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` must still give hit@5 0.865 and mrr 0.663 (`CLAUDE.md`, "Commands"). That check is how I showed the reorganisation changed no behaviour.

---

## 4. How is the API designed, and why?

**Short answer.** Resource-style routes under `/v1`, uploads return 202 and ingest in the background while the page polls a status, every call is scoped to an owner taken from one function, and errors map to clear HTTP codes.

**Go deeper.**
- `/v1` prefix so the contract can change later without breaking clients such as a scraper or an MCP server.
- Upload is slow (extract, chunk, embed), so it returns 202 with the document id and the page polls `GET /v1/documents/{id}` for `state` and `stage`.
- Duplicate upload (same owner, same file hash, same chunker) returns the existing document instead of indexing again.
- Another owner's document is a 404, not a 403, so existence does not leak.
- Errors: 400 bad file, 413 too large, 404 not found, 409 not ready, 502 model server unreachable (with the reason, addresses removed).

**In this repo (Built).**
- Routes: `rag/api/main.py` (`/v1/documents`, `/v1/documents/{id}`, `/v1/documents/{id}/ask`, `/v1/ask`, `/v1/ask-about`, `/v1/health`, `/v1/status`).
- Owner: `current_owner` in `rag/api/main.py`, the one place Keycloak will plug in (`docs/auth_plan.md`).
- Duplicates, stages, status files: `DocumentService` in `rag/api/service.py`.
- Error text without addresses: `DocumentService._public_error`.

**Follow-ups.** Why a dedicated endpoint for the UI instead of reusing the CLI code? (The page talks to the API only, so the pipelines stayed unchanged.)

---

## 5. How do you run it, and how would it scale?

**Short answer (what exists).** The API runs on Windows, because the GPU, the model tunnel and the files are there. OpenSearch runs in a Docker container in WSL. The model server is remote, reached through an SSH tunnel. It is a single-machine, single-user setup.

**Go deeper (what I would do for many users).** **Designed or General**, not built:
- One ingestion at a time today (a lock, because the embedder shares the GPU). For many uploads: a job queue and separate worker processes, with the API only enqueueing.
- In-process state (the set of running ingestions, the loaded-documents check) must move out of the API process before running several API replicas.
- The model server is the bottleneck: batching, a queue in front of it, per-user rate limits, and a cache for repeated questions (with the privacy caveat for uploaded documents).
- OpenSearch: more than one node, replicas, security plugin on, snapshots. The per-owner index design needs reviewing at thousands of owners (each index has overhead); an alias plus a filter on a routing key is the usual alternative, with the BM25-statistics trade-off described in `01_retrieval_and_chunking.md`.
- API in Docker once the tunnel is reachable from the container.

**In this repo.** `docker-compose.yml` (OpenSearch 2.17.1 on `127.0.0.1:9200`). Commands and the WSL quirks: `CLAUDE.md`, "Commands". Plans and open items: `docs/backlog.md`.

**Follow-ups.** What breaks first at 100 concurrent users? (The single GPU model server and the one-at-a-time ingestion.)

---

## 6. The first page load was slow. What was wrong and how did you fix it?

**Short answer.** The server built its models (embedder, model client, OpenSearch connection) on the first request, so the first visitor after a restart waited. I now load the models in a background thread at startup, serve the document list straight from the folders without the models, show placeholder rows meanwhile, and expose a readiness flag so the page holds the Ask button until the models are ready.

**Go deeper.** The general pattern is: cold start cost should be paid before the first user, in the background, and the UI should show honest states (loading, ready, failed) instead of hanging. Measured here after a restart: the list answers in 0.23 s, the models are ready about 10 s later.

**In this repo (Built).** `warm_up` and the lifespan in `create_app` (`rag/api/main.py`); `DocumentService.list_in` (`rag/api/service.py`) reads the list without models; `GET /v1/health` returns `ready`; skeleton rows and `checkReady` in `rag/api/static/index.html`; tests in `tests/test_api.py` (`test_the_list_is_readable_before_the_models_have_loaded`).

---

## 7. How do you know the system is up? (health and observability)

**Short answer.** A status endpoint checks the model server (asks which models it offers, no generation) and the database (cluster health), each with a time limit, and the page shows a green, amber or red light with the details on hover. Per question I keep a trace with stage timings. Full production observability (metrics, dashboards, alerts, tracing across services) is a separate project and not built here.

**In this repo (Built).** `DocumentService.status` and `_probe` (`rag/api/service.py`), `GET /v1/status` (`rag/api/main.py`), `checkStatus` and the light in `rag/api/static/index.html`. Traces: `rag/common/trace.py`, saved per question under the document's own folder `data/uploads/<doc_id>/chat/` so deleting the document deletes them.

**Follow-ups.** What would you alert on? (model server unreachable, p95 latency, abstention rate, blocked-answer rate, ingestion failures.) **General.**

---

## 8. How would you stream an answer, and how do you validate a streamed answer?

**Status: Designed, not built.** The streaming item is written up in `docs/backlog.md` ("The UI does not stream"). The reasoning below is the design.

**Short answer.** Stream tokens to the browser for speed, but treat the output check as part of the stream: hold back anything that could be the start of something risky until it is judged safe, stream the rest, then run the whole-answer check at the end and replace the text if it fails.

**Why it is hard.** The output filter (`filter_output` in `rag/query/guard.py`) can only judge the finished answer. It looks for the canary, an echo of the system prompt, an external image, and a URL that was not in the retrieved text. Each can be spread over several tokens, so you cannot know a URL is a URL until its last piece arrives. If tokens are already in the browser when the filter says no, that text is out.

**What can and cannot be undone.**
- **Can be done:** remove or replace the text on screen (replace the DOM text with a "withheld" notice), mark the answer as blocked in the server log, count it in metrics, and stop the model from generating more (cancel the request).
- **Cannot be done:** un-send bytes. Anything the client already did with them stays done: a markdown renderer that fetched an image has already sent the address (and any data in it) to the attacker's server; a browser extension or screen reader may have copied the text; the user may have read it.
- So retraction is a display fix, not a security control. The control has to stop the risky piece from being released in the first place.

**Options.**
1. **Buffer, then send:** safe, but it is not streaming.
2. **Stream, then replace:** fast. Fine when the client shows plain text, because nothing is fetched or run from text on screen. Not safe for a client that renders markdown.
3. **Stream with hold-back, then replace (my recommendation):** release text up to a safe boundary and hold back any tail that could be the start of `![`, `](`, `http`, `<`, or a prefix of the canary, until the next tokens show whether it is harmless. Normal prose flows; a risky piece is never sent early. The whole-answer check still runs at the end.
4. **Fix it at the display side (do this first, in any case):** do not turn images or links from untrusted domains into requests; use an image proxy and an allow-list of outside domains. This is what Google did for NotebookLM, after a researcher showed that a poisoned source document could make it write a markdown image carrying private data to an outside server. Azure OpenAI offers the same trade-off as two modes: default streaming holds each piece back until it is checked, and an asynchronous mode streams at once with delayed verdicts, which Microsoft says can show some content that would have been blocked.

**Other things an interviewer may probe.**
- **Reasoning tokens:** the generator is a reasoning model; its thinking arrives separately and must not be streamed to the user.
- **Citations:** parsed at the end, so the page links `[S1]` markers when the stream finishes.
- **Mid-stream failure:** send an error event, mark the partial text as incomplete, never present it as a finished answer.
- **Cancellation:** if the client disconnects, cancel the model call so you stop paying for tokens.
- **Protocol:** server-sent events are enough (one direction, simple, works through proxies); WebSockets are for two-way needs.
- **Time to first token and inter-token latency** are the metrics that streaming improves; total time does not change.

**How do you validate a streamed answer?** Two layers.
1. *Online, per request:* the hold-back filter plus the final whole-answer check above.
2. *Offline, for quality:* score the final concatenated text with the same judges as non-streamed answers (faithfulness, correctness; see `02_generation_and_evaluation.md`). Streaming changes delivery, not content, so you need a test that the streamed pieces joined together equal the final answer.
- Tests worth writing: split a hostile answer at every possible token boundary and check that nothing risky is ever released before its verdict; check that the filter's final verdict matches the non-streaming filter; check reasoning tokens never appear.

**In this repo.** Filter: `rag/query/guard.py` (`filter_output`, which already also reads text the way a renderer does: entities, backslash escapes, invisible characters). Page shows answers as plain text: `rag/api/static/index.html` (`textContent`). Rule for other clients: `docs/mcp_risks.md`, section 2. Sources for the industry practice: [Simon Willison on markdown exfiltration](https://simonwillison.net/tags/markdown-exfiltration), [NotebookLM fix](https://simonwillison.net/2024/Apr/16/google-notebooklm-data-exfiltration), [Azure OpenAI content streaming](https://learn.microsoft.com/azure/ai-foundry/openai/concepts/content-filter).

---

## 9. How do you handle multi-tenancy and deleting a user's data?

**Short answer.** The owner is required on every read and is applied inside the store, not after the search; each owner has separate indexes; deleting a document deletes its folder, its traces, its profile, and its rows in the database. Nothing about an uploaded document is cached on disk elsewhere.

**In this repo (Built).** Details and the reasons are in `03_security.md`, sections on tenant isolation and privacy. Code: `Scope` in `rag/common/chunk_store.py`, per-owner indexes in `rag/common/opensearch_store.py`, `DocumentService.delete` in `rag/api/service.py`.

---

## 10. Tell me about a limit you found by using the product and how you handled it.

**Story.** Asked across two HBase books, "when should I use the Definitive Guide and when the Reference Guide?" returned "I cannot answer this from the provided document". The refusal was honest: no passage says how two books differ, because that is a fact about the books. Retrieval over text chunks cannot answer questions like that.

**What I did.** I did not change the retrieval pipeline. I gave such questions their own data and path: a profile per document (name, page count, contents list, the preface), built from text we already extract so it needs no model and cannot invent anything, and a separate answer step and route that the user chooses on the page. I rejected automatic routing for now because it needs a classifier that has to be measured first, and rejected putting the profile into the search index because it would move the retrieval numbers.

**What it taught me.** Two real review findings in that new feature (a hostile bookmark or file name could carry instructions or a fake closing tag into the prompt) were fixed with tests. And the first evaluation run showed the judge matters more than the answers: 1 of 5 correct with a small judge, 5 of 6 with the generator grading itself, so neither is a result.

**In this repo (Built).** `docs/about_the_documents.md` (design, alternatives, safety, measured), `rag/ingestion/profile.py`, `rag/query/about.py`, `POST /v1/ask-about`, `tests/test_about.py`, golden questions `data/golden/about_questions.jsonl`, runner `rag/experiments/about.py`.

---

## 11. Decisions I would defend, and what I rejected

| Decision | Why | Rejected |
|----------|-----|----------|
| OpenSearch as the vector store | BM25, kNN and filters in one system | Qdrant, pgvector (no native BM25 in one query) |
| Per-owner indexes | Lucene BM25 statistics are index-wide; a shared index leaked ranking between owners | One shared index with a filter |
| Own fusion (RRF, weighted) | Keeps experiments comparable across stores | OpenSearch's hybrid pipeline |
| Plain Python orchestration | Fixed flow, easier to test | LangChain, LangGraph (for now) |
| Frozen `SYSTEM_PROMPT` for the book | Golden results and cache depend on it | Editing it per task; uploads get their own prompt |
| Profiles kept out of the index | Retrieval numbers must not move | A profile chunk in search |
| Fail closed in the extraction sandbox | No limit means no sandbox | Running the file unbounded with a warning |
| Plain-text rendering of answers | A pattern filter will be bypassed | Trusting the output filter alone |

Where each is recorded: `rag/README.md` ("Design decisions", Steps 9 and 10), `docs/about_the_documents.md`, `docs/auth_plan.md`.

---

## 12. What would you do differently, and what is not done?

Be direct about this in an interview; it shows judgment.
- **Not built:** streaming, real authentication (a single user `local` today; Keycloak is planned in `docs/auth_plan.md`), the API in Docker, online evaluation, citation-support and answer-relevance scoring (`docs/backlog.md`), OCR and tables and images.
- **Not measured:** approximate (HNSW) kNN recall; the extraction sandbox on Linux or macOS; the about-the-documents path with a judge that is not the generator.
- **Known weakness:** the output filter is a pattern list that was bypassed several times in review; the real defence is to show answers as plain text.
- **If starting over:** write the golden set and the trace first, before the second chunker; it would have saved the dead ends recorded in `CLAUDE.md` (the holistic judge, page-overlap relevance).

---

## 13. The two-minute project story

I built a RAG system over a technical book and uploaded PDFs to learn how production RAG works, with evaluation and security as the priority. There are two pipelines, ingestion and query, each a thin orchestrator over small step modules, and an evaluation layer that scores the traces. Retrieval is hybrid: dense vectors and BM25, fused, with an optional reranker, on OpenSearch with one index per user. I measured chunking strategies and retrieval configurations on a 45-question golden set and learned to treat gaps under about 8 points as noise. I tested prompt injection with poisoned documents, built layered defences (scanner, prompt, context limits, output filter), and found through review that a pattern filter alone gets bypassed, so the real rule is to show answers as plain text. A small web page lets you upload and chat across your documents and see the passages, scores and stage timings. When I hit a question the pipeline could not answer by design, I added a separate path instead of bending the pipeline. What is left: streaming, authentication, and deployment.
