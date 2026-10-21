---
last_mapped_commit: a53a2e9a053a09e28fd2a5cbe11629a8ded7d112
last_mapped_at: 2026-10-21
---
# Codebase Concerns

**Analysis Date:** 2026-10-21

## Tech Debt

**Owner is a placeholder (single local user):**
- Issue: every route takes its owner from `current_owner()`, which always returns `LOCAL_OWNER`. Multi-owner isolation is enforced in the store and service, but no caller identity exists yet.
- Files: `rag/api/main.py` (`current_owner`, all `Depends(current_owner)` routes), `rag/api/service.py` (`LOCAL_OWNER`), `docs/auth_plan.md`
- Impact: any client that reaches the API is the same user. Isolation tests pass only because tests override the function.
- Fix approach: replace `current_owner` with Keycloak token validation (backlog item in `docs/backlog.md`, Security section). Keep it the only place the owner is read.

**Chat has no memory:**
- Issue: each `/v1/ask` question is retrieved on its own. Follow-ups ("what is its population?") search for the pronoun.
- Files: `rag/query/pipeline.py`, `rag/api/service.py` (`ask`, `ask_documents`), `docs/backlog.md`, `interview/05_conversation_memory_and_cost.md`
- Impact: multi-turn use gives weak retrieval and abstentions that look like failures.
- Fix approach: conversation id, a rewrite step before retrieval, then compaction. Add only after a multi-turn golden set shows a gain (per `docs/backlog.md`).

**Stemming is off by default in the in-memory BM25:**
- Issue: `BM25Index(chunks, stem=False)` is the default. OpenSearch's `english` analyzer stems, so the two stores rank keywords differently (about 5 to 8 hit@5 points on the golden set).
- Files: `rag/common/bm25.py`, `rag/common/stem.py`, `rag/README.md` (Step 9)
- Impact: experiment results differ by store. Retrieval invariant `--chunkers semantic --configs weighted` (hit@5 0.865, mrr 0.663) is pinned to the default setting.
- Fix approach: decide per store, or make stemming the same in both, then update the invariant numbers in `rag/README.md` and `CLAUDE.md`.

**Extraction reads only the text layer:**
- Issue: tables, images, figures and scanned pages are not handled. Image blocks are skipped (`block["type"] != 0`), tables lose grid order, and a scanned PDF fails with "OCR is not supported yet".
- Files: `rag/ingestion/extract.py` (`_read_blocks`, `_block_text`), `rag/ingestion/pipeline.py`, `docs/extraction.md`
- Impact: answers that need a table or figure are wrong or abstain, and the golden set cannot score them.
- Fix approach: the `Element` contract and layout/OCR handlers in `docs/extraction.md` ("If this is built next"). Measure on the two HBase books against the plain-text path.

**Extraction is a single loop, one document at a time:**
- Issue: pages are read in one process; `_ingest_lock` in `rag/api/service.py` serialises ingestion because the embedder shares the GPU.
- Files: `rag/ingestion/extract.py`, `rag/api/service.py` (`_ingest_lock`), `docs/extraction.md`
- Impact: 500-plus page uploads are slow and block other uploads. Time for 500 pages was not measured.
- Fix approach: measure first. Then process pages in a pool with results sorted by page number; keep one embedder.

**Judge and answer scoring are noisy:**
- Issue: a 7B local judge (`ollama:qwen2.5:7b`) is not ground truth; calibration gives 95 to 100 percent correctness and 89 percent faithfulness, with false "unfaithful" marks. The golden set has 37 answerable questions, so one question is 2.7 points.
- Files: `rag/observe/generation_quality/judge.py`, `rag/observe/generation_quality/calibrate_judge.py`, `rag/observe/generation_quality/answers.py`, `rag/README.md` (Step 6)
- Impact: differences under about 8 points are treated as noise, but results are still reported as decisions.
- Fix approach: rerun calibration whenever the judge or prompt changes; read stored verdict reasons for a sample. Do not retry the holistic correctness judge or page-overlap-only relevance (`CLAUDE.md`).

