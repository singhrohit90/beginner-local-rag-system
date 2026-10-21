# Project Research Summary

**Project:** Local RAG System, chat-memory milestone
**Domain:** Conversational memory (multi-turn chat with query rewriting) added to a brownfield, plain-Python, guarded RAG system
**Researched:** 2026-10-21
**Confidence:** MEDIUM (repo-derived facts HIGH; model behaviour, latency, context window and rewrite quality are unmeasured)

## Executive Summary

This is a brownfield integration, not a new product. Conversational RAG is a standard pattern: keep the history server-side, condense a follow-up into a standalone question before retrieval, retrieve on that question, and put a short history block into the answer prompt. The four researchers agree on how to fit it into this repo with no new dependency and no framework. The rewrite runs in `DocumentService._retrieve` before `RetrievalPipeline.run`, so retrieval code is never edited. New pure helpers go in `rag/query/history.py` and `rag/query/rewrite.py`. All state goes in a new `rag/api/conversations.py` next to the document folders, where a delete already removes things. History enters the user prompt as one delimited block. An empty block returns today's prompt string byte for byte, so `SYSTEM_PROMPT`, the golden results and the LLM cache stay valid.

The recommended approach is to build the safety net first (a prompt-snapshot test committed before any edit, plus the retrieval invariant hit@5 0.865 / mrr 0.663). Then add memory in the answer prompt with the rewrite off. Only then add the rewrite, clarify and topic-switch behaviour behind a switch that defaults to off. The multi-turn golden set decides whether the switch flips. The rewrite model is favoured as the local `ollama:qwen2.5:7b` because the reasoning generator is slow to first token and its thinking tokens can eat a small output budget. That is a lean, not a result, and measurement decides it. The honest expected outcome is that the golden set is too small to show a gain outside the noise band, so "ship off with the numbers recorded" is a likely and acceptable result under the project's own rule.

The main risks are silent drift of the single-turn prompt, history re-exposing poisoned text, the rewriter distorting questions (invented details, dropped constraints, wrong pronoun, topic leak), conversation text outliving a document delete, and an evaluation that cannot separate a gain from noise. Mitigations are mostly deterministic and testable offline with `FakeLLM`: a snapshot test, a regex skip gate, a constraint-preservation and invention check on rewrite output, `scan_text` plus defanging on every stored turn read back, `cache_dir=None` for every service LLM, a delete cascade with an in-flight race test, and an evaluation design with teacher-forced histories and an oracle arm. Three questions the researchers disagree on or leave open are recorded below as open decisions and are not settled here.

## Key Findings

Details: `STACK.md`, `FEATURES.md`, `ARCHITECTURE.md`, `PITFALLS.md` in this folder.

### Recommended Stack

Add zero new dependencies. Chat memory here is a prompt, a regex gate, a file store and a budget check, all in the standard library plus what the repo already installs. No LangChain, no vector or summary memory, no tokenizer package, no database.

**Core technologies:**
- Python stdlib (`json`, `pathlib`, `threading`, `re`, `secrets`, `hashlib`): conversation files, ids, locks, gate regexes, owner folder name. Python 3.10.11, so no `tomllib` and use `datetime.timezone.utc`.
- FastAPI / Pydantic (installed 0.129.0 / 2.12.5): optional `conversation_id` on the ask request models, validated by a strict hex pattern before it becomes a path. Pydantic 2 keyword is `pattern`, not `regex`. Do not upgrade.
- Existing `LLM` interface, always `get_llm(spec, cache_dir=None)` for the rewriter and the service: no new HTTP client, and no upload-derived text in the disk cache.
- `ollama:qwen2.5:7b` as the favoured rewriter, configurable (`RAG_REWRITER` in STACK.md, `RAG_REWRITE_LLM` in ARCHITECTURE.md; pick one name): temperature 0, about 100 output tokens. The generator `vllm:/models/gpt-oss-20b` is unchanged. A `gpt-oss-20b` low-effort arm is kept as an experiment comparison.
- Existing `scan_text` / `filter_output` / `StreamGuard` in `rag/query/guard.py`: reused for stored turns (on write and on read), the rewrite output and any clarifying text. No new rule list.
- Output protocol for the rewriter: one tagged line (`STANDALONE`, `REWRITE:`, `CLARIFY:`, `NEW_TOPIC:`) parsed by regex; anything else falls back. An Ollama JSON-schema `format` is the upgrade only if parse failures are measured high.
- Budget in words with a 1.5 tokens-per-word factor, calibrated once from logged `prompt_tokens`. Worst-case single-turn footprint is about 6,150 tokens (STACK.md arithmetic), and the true `max-model-len` of the on-prem server is not recorded anywhere.

