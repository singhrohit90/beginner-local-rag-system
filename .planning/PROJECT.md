# Local RAG System: Chat Memory

## What This Is

A local, production-style retrieval-augmented generation (RAG) system built to learn by measuring: evaluation and security first, plain-Python orchestration, every answer traceable to the stage that produced it. It ingests PDFs, retrieves with hybrid dense + BM25 search, answers through a guarded LLM path, and serves a chat page and a `/v1` API for a single local owner.

This milestone adds **chat memory**. Today the chat page and the `/v1/ask*` API treat every question as standalone. After this work a user can ask a follow-up ("and how does that compare to the other book?") and get an answer that uses the conversation so far, without the pipeline's single-turn behaviour, scores or prompt changing.

## Core Value

A follow-up question with a pronoun retrieves the passages the standalone phrasing would, while a single-turn question produces exactly the prompt bytes and cached answer it produces today.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. Source: requirements-reconstructed.md "Already done, evidence". -->

- ✓ Modular ingestion and query pipelines, five chunkers, hybrid retrieval (dense + BM25, RRF or weighted), optional cross-encoder rerank — PR #1 (merge 077341f); `rag/ingestion/`, `rag/query/`; `rag/README.md` Steps 1-7
- ✓ Golden set (45 questions) and evaluation layer with fact checklist judge — PR #1; `data/golden/ddia_questions.jsonl`, `rag/observe/`
- ✓ OpenSearch store with per-owner indexes, owner isolation (404 not 403) — 0077194; PR #1; `rag/common/opensearch_store.py`; `tests/test_chunk_store.py`
- ✓ Upload + chat UI, multi-document ask, health light, duplicate detection, upload progress — PR #1; `rag/api/service.py`, `rag/api/main.py`, `rag/api/static/index.html`
- ✓ Streaming with `StreamGuard` (SSE `token`/`final`/`error`) — a4d71c3, 78ddcd7; `rag/query/guard.py`; `tests/test_stream_guard.py` (270 cases), `tests/test_stream_api.py`
- ✓ "About the documents" profile path, `/v1/ask-about` — 1a5f6f2; `rag/ingestion/profile.py`, `rag/query/about.py`; `docs/about_the_documents.md`
- ✓ Extraction sandbox (time and memory limits, bookmark cap) — 52f52fe; `rag/ingestion/sandbox.py`; `tests/test_sandbox.py`
- ✓ Injection defences (scanner, output filter, per-source cap, spotlight option) and harness — 7951117; `rag/security/`; `rag/README.md` Step 7
- ✓ BM25 stemming option and measurement — fe22b9f; `rag/common/stem.py`; `rag/README.md` Step 9
- ✓ Two ultrareview rounds fixed and merged (16 + 6 findings) — PR #2 (adee9be), PR #4 (a53a2e9)
- ✓ CLAUDE.md learnings — PR #3 (651f0ca)
- ✓ Interview notes including the chat-memory design — 22946f7; `interview/05_conversation_memory_and_cost.md` (design only, not built)
- ✓ Model and extraction documentation — `docs/models.md`, `docs/extraction.md`
- ✓ Live golden run after PR #4: correct 0.73, faithful 0.946, 0 canary leaks — `runs/ans__verify_pr4_live/answer_report.json` (gitignored run folder)

### Active

<!-- Current scope: chat memory (R1-R10 of requirements-reconstructed.md). -->