**Golden set partly written by agents:**
- Issue: `data/golden/ABOUT_REVIEW.md` and `data/golden/KEY_FACTS_REVIEW.md` record facts written by agents; the about questions and key facts are not yet confirmed by a real run.
- Files: `data/golden/about_questions.jsonl`, `data/golden/ddia_questions.jsonl`, `data/golden/ABOUT_REVIEW.md`, `data/golden/KEY_FACTS_REVIEW.md`, `HANDOFF.md` (section 6, item 5)
- Impact: a wrong gold label reads as a pipeline failure, or a wrong answer passes.
- Fix approach: review the key facts against the book, then run the golden set once with the real model.

**Model-server dependence and manual steps:**
- Issue: generation and judge run through a PuTTY tunnel to `127.22.10.1:30007`. When it is down, `/v1/ask` returns 502. WSL stops when idle and takes the OpenSearch container with it.
- Files: `rag/common/llm.py` (not read for this map; see Unverified), `rag/common/llm_check`, `docker-compose.yml`, `docs/backlog.md` (Running it), `CLAUDE.md`
- Impact: a documented workflow, not a code fault, but it blocks runs and makes results hard to reproduce.
- Fix approach: a background `wsl -d Ubuntu-24.04 -- sleep 100000` for now; a permanent WSL idle setting (needs approval per `HANDOFF.md` section 7).

**Sandbox runs only on Windows:**
- Issue: the child process memory cap is a Windows Job Object. On Linux and macOS it uses `RLIMIT_AS`, which has not been run.
- Files: `rag/ingestion/sandbox.py` (`_WindowsJob`, `_child`, `run_limited`), `docs/extraction.md`, `docs/backlog.md`
- Impact: a Linux or macOS deployment may fail extraction, or not be capped.
- Fix approach: run `tests` for the sandbox on Linux before any non-Windows deployment.

## Known Bugs

**Duplicate uploads from before the hash check are not recognised:**
- Symptoms: uploads made before the sha256 check existed are not recognised as duplicates, so the same file can be stored twice for one owner.
- Files: `rag/api/service.py` (`create`, duplicate check under `_create_lock`), `docs/backlog.md` (Duplicate uploads)
- Trigger: upload a file, then upload it again after the duplicate check was introduced only for new documents.
- Workaround: delete the older document with `DELETE /v1/documents/{id}`.

**Cross-document questions are not traced:**
- Symptoms: `/v1/ask` (several or all documents) saves no trace, so those answers cannot be audited later.
- Files: `rag/api/service.py` (`ask_documents`, `ask_documents_stream`), `docs/backlog.md` (Chat across several documents)
- Trigger: any question with `doc_ids: null` or more than one id.
- Workaround: none; decide on a retention rule (tied to the trace-retention item under Security).

**Comparison questions across documents abstain:**
- Symptoms: "When should one use the definitive guide and the reference guide?" returned "I cannot answer this from the provided document".
- Files: `rag/query/about.py`, `rag/ingestion/profile.py`, `docs/backlog.md` (Questions about the documents themselves), `docs/about_the_documents.md`
- Trigger: a question about the documents themselves sent to `/v1/ask` instead of `/v1/ask-about`.
- Workaround: the user picks "about the documents themselves" on the page, which calls `POST /v1/ask-about`. Automatic routing is not built.

**Streaming gaps:**
- Symptoms: no Stop button; the about path answers in one piece; the embedding stage shows a stage name, not a percentage.
- Files: `rag/api/main.py` (`stream_request`, `ask_stream`), `rag/api/static/index.html`, `docs/backlog.md`
- Trigger: a long answer or upload in the page.
- Workaround: closing the connection stops the model (`_close_when_idle` in `rag/api/main.py`).

## Security Considerations