### Expected Features

**Must have (table stakes):**
- Rewrite a pronoun follow-up to a standalone question before retrieval, skipped when the message is already standalone and always on the first turn (R3).
- Conversation id round trip, owner-scoped, with unknown, foreign, malformed and wrong-scope ids all returning the same 404 (R1).
- Server-side history that a document delete removes, stored as shown after the output filter (R2).
- Recent turns in the answer prompt, short answers, single-turn prompt byte-identical (R5).
- Stored history treated as untrusted, rendered with `textContent` (R6).
- A hard cap with a clear message before any SSE byte (R7), and "new conversation" (R9).
- Gaps not in R1-R10 that the researchers recommend adding as small requirements: a `GET` for one conversation so a page reload can resume, per-turn citations kept with each stored turn, a cap-hit message plus turn counter, a per-conversation lock, a scope change starting a new conversation, and an explicit single-conversation delete.

**Should have (competitive):**
- Visible rewritten question, shown in the "what the pipeline saw" panel only, never in the chat bubble (traceability).
- One clarifying question on genuine ambiguity, never two in a row (R4, R9).
- Topic-switch handling that cleans the history window (R4), preferably from the same rewriter call.
- Rewrite on/off measured on a multi-turn golden set with an oracle arm (R8), plus the four named failure-mode tests.

**Defer (v2+):**
- Compaction or rolling summary, cost and token totals, tracing, tool calling, Keycloak.
- Conversation list sidebar, auto-generated titles, suggested follow-up chips, export, branching, cross-conversation memory, vector memory.

### Architecture Approach

Memory is a thin layer in front of the existing query path plus one optional block in the answer prompt. `rag/query/` stays pure (values in, values out, no I/O, no owner), and `rag/api/` holds everything stateful. The five edits to shared code are each a new optional parameter whose empty default returns the old expression. A conversation is bound to the scope it started with, and the page resets its id when the selected documents change. Persist the turn immediately before yielding `final`, on the success path only, so an aborted or failed turn is never stored. `Trace.question` holds the text retrieval ran on, and the original message and rewrite details go in `trace.config["conversation"]`, so the `Trace` dataclass and old trace files are untouched.

**Major components:**
1. `rag/api/conversations.py` (new): ids, paths, owner check, scope binding, cap check, delete cascade. The only module that knows the on-disk layout.
2. `rag/query/history.py` (new): `HistoryTurn`, `window()`, `neutralize()` (scan, defang, strip `[S n]`, truncate), `render_block()`, budget constants.
3. `rag/query/rewrite.py` (new): regex skip gate plus `rewrite_question(llm, message, window) -> RewriteResult`, with deterministic guards on the output. It owns its own system prompt.
4. `rag/api/service.py` `DocumentService._retrieve` (edit): conversation lookup, cap check, window, rewrite, clarify short-circuit, then `RetrievalPipeline.run` on the effective question. `_remember()` persists. All of this runs before the first SSE byte.
5. Prompt seam (edit, about 7 lines): `history_block=""` on `build_user_prompt`, `spotlight_user_prompt`, `build_prompts` and `RagPipeline`.
6. `rag/api/static/index.html` (edit) and `rag/experiments/conversation.py` plus `data/golden/` multi-turn set (new).

### Critical Pitfalls