- [ ] R1 Conversation id: `POST /v1/ask`, `/v1/ask/stream`, `/v1/documents/{id}/ask` and `/v1/documents/{id}/ask/stream` accept an optional `conversation_id`; absent, a new conversation is created and its id returned in the response (and in the `final` SSE event); a conversation belongs to the owner from `current_owner`; another owner's id is a 404
- [ ] R2 Server-side history: each turn stores the user's message, the rewritten question (if any), the answer as shown (after the output filter), the document scope and a timestamp; storage lives where a document delete can remove it (`data/uploads/<doc_id>/chat/` for single-document conversations; cross-document conversations under a per-owner folder with the cross-document trace retention rule); no LLM disk cache for anything derived from uploads
- [ ] R3 Rewrite before retrieval: a new `rag/query/rewrite.py` runs in or before `DocumentService._retrieve` (`rag/api/service.py:441`), before `RetrievalPipeline.run`; given the latest message and the last N turns it returns one standalone question keeping the user's constraints, or the message unchanged when already standalone (cheap check first, model second); retrieval runs fresh on the rewritten question; the trace records both texts; errors surface as HTTP statuses before any SSE byte is sent
- [ ] R4 Ambiguity and topic switch: when two readings of a follow-up are equally plausible the system asks one clarifying question instead of guessing; a detected topic switch starts a clean history for the rewrite; named failure modes to test: invented details, dropped constraints, wrong pronoun resolution, an earlier topic leaking into a new question
- [ ] R5 History in the prompt, prompt unchanged for single turns: `build_prompts` (`rag/query/generate.py:51`) gains an optional history block of the last N turns (questions and short answers, not full earlier answers); with no history the prompt is byte-identical to today's
- [ ] R6 History is untrusted: stored turns go through `scan_text` and are shown and reused only after `filter_output`-style defanging (`rag/query/guard.py`); the page renders history with `textContent`; streamed answers still go only through `StreamGuard`
- [ ] R7 Budget: history plus passages plus answer budget (including the reasoning model's 3000 thinking tokens, `docs/models.md`) must fit the context window; this run enforces a hard cap on turns/words per conversation and leaves compaction to a later phase
- [ ] R8 Evaluation: a multi-turn golden set under `data/golden/` (at least a pronoun follow-up, a topic switch, an ambiguous follow-up, a standalone question inside a conversation); retrieval scored on the rewritten query and the answer on the last turn, rewriting on and off, through `rag/experiments/`; rewriting ships on by default only if it shows a gain outside the noise band, otherwise off with the numbers recorded
- [ ] R9 Page: `rag/api/static/index.html` keeps the conversation id across questions, offers "new conversation", and shows the clarifying question (R4) as an ordinary assistant turn
- [ ] R10 Docs and notes: `rag/README.md` (a Step 11), `docs/backlog.md` (mark done, add compaction), and `interview/05_conversation_memory_and_cost.md` relabelled from "designed" to "built" only for what is built and measured

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Any change to `SYSTEM_PROMPT` or `DOCUMENT_SYSTEM_PROMPT` wording — the golden-set results and the LLM cache depend on them word for word (`CLAUDE.md`)
- LangChain or LangGraph — the project is plain-Python orchestration by design (`rag/README.md` "Design decisions"); no new framework
- Client-supplied history — the client sends only the new message and the conversation id; a client-sent history is user-controlled and cannot be trusted (`interview/05_conversation_memory_and_cost.md`)
- Compaction of long histories (rolling summary at about 70% of the history budget) — later roadmap item; this milestone enforces a hard cap instead
- Cost and token totals per request; tracing (Langfuse or LangSmith; self-hosting decision because traces hold document text); tool calling — later roadmap items in the owner's planned order (`docs/backlog.md`)
- Keycloak replacing `current_owner`; the API in Docker — later roadmap items (`docs/auth_plan.md`)
- Stop button; streaming for the about path; tables, images, OCR; HNSW measurement; automatic routing to the about path; the remaining `docs/backlog.md` items — later roadmap items

## Context

- **Brownfield.** The codebase is mapped in `.planning/codebase/` (ARCHITECTURE, STACK, STRUCTURE, CONVENTIONS, TESTING, INTEGRATIONS, CONCERNS; mapped at a53a2e9 on 2026-10-21). Read `rag/README.md` ("Layout" and "Read in this order") before changing code.
- **Architecture.** Two linear pipelines (ingestion, query) joined only by a shared `ChunkStore`; orchestrators choose order, logic lives in step modules; every query writes a `Trace`; stages switched by named `RetrievalConfig`s; multi-tenancy enforced inside the store via `Scope`.
- **Where chat memory plugs in.** `AskRequest` in `rag/api/main.py` has `question`, `config`, `style`. `DocumentService.ask` / `_retrieve` (`rag/api/service.py:437-441`) build a `Scope` and call `RetrievalPipeline.run`, which embeds the question string it is given. `build_prompts` (`rag/query/generate.py:51`) holds the question and passages, never earlier turns. The page keeps a visible log but sends only the new question. Traces for uploads are saved under `data/uploads/<doc_id>/chat/`; cross-document questions are not yet traced (`docs/backlog.md`).
- **Design already written.** `interview/05_conversation_memory_and_cost.md` holds the design: two uses of history (answer prompt and rewrite before retrieval), skip the rewrite when standalone, clarifying question on ambiguity, topic-switch detection, history as untrusted text, multi-turn golden set with rewrite on/off comparison.
- **Model stack.** Default generator `vllm:/models/gpt-oss-20b` (reasoning model, 3000 thinking tokens, through a PuTTY tunnel at `127.22.10.1:30007`, checked with `python -m rag.common.llm_check`); judge `ollama:qwen2.5:7b` (local, fast, weak on about-questions); embedder `all-mpnet-base-v2` (384-token limit).
- **Known concerns** (`.planning/codebase/CONCERNS.md`): owner is a placeholder; chat has no memory; judge scoring is noisy (gaps under about 8 points on 37 questions are noise); prompt-injection defences are a pattern list; text sent to a stream cannot be recalled; retention of traces that hold document text is unresolved; cross-document questions are not traced.
- **Test baseline.** `python -m pytest tests -q`: 591 passed, 2 skipped (593 collected). Retrieval invariant: `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` gives hit@5 0.865, mrr 0.663.
- **Open questions carried into planning.** (1) Cross-document conversation storage: per-owner folder with the cross-document trace retention rule, or refuse history for cross-document scope in phase 1. (2) Which model does the rewrite: the reasoning generator (slow to first token) or the local instruction model (`ollama:qwen2.5:7b`, fast, weaker). (3) N (turns in the rewrite window and in the prompt): start at 6 unless measurement says otherwise.

## Constraints

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

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| History lives server-side per owner; client sends only the new message and a conversation id | Client-sent history is user-controlled and cannot be trusted; owner filter still applies | — Pending |
| Rewrite before retrieval, skipped when the message is already standalone (cheap check first, model second) | Most conversational-RAG failures are retrieval failures from searching the raw follow-up; a needless rewrite costs a call and can distort the question | — Pending |
| History block in the prompt holds questions and short answers, not full earlier answers | Keeps budget small and limits re-exposure of text copied from a poisoned document | — Pending |
| Hard cap on turns/words per conversation now; compaction deferred | Fits the context window without a second summarisation model path in this milestone | — Pending |
| Rewriting ships on by default only if the multi-turn golden set shows a gain outside the noise band | Project rule: add a stage only when measurement shows a gain | — Pending |
| Stored turns are treated as untrusted text (scanned, defanged, rendered with `textContent`) | An earlier answer may carry text from a poisoned document and would return in every later prompt | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-10-21 after initialization*