**Unauthenticated API:**
- Risk: there is no login. Anyone who can reach the port can read, upload, ask and delete as the local user.
- Files: `rag/api/main.py` (`current_owner`, `create_app`, `reject_foreign_origins`, `LimitUploadBody`)
- Current mitigation: `TrustedHostMiddleware` with `RAG_ALLOWED_HOSTS` (default `127.0.0.1`, `localhost`); an Origin check on state-changing requests (`reject_foreign_origins`), which does not apply to requests without an Origin header; the server binds to localhost in the documented run.
- Recommendations: keep the bind to localhost until Keycloak is in place (`docs/auth_plan.md`, `docs/mcp_risks.md`). Note that the Origin check does not stop a non-browser client.

**OpenSearch security plugin disabled:**
- Risk: `DISABLE_SECURITY_PLUGIN: "true"` in `docker-compose.yml`. Any process that reaches the OpenSearch port can read and modify every owner's indexes.
- Files: `docker-compose.yml` (lines 6 to 20), `rag/common/opensearch_store.py`
- Current mitigation: the port is published on `127.0.0.1` only (`docker-compose.yml`, `docs/backlog.md`).
- Recommendations: enable the security plugin before exposing the port or running the API in Docker (`docs/backlog.md`, Running it).

**Prompt-injection defences are a pattern list:**
- Risk: the scanner (`rag/query/guard.py`, `scan_text`, the `_PATTERNS`-style table) and the output filter (`filter_output`) match fixed phrases and URL or image shapes. `CLAUDE.md` records that review has bypassed the output filter repeatedly. The payload check in `rag/security/defenses.py` (`classify`) only detects verbatim compliance.
- Files: `rag/query/guard.py` (`scan_text`, `filter_output`, `StreamGuard`), `rag/query/prompt.py`, `rag/security/fixtures.py`, `rag/security/defenses.py`, `rag/security/indirect.py`, `rag/README.md` (Step 7)
- Current mitigation: `StreamGuard` holds back risky text before it is sent; the whole-answer check runs at the end; the system prompt holds a canary `CANARY-7f3a91` that must never appear.
- Recommendations: treat the filter as a last check, not a control. Test with adaptive attacks, not only the ten fixtures written by the defender (`rag/README.md` says the attacks were written by the defender). Keep the spotlight and cap defences under test.

**Text sent to a stream cannot be recalled:**
- Risk: the stream sends text before the whole answer is judged. A risky piece missed by `StreamGuard` reaches the page; the page replaces only what it still shows.
- Files: `rag/query/guard.py` (`StreamGuard.feed`, `finish`), `rag/api/main.py` (`stream_request`), `rag/api/static/index.html`
- Current mitigation: hold-back of anything that could start a risky piece; the page renders text with `textContent` (`rag/api/static/index.html`, line 117 comment), not `innerHTML`; no `innerHTML` use was found in the page.
- Recommendations: keep the rule in `CLAUDE.md`; add adaptive streaming tests before changing the hold-back logic.

**Retention of traces that hold document text:**
- Risk: each question's trace is kept in `data/uploads/<doc_id>/chat/` with passages and answers. Traces for documents that are not deleted have no retention rule. Observability tools would send this text off-machine.
- Files: `rag/api/service.py` (`delete` removes the document folder), `rag/query/pipeline.py`, `docs/backlog.md` (Security, Observability)
- Current mitigation: deleting a document removes its folder; the LLM disk cache is not used for uploads (`get_llm(spec, cache_dir=None)`, `CLAUDE.md`).
- Recommendations: set a retention rule; decide self-hosting before sending any trace to Langfuse or LangSmith.

**Secret handling and a key in chat history:**
- Risk: `HANDOFF.md` (section 7) records a Gemini API key that was pasted in chat as "temporary". It should be treated as exposed until rotated.
- Files: `HANDOFF.md`, `.env.example` (committed template, no values), `.env` (gitignored; not read for this map)
- Current mitigation: the key is said to live only in the gitignored `.env`.
- Recommendations: rotate the key in the Google console, then update `.env`. Keep the sensitive-canary hook enabled (`HANDOFF.md` section 7).