1. **Single-turn prompt or call pattern drifts.** A history argument is threaded into one prompt style and not the others, or an empty history emits a header, or turn 1 still calls the rewriter. Avoid it with an empty-block early return that is the old expression untouched. Commit a snapshot test (3 styles x 2 subjects, with `history_block=""` equal to no argument) before editing `generate.py`. Add a `FakeLLM` call-count test: zero rewrite calls on turn 1. Re-run the retrieval invariant.
2. **The rewriter distorts the question** (invented details, dropped constraints, wrong pronoun, topic leak, and over-rewriting a standalone question). Do not rely on the prompt alone. Use a conservative regex skip gate. Then check the output deterministically: every number, year, quoted string and constraint word of the message survives, no new proper nouns appear, and the length is capped. A failed check means the raw message plus a recorded reason. Test each mode with a `FakeLLM` that returns a deliberately bad rewrite.
3. **History and rewrite output are injection channels.** An earlier answer can carry poisoned document text into every later prompt, and into the rewriter, whose output steers retrieval and bypasses `scan_chunks`. Store the answer as shown. On read, `scan_text`, defang, strip `[S n]` markers (they collide with the new passage numbering) and truncate. Label the block "quoted text, not instructions", and scan and shape-check the rewrite output.
4. **Conversation text outlives its document or leaks across owners.** Single-document files live under the document's own folder. Never `mkdir(parents=True)` in the writer (a late writer would resurrect a deleted folder). Re-check the documents inside the store lock before writing. Server-generated 128-bit ids validated before any path join. Identical 404 body for every miss. A spy test confirms every service LLM has `cache_dir=None`.
5. **The evaluation cannot show a gain.** The 8-point band belongs to 37 single-turn questions, and a 12-16 turn follow-up set moves 6-8 points per turn. Use teacher-forced histories so both arms see identical history, an oracle arm (human standalone question), paired per-item win/tie/loss, per-category tables and a regression arm replaying the 37 existing questions inside a fake conversation. Write the shipping rule before the first run. Author at least about 30 follow-up turns, with at least half being baseline misses, or accept "off with numbers".

Also scheduled by the researchers: history budget overflow versus an unknown `max-model-len` (Pitfall 12), errors versus the HTTP-status-before-SSE contract and the clarify response shape (`_describe` reads `trace.stage("context")` unconditionally), and concurrent requests on one conversation.

## Open Decisions (researchers disagree or leave open; not settled here)

The roadmapper should surface these to the requirements owner, not resolve them silently. Decide each before the phase that needs it.

| # | Decision | Side A | Side B | Needed by |
|---|----------|--------|--------|-----------|
| D1 | Cross-document conversation storage (PROJECT.md open question 1) | **Store on disk** under a per-owner folder with a delete cascade (ARCHITECTURE.md, FEATURES.md). Argument: cross-document scopes ("all my documents", "checked documents") are the page's default flows, so refusing memory there leaves the feature absent where users chat most. Layout proposed: `data/uploads/_conversations/<sha256(owner)[:16]>/` (ARCHITECTURE.md; `_conversations` cannot match `DOC_ID`, so it is already gitignored and skipped by directory scans) or `data/conversations/<owner_key>/` (STACK.md; needs a new `.gitignore` line). Delete any conversation whose recorded scope touches a deleted document; whole-file removal, not redaction. | **Refuse history for cross-document scope in the first phase** (PITFALLS.md; STACK.md and FEATURES.md accept it as the smaller fallback). Argument: it is the only case a single folder delete cannot cover, there is no cross-document retention rule yet (cross-document asks are not traced today), and it avoids a new delete path and race. The ask still works and returns `conversation_id: null` with a clear message, not a silent ignore. | Phase 2 |
| D2 | Rewrite-failure policy (model server or tunnel down, timeout, empty output) | **Fail-open**: use the raw message, record `fallback`/`rewrite: "unavailable"` in the trace, and show a visible flag on the response and page (STACK.md, PITFALLS.md). Argument: a down second model must not make the chat unusable, and the answer path already needs the tunnel. Count these as failures in experiments, never as "off". | **Fail-closed**: propagate to an HTTP status (502), no silent fallback (ARCHITECTURE.md anti-pattern 8, FEATURES.md). Argument: a silent fallback hides the exact failure being measured, and PROJECT.md R3 says errors surface as HTTP statuses before any SSE byte. | Phase 3 |
| D3 | Stored-turn caps and window numbers | STACK.md: prompt window 6 turns, history block at most 400 words, answers cut to about 40 words, question about 60 words, stored cap about 50 turns, safe even at `max-model-len` 8,192. | ARCHITECTURE.md: window 6 turns, history block 600 words, answers about 60 words, stored cap 20 turns and 8,000 stored words. PITFALLS.md wants 3 named limits (window, per-turn caps with a longer last assistant turn, conversation cap) and an explicit report of dropped turns. | Phase 1 (constants), pinned after `max_model_len` is read |

Smaller disagreements the roadmapper should also carry as open (each has a lean noted in the source file):
- **Question slot in the answer prompt:** rewritten standalone question (STACK.md, ARCHITECTURE.md; the passages were retrieved for it) versus the original message plus the history block (PITFALLS.md; a wrong rewrite would otherwise be invisible). Both texts are recorded, so measure both in Phase 4.
- **Conversation file format:** append-only JSONL under a lock (STACK.md, PITFALLS.md; torn last line loses at most one turn) versus one JSON file rewritten atomically (ARCHITECTURE.md; at most about 20 turns). Under the Windows `PermissionError` retry pattern already in `_atomic_write`, either works; choose once in Phase 2. Use a subfolder `chat/conversations/` in either case, because existing tests glob `chat/*.json` for traces.
- **Conversation id shape:** 32 hex (STACK.md, ARCHITECTURE.md, PITFALLS.md using `secrets.token_hex(16)`) versus FEATURES.md's illustration of 12 hex. Take 32 hex.
- **Reload-resume `GET`:** FEATURES.md calls it the largest functional gap in R1-R10; ARCHITECTURE.md says do not add a history route this milestone. Decide whether R9 includes reload-resume.
- **Concurrent requests on one conversation:** PITFALLS.md rejects the second with 409 before any SSE byte (lock held across streaming); ARCHITECTURE.md uses a store lock around the write only and accepts that a later turn's window may miss an earlier one.
- **Default rewrite model:** ARCHITECTURE.md defaults the seam to the service LLM until measured; STACK.md, FEATURES.md and PITFALLS.md say the reasoning generator should not be the default rewriter. This is decided by measurement in Phase 4 (latency and rewrite quality), and the seam is built in Phase 3.
- **Whether `keep_traces=False` should gate conversation files:** ARCHITECTURE.md recommends no (history is functional state) and flags it to the requirements owner.

## Implications for Roadmap

Proposed scope is R1-R10 only. Five phases. Dependencies: the safety net comes before any shared function is edited; `history.py` comes before both the store and the rewriter; the store and the rewriter are independent of each other; service integration needs all three; evaluation needs only `history.py` and `rewrite.py` and gates the default; the page needs the API contract; docs come last.

### Phase 1: Safety net and prompt seam
**Rationale:** Everything else edits shared code. The snapshot test must exist on current code before the first edit, or drift is undetectable. `history.py` is needed by every later piece.
**Delivers:** Committed `build_prompts` snapshot test (standard, spotlight, naive x both subjects x zero, single-page and page-range passages; `history_block=""` equals no argument). Recorded retrieval-invariant output (hit@5 0.865 / mrr 0.663). `rag/query/history.py` (`HistoryTurn`, `window`, `neutralize`, `render_block`, budget constants). The `history_block=""` parameter on `build_user_prompt`, `spotlight_user_prompt`, `build_prompts` and `RagPipeline`. A worst-case budget test. One command to read the server's `max_model_len` into `docs/models.md`.
**Addresses:** R5, R6 (read-time neutralization, unit-level), R7 (constants and budget test).
**Avoids:** Pitfall 1 (prompt drift), Pitfall 4 (stale `[S n]`, defanged history), Pitfall 12 (overflow).

### Phase 2: Conversation store and memory in the answer prompt (rewrite off)
**Rationale:** Memory must work and be safe before the rewriter exists, so the rewriter can be measured against a working baseline. Owner, delete and error semantics are the hard security part and belong early.
**Delivers:** `rag/api/conversations.py` (server-generated 32-hex id, strict regex, owner check, scope binding, identical 404, cap check returning 409 before any model call, delete cascade). `conversation_id` on all four ask routes (`AskRequest` and `AskAcrossRequest` are separate models) and in `final`. `_retrieve` steps for lookup, cap, window and history block. `_remember()` persisting only on the success path before `final`. `trace.config["conversation"]` block. Typed exceptions mapped in `guarded()`. Page id plumbing and "New conversation" (the id part of R9).
**Addresses:** R1, R2, R5 (end to end), R6, R7 (hard cap), the table-stakes gaps (cap message, per-turn citations, per-conversation lock, scope change resets, explicit delete if accepted).
**Avoids:** Pitfall 5 (owner and enumeration), Pitfall 6 (delete leaves text or resurrects the folder; includes the in-flight delete race test), Pitfall 7 (cache leak; `get_llm` spy test), Pitfall 8 (concurrency), Pitfall 9 (errors before SSE), Pitfall 19 (Windows file handling). Depends on open decisions D1 and D3.