**Truncated-answer retry cache key (unverified):**
- Risk: an answer cut off at the token limit was retried (commit `4fc6186`). The retry keys the cache on the budget and server (`rag/common/llm.py`, not read). Whether the cache key covers the budget is stated in the commit message only; the code was not read.
- Files: `rag/common/llm.py` (not read), `rag/query/generate.py`, `rag/experiments/answer.py`
- Current mitigation: cache salt is tested (`HANDOFF.md` section 5).
- Recommendations: confirm against the real model once; the PR #4 fixes were tested only with scripted models.

## Performance Bottlenecks

**Dense search is exact and scores every vector in scope:**
- Problem: `OpenSearchChunkStore(exact=True)` is the default and scores each vector; the in-memory store does exact cosine search over `numpy` arrays in `rag/common/store.py`.
- Files: `rag/common/store.py`, `rag/common/opensearch_store.py`, `rag/README.md` (Step 9)
- Cause: exact search is chosen for parity with the in-memory store. Dense search was about 7x slower than in memory; the HNSW path was never measured.
- Improvement path: measure `exact=False` (HNSW) on the golden set and on latency; move to it if the ranking loss is within noise.

**Latency per question on OpenSearch:**
- Problem: 0.1 to 0.5 seconds per question for retrieval and evaluation, against 0.02 to 0.2 seconds in memory.
- Files: `rag/common/opensearch_store.py`, `rag/README.md` (Step 9)
- Cause: one round trip per search plus per-owner index routing.
- Improvement path: profile with the trace stage timings already recorded (`rag/common/trace.py`) before changing the query shape.

**Upload embedding in batches of 64:**
- Problem: all chunks of a document are embedded before indexing; a large upload holds the single ingestion lock for its whole run.
- Files: `rag/ingestion/index.py`, `rag/api/service.py` (`run_ingestion`, `_ingest_lock`)
- Cause: one embedder on an 8 GB GPU (per `docs/extraction.md`).
- Improvement path: measure a 500-page upload; a percentage shown during embedding is listed in `docs/backlog.md` but not built.

**Polling loop in stream close:**
- Problem: `_close_when_idle` in `rag/api/main.py` sleeps 20 ms in a loop for up to 5 seconds to close a generator a thread still runs.
- Files: `rag/api/main.py` (`_close_when_idle`)
- Cause: a Python generator cannot be closed while a worker runs it.
- Improvement path: signal the worker with a `threading.Event` and wait on it, instead of polling.

## Fragile Areas

**Owner isolation depends on every query path:**
- Files: `rag/api/service.py` (`get`, `_ready_documents`, `_retrieve`, `ask_documents`), `rag/common/opensearch_store.py`, `rag/common/chunk_store.py`
- Why fragile: isolation holds only if every search filters on owner and document ids inside the query (`rag/README.md`, Step 9). A new route that searches without the filter would leak across owners.
- Safe modification: add the filter in the store, never after the search; add a test that a second owner gets 404 and no passages (`CLAUDE.md`).
- Test coverage: owner isolation is tested against both stores (`docs/backlog.md`, Security).

**Chunk ids must be qualified per document:**
- Files: `rag/api/service.py` (upload ingestion), `rag/common/chunk_store.py`, `rag/ingestion/index.py`
- Why fragile: chunk ids must be `<doc_id>:<chunk_id>` and unique within an owner (`CLAUDE.md`). A missed qualification merges chunks from two documents.
- Safe modification: use the qualified form at every creation site; test cross-document deletes (`HANDOFF.md`, verified: cross-embedder delete).