### Phase 3: Rewrite, clarify and topic switch behind a switch (default off)
**Rationale:** Implementing the rewriter with its deterministic guards, before any quality claim, keeps it testable offline. Golden-set authoring must start here, before the prompt is tuned, to avoid tuning to your own examples.
**Delivers:** `rag/query/rewrite.py` (regex skip gate, tagged one-line protocol, constraint-preservation, invention, length and `scan_text` checks, `allow_clarify=False` after a clarification). `rewrite` / `rewrite_llm` service wiring with a configurable rewriter spec (one name, one switch for rewrite plus clarify plus topic switch). The clarify short-circuit that returns the normal event contract (`passages: []`, `citations: []`, `abstained: false`, `kind: "clarify"`, a `_describe` branch that does not read `trace.stage("context")`). `rewrite_ms` timing in the trace config. Multi-turn golden item authoring begins, with the shipping rule written down.
**Addresses:** R3, R4, rewritten question in the response and pipeline panel.
**Avoids:** Pitfalls 2, 3, 9, 13, 14, 15, 20. Depends on open decision D2.

### Phase 4: Multi-turn evaluation and the default decision
**Rationale:** The project rule is to add a stage only when measurement shows a gain. This phase produces the evidence and sets the default.
**Delivers:** `data/golden/` multi-turn set (each item: fixed prior turns, message, human `standalone`, PDF gold pages, category, `expect`, `must_contain` / `must_not_contain`; human review file) with its own loader (`load_golden` rejects unknown keys). `rag/experiments/conversation.py` with arms off, on and oracle (plus concatenation baseline), teacher-forced histories, paired win/tie/loss, per-category tables, a regression arm on the 37 existing questions, separate scoring for clarify and gate recall, latency p50/p95. Decision on rewriter model, question slot, and the default of the switch, with numbers recorded in `runs/`.
**Addresses:** R8.
**Avoids:** Pitfalls 10, 11, 7 (experiment cache keys include rewriter spec, prompt version, message and the exact window).

### Phase 5: Page polish, docs and honest relabelling
**Rationale:** The page depends on a stable API and the clarify shape; docs must follow only what was built and measured.
**Delivers:** Clarify bubble as an ordinary assistant turn; stale-id 404 handling; superseded-stream handling on "New conversation"; "searching for" line via `textContent`; cap message and counter; optional reload-resume. `rag/README.md` Step 11, `docs/backlog.md` (mark done, add compaction and retention), `interview/05_conversation_memory_and_cost.md` relabelled for built and measured items only.
**Addresses:** R9 (rest), R10.
**Avoids:** Pitfall 23 (overclaiming), the stale-id and superseded-stream UX traps. The page has no automated test, so a manual browser pass is a verification step.

### Phase Ordering Rationale

- The snapshot test and retrieval run have no dependencies and de-risk every later edit, so they are Phase 1.
- Memory without the rewrite (Phase 2) is deliverable and demonstrable on its own, and gives the experiment a working baseline.
- The rewrite is a switchable stage (Phase 3), so a bad measurement in Phase 4 turns it off without removing code.
- Golden-set authoring overlaps Phase 3 deliberately, so the rewriter is not tuned to its own examples.
- Phases 2 and 3 are independent after Phase 1 (separate files), except `service.py`, which should be edited in one worktree. This matches the flow convention of creating worktrees from the feature branch yourself.

### Research Flags

Phases likely needing deeper research during planning (`/gsd-plan-phase --research-phase <N>`):
- **Phase 3:** Unmeasured model behaviour (qwen2.5:7b constraint dropping and parse-failure rate, Ollama default context and silent front-truncation, `keep_alive`), and whether `OllamaLLM` sets `num_ctx` / `temperature` (the provider file is hook-flagged and was not read). Clarify threshold design is the hardest part and has only abstract-level literature.
- **Phase 4:** Golden-set size and statistical design (the noise band must be recomputed from n; about 30 follow-up turns needed), judge choice (the rewriter and judge would both be `qwen2.5:7b`), and the shipping rule.
- **Phase 2:** Light research only, on open decisions D1 and D3 and on the `GET`/lock choices. Mostly a decision task, not an information task.

Phases with standard patterns (skip research-phase):
- **Phase 1:** snapshot test, optional parameters with identity defaults, pure helpers; all in-repo patterns.
- **Phase 5:** page edits follow existing `textContent` and SSE conventions; docs follow R10.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | Zero-dependency choice and installed versions are HIGH (read from the repo). Ollama and model-card facts are MEDIUM (official pages, not run against the user's servers). Latency, the rewriter's quality and the 8 GB GPU context default are unmeasured. The `OllamaLLM` provider file was not read. |
| Features | MEDIUM | R1-R10 mapping is HIGH. Rewrite-before-retrieval is cross-checked (LlamaIndex and LangChain agree). Product UX claims (ChatGPT, Copilot, NotebookLM) and clarification literature are LOW (single help pages, abstracts). |
| Architecture | HIGH for integration points, MEDIUM for numbers | Integration points read from the source at a53a2e9. Budgets and the rewrite protocol are proposals to be measured. The model's context window is not recorded in the repo (LOW). |
| Pitfalls | MEDIUM-HIGH | Repo-derived pitfalls are HIGH; general conversational-RAG failure modes are MEDIUM (secondary sources). The cache-key claims were not verified (provider module not read). The over-rewrite checks are this research's design, not a published method (LOW). |

**Overall confidence:** MEDIUM

### Gaps to Address

- **Server `max-model-len`:** not recorded anywhere; one `GET /v1/models` or `python -m rag.common.llm_check` fixes the history cap. Do in Phase 1 and write it into `docs/models.md`.
- **Provider behaviour:** whether `OllamaLLM` sets `num_ctx`, `keep_alive`, `temperature`, and what the disk-cache key includes. Read it by exact path only if the user lifts the hook, or ask the user. Test the cache behaviour with a spy instead of assuming it.
- **Open decisions D1-D3 and the smaller disagreements** above: need the requirements owner.
- **Golden-set power:** with 37 answerable questions one question is 2.7 points; a multi-turn set of 12-16 follow-ups cannot clear an 8-point band. Plan Phase 4 authoring effort (about 30 follow-up turns) or accept "off with numbers".
- **Same-model correlation:** rewriter and judge are both `qwen2.5:7b`; re-score a borderline result with a different judge before flipping the default.
- **Latency and GPU contention:** the rewrite adds a call before the first token; a 4.4 s first-token time was measured on one question only. Measure in Phase 4 with `rewrite_ms`.
- **Retention beyond delete:** no TTL for conversations of documents that are never deleted; keep it as the same backlog item as trace retention. Also flag that conversation files put answer text on disk even when `keep_traces=False`.
- **Existing test fallout:** `test_the_streamed_response_equals_the_ordinary_one` must ignore `conversation_id`; the new id shape must not break the `chat/*.json` trace-count assertions.

## Sources

### Primary (HIGH confidence)
- Repo: `.planning/PROJECT.md`, `.planning/codebase/*`, `interview/05_conversation_memory_and_cost.md`, `docs/models.md`, `docs/backlog.md`, `rag/api/main.py`, `rag/api/service.py`, `rag/query/pipeline.py`, `rag/query/generate.py`, `rag/query/prompt.py`, `rag/query/guard.py`, `rag/query/select_context.py`, `rag/security/defenses.py`, `rag/common/trace.py`, `rag/api/static/index.html`, `rag/observe/golden.py`, `requirements-rag.txt`, `.gitignore`; installed versions from `pip list` and `ollama --version`.

### Secondary (MEDIUM confidence)
- Ollama docs (context length, structured outputs); gpt-oss-20b and Qwen2.5-7B-Instruct model cards; vLLM recipe page (an example uses `--max-model-len 8192`).
- LlamaIndex Condense Plus Context chat engine and LangChain `create_history_aware_retriever` docs (agree on the condense-then-retrieve pattern).
- CORAL (NAACL 2025 Findings, arXiv 2410.23090); arXiv 2603.10524 (secondary summary); "Not what you've signed up for" (arXiv 2302.12173); Hidden in Memory: Sleeper Memory Poisoning (ICML 2026).

### Tertiary (LOW confidence, needs validation)
- ElevenLabs engineering blog (rewrite step over 80% of RAG latency); arXiv 2509.19700 (rewriting helps on TopiOCQA, can hurt on QReCC; snippet only); TopiOCQA / QReCC / ChatRAG-Bench dataset statistics (sources disagree).
- Clarification-versus-answering abstracts (arXiv 2605.25284, 2605.25831); NotebookLM, ChatGPT and Copilot help pages and forum threads; Open WebUI follow-up docs; Akto memory-poisoning blog.
- Blog and forum posts on Ollama silent truncation and the `/v1` versus `/api/chat` `num_ctx` behaviour (sources disagree on the default 2048 versus 4096; verify with `ollama ps`).

---
*Research completed: 2026-10-21*
*Ready for roadmap: yes*