**Streaming and the guard:**
- Files: `rag/query/guard.py` (`StreamGuard`, `_construct_start`, `_echo_start`, `_PARTIAL_ENTITY`), `rag/api/main.py` (`stream_request`, `_sse`)
- Why fragile: a regex edit can release text early. Entity and link detection depends on partial-token positions.
- Safe modification: add a case to the streaming tests for each change; run the injection harness `python -m rag.security.indirect`.
- Test coverage: tests use scripted models; the real model stream was checked once (`HANDOFF.md` section 5).

**Module-level state and locks in the service:**
- Files: `rag/api/service.py` (`_ingest_lock`, `_status_lock`, `_load_lock`, `_create_lock`, `_deleting`, `_running`), `rag/api/main.py` (`build_lock`, `ingest_gate`, `threading.Thread` warm-up)
- Why fragile: the delete and load race is handled by ordering on `_load_lock`; a load that starts later is refused via `_deleting`. Changing lock order can reintroduce the race.
- Safe modification: take locks in the same order as `delete`; add a test that uses an `Event`, not a sleep.

**Sandbox memory and timing:**
- Files: `rag/ingestion/sandbox.py` (`run_limited`, `_child`, `_WindowsJob`), `rag/ingestion/extract.py`
- Why fragile: `max_page_chars` bounds the output, not the work; `page.get_text("dict")` builds the whole page first (`docs/extraction.md`, `docs/backlog.md`). Memory and time limits are the real protection.
- Safe modification: change limits only together with a test on a very dense page; test on Linux before relying on it.

**Question-level abstention:**
- Files: `rag/query/pipeline.py`, `rag/query/generate.py`, `rag/query/prompt.py`
- Why fragile: `SYSTEM_PROMPT` in `rag/query/prompt.py` must stay word for word; golden results and the LLM cache depend on it (`CLAUDE.md`). Edits move every score.
- Safe modification: never edit `SYSTEM_PROMPT`; add uploads only through `DOCUMENT_SYSTEM_PROMPT`.

## Scaling Limits

**Single user, single process:**
- Current capacity: one local owner (`LOCAL_OWNER`); one ingestion at a time (`_ingest_lock`); one embedder on an 8 GB GPU (`docs/backlog.md`, `docs/extraction.md`).
- Limit: concurrent uploads queue; a second user would share one ingestion lock and one GPU.
- Scaling path: Keycloak owners, a task queue for ingestion (`docs/extraction.md`, "Can pages be processed in parallel"), and the API in a container with the tunnel reachable from Docker (`docs/backlog.md`, Running it).

**Page and size caps:**
- Current capacity: 50 MB per upload (`DEFAULT_MAX_UPLOAD_BYTES`), 2000 pages (`DEFAULT_MAX_PAGES`), 20,000,000 characters total (`DEFAULT_MAX_TOTAL_CHARS` in `rag/ingestion/sandbox.py`), 120 seconds per extraction (`DEFAULT_TIMEOUT_SECONDS`). A payload near 100 MB was not tested (`HANDOFF.md` section 5).
- Limit: larger documents fail or are rejected; the time limit can cut a slow but valid book.
- Scaling path: measure extraction time per page on the real machine and raise the caps from measurements.

**Caps on documents per question:**
- Current capacity: 50 documents per request (`doc_ids` `max_length=50`); 20 documents for an about question (`MAX_ABOUT_DOCUMENTS` in `rag/api/service.py`).
- Limit: the about prompt holds every profile, so it grows with the document count.
- Scaling path: summarise profiles, or route by topic, before raising the 20 cap.

## Dependencies at Risk

**PyMuPDF (`pymupdf`) and its font flags:**
- Risk: code detection (60 percent monospaced characters) and superscript handling depend on PyMuPDF span flags (`rag/ingestion/extract.py`, `_block_text`, `_line_text`).
- Impact: a library version change alters which blocks are code, and so the chunk boundaries and golden scores.
- Migration plan: pin the version in `requirements-rag.txt` (currently `pymupdf>=1.24`, a floor only) and rerun `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` after any change.

**Model stack without pins:**
- Risk: `requirements-rag.txt` lists packages with floors; `sentence-transformers` pulls in `torch`.
- Impact: results can change across installs, and the cache of embeddings in `data/processed/index/` may not match a new model.
- Migration plan: pin exact versions and record the embedding model name in the index folder name (`rag/README.md` Step 9 says one documents index per embedding model).

## Missing Critical Features

**Authentication:** no login and no per-client identities for the page, a scraper or an MCP server (`docs/backlog.md`, Security; `docs/mcp_risks.md`).
- Blocks: exposing the API beyond localhost; any shared use.

**OCR and layout analysis:** no handling of tables, figures or scans (`docs/extraction.md`).
- Blocks: scanned documents, questions about tables and figures, and any document that is mostly images.

**Observability and cost totals:** traces hold tokens and stage timings, but there is no price table, no totals per owner, no time to first token, and no tracing tool (`docs/backlog.md`, Cost and observability).
- Blocks: cost control per user; a comparison of cost against quality.

**Stop button and streaming on the about path:** `docs/backlog.md`, UI and API.
- Blocks: stopping a long answer from the page; streaming an about answer.

## Test Coverage Gaps

**Real model and real book not re-run after PR #4:**
- What's not tested: the PR #4 fixes (judge failure isolation, truncated-answer retry, cache salt, reranked injection runs, raw answer for blocked answers) were verified with scripted models only (`HANDOFF.md` section 5).
- Files: `tests/` (not read for this map), `rag/experiments/answer.py`, `rag/query/generate.py`
- Risk: a real model can return a shape the scripted model never produced, so a fix can fail silently in a long run.
- Priority: High

**Scanner on real book text:**
- What's not tested: whether the injection scanner removes any gold chunk on the real DDIA book (`HANDOFF.md` section 6, item 5).
- Files: `rag/query/guard.py` (`scan_chunks`), `rag/observe/retrieval_quality/metrics.py`
- Risk: a false positive removes evidence and lowers `hit@5` without any visible error.
- Priority: High

**Sandbox on Linux and macOS:**
- What's not tested: the `RLIMIT_AS` path (`rag/ingestion/sandbox.py`, `_child`).
- Files: `rag/ingestion/sandbox.py`
- Risk: extraction fails or runs uncapped on a non-Windows host.
- Priority: Medium

**Browser page:**
- What's not tested: the page in a browser (`rag/api/static/index.html`); `textContent` and the streaming replace path are checked only in code.
- Files: `rag/api/static/index.html`, `rag/api/main.py`
- Risk: a rendering or event-handling bug is not caught by the tests.
- Priority: Medium

**Large payloads and mid-stream model failures:**
- What's not tested: payloads near 100 MB; a real vLLM failure in the middle of a stream (`HANDOFF.md` section 5).
- Files: `rag/api/main.py` (`LimitUploadBody`, `stream_request`), `rag/api/service.py`
- Risk: a half-sent stream or a limit that is not enforced under a real load.
- Priority: Medium

**About-the-documents golden set:**
- What's not tested: the six about questions with a judge that is not the generator; the 4 to 6 golden questions of the comparison kind are not written (`docs/backlog.md`).
- Files: `data/golden/about_questions.jsonl`, `data/golden/ABOUT_REVIEW.md`, `rag/experiments/about.py`
- Risk: the about path is accepted without measurement.
- Priority: Low

---

**Unverified in this map:** `rag/common/llm.py`, `rag/common/store.py`, `rag/common/opensearch_store.py`, and the `tests/` folder were not read. The task rules forbid naming `rag/common/llm.py` or `tests/test_vllm.py` and globbing `tests/` or `rag/common/`, and `.env` was never read. Items that depend on them (the LLM cache key, the 502 path, the store filters, the test coverage) are taken from `HANDOFF.md`, `CLAUDE.md`, `rag/README.md` and the docs, not from the code. `HANDOFF.md` was read with a Bash `sed`/`grep`, not the Read tool, per the project note.

---

*Concerns audit: 2026-10-21*
