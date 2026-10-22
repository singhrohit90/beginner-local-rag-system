# Roadmap: Local RAG System

## Overview

This milestone adds chat memory to a working, guarded local RAG system. Today every question is standalone. The journey has five phases. First, pin single-turn behaviour (prompt bytes, retrieval numbers, test baseline) so no later edit can drift it silently. Second, add a server-side conversation store and put a short history block in the answer prompt, with the rewrite off, so memory works and is safe (owner isolation, delete cascade, untrusted history, hard cap) before anything is tuned. Third, add rewrite-before-retrieval, one clarifying question and topic-switch handling behind a single switch that defaults to off. Fourth, measure rewriting on and off on a multi-turn golden set and let the numbers set the default, which may honestly be "off with the numbers recorded". Fifth, make the chat page use conversations and record in the docs only what was built and measured.

Core value: a follow-up question with a pronoun retrieves the passages the standalone phrasing would, while a single-turn question produces exactly the prompt bytes and cached answer it produces today.

Scope is the 18 v1 requirements in `.planning/REQUIREMENTS.md`. v2 items stay out of the phases. Work stays on the existing `flow/chat-memory` branch (no phase branches, no pushes).

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Safety net and prompt seam** - Pin single-turn prompts, retrieval numbers and the test baseline before any shared function is edited
- [ ] **Phase 2: Conversation store and memory in the answer prompt** - Owner-scoped, deletable server-side history that the answer prompt uses, rewrite off
- [ ] **Phase 3: Rewrite, clarify and topic switch** - Standalone-question rewrite before retrieval, one clarifying question, clean history on a topic switch, behind a default-off switch
- [ ] **Phase 4: Multi-turn evaluation and the default decision** - Multi-turn golden set and an on/off/oracle experiment that sets the rewrite default
- [ ] **Phase 5: Chat page and honest docs** - Page keeps and resets the conversation, shows clarifying questions, and the docs describe only what was built and measured

## Phase Details

### Phase 1: Safety net and prompt seam

**Goal:** As a system owner, I want to pin single-turn prompts and retrieval numbers with a committed snapshot test and recorded invariants before any shared function is edited, so that every later change can prove a plain question still produces the same prompt bytes, the same hit@5 0.865 and the same mrr 0.663.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: PRMT-02
**Success Criteria** (what must be TRUE):
  1. A snapshot test, committed on the unedited prompt code before any prompt builder is touched, fixes the exact prompt bytes for the three prompt styles (standard, spotlight, naive), both subjects (the book collection and a single uploaded document), and zero-, single-page and page-range passages, plus the golden-set questions.
  2. After the seam edits, the prompt builders called with an explicitly empty history return exactly the same bytes as when called with no history argument, and both equal the committed snapshot (an empty history adds no header and no blank line).
  3. `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` still prints hit@5 0.865 and mrr 0.663, and `python -m pytest tests -q` still reports 591 passed, 2 skipped; both results are recorded for later phases to compare against.
  4. The model server's context window (`max_model_len`) is read once and written into `docs/models.md`, so the history caps pinned in Phase 2 rest on a recorded number, not a guess.

**Plans:** 7 plans

Plans:
**Wave 1**
- [ ] 01-01-PLAN.md — Snapshot of single-turn prompt bytes (24 cases + 45 golden digests) committed on unedited code; retrieval invariant run 1 (wave 1)
- [ ] 01-02-PLAN.md — Read max_model_len once and record it (or the dated not-read reason and 8192 floor) in docs/models.md and STATE.md (wave 1)

**Wave 2** *(blocked on Wave 1 completion)*
- [ ] 01-03-PLAN.md — history_block seam through the four prompt builders and RagPipeline.answer/stream, empty default byte-identical (wave 2)
- [ ] 01-05-PLAN.md — Pure rag/query/history.py: HistoryTurn, window, neutralize, render_block, D-10 budget constants (wave 2)

**Wave 3** *(blocked on Wave 2 completion)*
- [ ] 01-04-PLAN.md — Seam tests: empty == no argument == snapshot, block position in every style, pipeline forwarding (wave 3)

**Wave 4** *(blocked on Wave 3 completion)*
- [ ] 01-06-PLAN.md — History unit tests and the worst-case context-window budget test (wave 4; after 01-04 so their fail-first checkouts never overlap)

**Wave 5** *(blocked on Wave 4 completion)*
- [ ] 01-07-PLAN.md — Retrieval invariant run 2, full suite, phase prohibition checks, baseline recorded for Phase 2 (wave 5)

Scope note (not a criterion): this phase also lands the pure history helpers (window, neutralize, render) and the budget constants as unwired groundwork. The requirements that use them (history in the prompt, untrusted history, budget) are verified end to end in Phase 2.

**Open decisions**: D3 (constants raised here, pinned after `max_model_len` is recorded)

### Phase 2: Conversation store and memory in the answer prompt

**Goal:** As a chat user, I want to ask a follow-up inside a conversation that the server remembers for me, so that the answer uses my earlier turns while my history stays private to me, disappears with its document, and fits the model's context window.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: CONV-01, CONV-02, CONV-03, CONV-04, PRMT-01, PRMT-03, PRMT-04
**Success Criteria** (what must be TRUE):
  1. Asking without a `conversation_id` on each of the four ask routes (all documents, one document, each with and without streaming) returns a new id in the response body and in the `final` SSE event; asking again with that id answers using the earlier turns, and the saved trace shows a history block of at most the last N turns with questions and shortened earlier answers, while a first turn's prompt is unchanged from Phase 1's snapshot.
  2. Another owner's id, an unknown id, a malformed id and an id from a different document scope all return the same 404 body (never 403), decided inside the store lookup before any model call; each turn stores the user message, the rewritten question if any, the answer as shown after the output filter, the document scope and a timestamp.
  3. Deleting a document removes the conversation history that lived under it, including a delete that races an in-flight turn (the deleted folder is not recreated); cross-document scope behaves as open decision D1 resolves (stored under a per-owner folder and removed when any document in its scope is deleted, or refused with a clear message), never silently dropped or silently kept; no service LLM uses the disk cache (a spy test shows `cache_dir=None` for every one).
  4. A stored turn that contains an injected instruction or a stale `[S n]` citation marker reaches the next prompt only after scanning and defanging, with the markers stripped, and streamed answers still reach the client only through `StreamGuard`.
  5. A conversation that reaches the turn or word cap is refused with a clear error status before any model call and before any SSE byte, and a worst-case budget test shows history plus passages plus the 3000 thinking tokens plus the answer budget fits the recorded context window.

**Plans:** 9 plans

Plans:
**Wave 1**
- [ ] 02-01-PLAN.md — Phase 1 contract check, P2_BASE record, context window in force for Phase 2 (docs/models.md, STATE.md) (wave 1)

**Wave 2** *(blocked on Wave 1 completion)*
- [ ] 02-02-PLAN.md — rag/query/history.py: THINKING_TOKENS, ANSWER_TOKENS, CONVERSATION_MAX_STORED_WORDS, estimate_prompt_tokens, fits_context, block_turns (wave 2)

**Wave 3** *(blocked on Wave 2 completion)*
- [ ] 02-03-PLAN.md — rag/api/conversations.py store: D-01 checkpoint (auto owner-folder), owner/scope lookup, lease, caps, atomic writes, delete cascade (wave 3)

**Wave 4** *(blocked on Wave 3 completion)*
- [ ] 02-04-PLAN.md — Wire service.py and main.py: conversation_id on four routes, history block, stored turns, 404/409 mappings, delete under the store lock, budget refusal (wave 4)

**Wave 5** *(blocked on Wave 4 completion; the test plans 02-05 to 02-08 run one per wave because each fail-first proof checks rag/ files out in the shared working tree)*
- [ ] 02-05-PLAN.md — tests/test_api.py: history window in the trace, one 404 for every miss, 512/513 limit, delete cascade, duplicate ids (wave 5)

**Wave 6** *(blocked on Wave 5 completion)*
- [ ] 02-06-PLAN.md — tests/test_stream_api.py: id on all four routes, separate conversations, errors before any SSE byte, stored streamed answer (wave 6)

**Wave 7** *(blocked on Wave 6 completion)*
- [ ] 02-07-PLAN.md — tests/test_conversations.py (new): turn record, stale reads, traces off, cascade, prompts with history, defang, no disk cache (wave 7)

**Wave 8** *(blocked on Wave 7 completion)*
- [ ] 02-08-PLAN.md — tests/test_conversations.py: delete races, busy conversation, lease release paths, caps, oversize follow-up, worst-case budget (wave 8)

**Wave 9** *(blocked on Wave 8 completion)*
- [ ] 02-09-PLAN.md — Phase gate: full suite, retrieval invariant, snapshot, prohibition checks; Phase 2 baseline and D-11 owner flag in STATE.md (wave 9)

**Open decisions**: D1 (cross-document storage), D3 (cap and window numbers); smaller points listed under Open Decisions below.

### Phase 3: Rewrite, clarify and topic switch

**Goal:** As a chat user, I want to ask a follow-up with a pronoun and have it turned into a standalone question before retrieval (or get one clarifying question when it is ambiguous), so that retrieval finds the passages the full phrasing would find.
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: RWR-01, RWR-02, RWR-03, RWR-04
**Success Criteria** (what must be TRUE):
  1. With the rewrite switch on, the first turn of a conversation makes no rewrite call and an already-standalone later message passes through unchanged with no model call (a call-count test with a fake model proves both); the switch ships off.
  2. A pronoun follow-up such as "and how does that compare to the other book?" is rewritten into one standalone question that keeps the user's constraints, retrieval runs fresh on the rewritten text, and the saved trace records both the original message and the rewritten text.
  3. A rewrite failure (model server down, timeout, empty or malformed output) is visible to the caller and never silent, following open decision D2: an HTTP status before any SSE byte, or a flagged fall-back to the raw message.
  4. An ambiguous follow-up returns exactly one clarifying question through the normal response and SSE shape (no passages, no citations, not abstained), and an ambiguous message right after a clarification never produces a second clarification in a row.
  5. A topic switch starts a clean history for the rewrite, and four deliberately bad fake rewrites (invented details, dropped constraints, wrong pronoun resolution, an earlier topic leaking into a new question) are each caught by a test and fall back to the raw message with a recorded reason.

**Plans:** 8 plans

Plans:
**Wave 1**
- [ ] 03-01-PLAN.md — P3_BASE record, Phase 2 contract check, rag/query/rewrite.py: gate, rewriter prompts, one-line parser, guards, total rewrite_question (wave 1)
- [ ] 03-02-PLAN.md — rag/api/conversations.py: optional kind "clarify" and topic_start on a stored turn, since_topic_start (wave 1)
- [ ] 03-03-PLAN.md — data/golden/conversations_draft.jsonl: eight draft multi-turn rows marked pending-human for owner review (wave 1)

**Wave 2** *(blocked on Wave 1 completion)*
- [ ] 03-04-PLAN.md — Wire service.py and main.py behind RAG_REWRITE/RAG_REWRITER: rewrite before retrieval, visible fallback, clarify short-circuit, topic window, .env.example (wave 2)
- [ ] 03-05-PLAN.md — tests/test_rewrite.py (new): gate table, prompt, parser, guards, four named bad rewrites, known limit, failure codes, totality (wave 2)

**Wave 3** *(blocked on Wave 2 completion; the service test plans run one per wave because their fail-first proofs check rag/ files out)*
- [ ] 03-06-PLAN.md — tests/test_rewrite_api.py (new): call counts, switch and settings, retrieval on the rewrite, visible fallback before any SSE byte, real Ollama client (wave 3)

**Wave 4** *(blocked on Wave 3 completion)*
- [ ] 03-07-PLAN.md — tests/test_rewrite_api.py: clarify shape, never two in a row, topic switch clean history, four named bad rewrites through the service (wave 4)

**Wave 5** *(blocked on Wave 4 completion)*
- [ ] 03-08-PLAN.md — Phase gate: full suite, retrieval invariant, prompt fingerprint, prohibition checks; Phase 3 baseline, D2 resolved and owner flag in STATE.md (wave 5)

**Open decisions**: D2 (rewrite-failure policy); rewriter model seam and switch name (see Open Decisions below).

### Phase 4: Multi-turn evaluation and the default decision

**Goal:** As a system owner, I want to measure rewriting on and off against a multi-turn golden set, so that rewriting becomes the default only when it shows a gain outside the noise band and the numbers are recorded either way.
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: EVAL-01, EVAL-02, EVAL-03
**Success Criteria** (what must be TRUE):
  1. A multi-turn golden set under `data/golden/` holds at least a pronoun follow-up, a topic switch, an ambiguous follow-up and a standalone question inside a conversation, each with fixed prior turns, a human-written standalone question and PDF gold pages; its own loader reads it and rejects unknown keys, and `load_golden` is unchanged.
  2. One command under `rag/experiments/` prints, for the arms rewrite off, rewrite on and oracle (the human standalone question), retrieval scored on the rewritten query and the answer scored on the last turn with the per-question fact checklist judge, using identical teacher-forced histories per arm, with paired win/tie/loss and per-category tables.
  3. The shipping rule (what counts as a gain outside the noise band recomputed for this set's size) is committed before the first scored run, and the run's numbers are recorded in a committed file in the repo (the `runs/` folder is gitignored).
  4. The rewrite switch's default follows the rule: on only if the gain clears the band, otherwise off with the numbers recorded; the rewriter model and the question slot in the answer prompt are decided from the recorded latency and quality numbers.
  5. Replaying the existing 37 answerable questions as first turns of a conversation with rewriting on gives the same retrieval as with it off, and hit@5 0.865 / mrr 0.663 on the single-turn command are unchanged.

**Plans:** 10 plans

Plans:
**Wave 1**
- [ ] 04-01-PLAN.md — Phase 1-3 contract check, P4_BASE, rag/observe/golden_conversations.py: schema, validation, GoldQuestion adapter, page-check CLI (wave 1)
- [ ] 04-02-PLAN.md — docs/chat_memory_eval.md: the shipping rule committed alone before any scored run (wave 1)

**Wave 2** *(blocked on Wave 1 completion)*
- [ ] 04-03-PLAN.md — rag/experiments/conversation.py part 1: four arms on teacher-forced histories, strict scoring, rewrite and clarify scoring, regression arm, rule guard, preflight, --check-set (wave 2)

**Wave 3** *(blocked on Wave 2 completion)*
- [ ] 04-04-PLAN.md — rag/experiments/conversation.py part 2: paired stats, sign test, evaluate_rule, repeats, fact-checklist answers, rewriter choice, render_results (wave 3)

**Wave 4** *(blocked on Wave 3 completion)*
- [ ] 04-05-PLAN.md — data/golden/ddia_conversations.jsonl and MULTITURN_REVIEW.md: author, page-check, rule-first checkpoint, --check-set discrimination, freeze (wave 4)

**Wave 5** *(blocked on Wave 4 completion)*
- [ ] 04-06-PLAN.md — tests/test_golden_conversations.py: reject table, edges, load_golden unchanged, committed set (wave 5)

**Wave 6** *(blocked on Wave 5 completion)*
- [ ] 04-07-PLAN.md — tests/test_conversation_experiment.py: offline smoke, arms, history, tables, fallback, clarify, answers, rule table, guard, regression (wave 6)

**Wave 7** *(blocked on Wave 6 completion)*
- [ ] 04-08-PLAN.md — Live scored run (qwen, gpt-oss comparison if the tunnel is up), Results committed below the rule, STATE.md blocker for skipped arms (wave 7)

**Wave 8** *(blocked on Wave 7 completion)*
- [ ] 04-09-PLAN.md — Apply the decision: default-matches-decision and rewriter-choice tests; flip, rewriter default or question slot only if the Results require it (wave 8)

**Wave 9** *(blocked on Wave 8 completion)*
- [ ] 04-10-PLAN.md — Phase gate: full suite, retrieval invariant, regression replay, rule-first check, prohibitions; Phase 4 baseline and owner flag in STATE.md (wave 9)

Scope note (not a criterion): golden-item authoring starts during Phase 3 on purpose, so the rewriter is not tuned to its own examples; the set is complete and loaded here.

**Open decisions**: question slot in the answer prompt and default rewriter model (decided here by measurement).

### Phase 5: Chat page and honest docs

**Goal:** As a chat user, I want to keep one conversation going in the browser page and start a fresh one when I choose, so that follow-ups and clarifying questions work where I chat and the project docs describe only what was built and measured.
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: PAGE-01, PAGE-02, DOCS-01
**Success Criteria** (what must be TRUE):
  1. In the browser, a follow-up typed after an answer is answered with the earlier turns because the page keeps the conversation id across questions; "New conversation" and a change of the selected documents each make the next question start a fresh conversation (no id sent).
  2. When the server answers 404 for the page's stored id (stale, deleted or foreign), the next question starts a new conversation on its own and the user is not left with an error to clear by hand.
  3. A clarifying question appears in the chat log as an ordinary assistant turn, rendered with `textContent` (a clarification containing markup shows as literal text, not as HTML).
  4. `rag/README.md` has a Step 11 for chat memory; `docs/backlog.md` marks chat memory done and adds compaction and conversation retention; `interview/05_conversation_memory_and_cost.md` is relabelled from "designed" to "built" only for what was built and measured, with the recorded numbers, and anything unbuilt keeps its "designed" label.

**Plans**: TBD
**UI hint**: yes

Scope note (not a criterion): the page has no automated test, so a manual browser pass covers the first three criteria at the end of the phase.

## Open Decisions

Not settled. Resolve each in `/gsd-discuss-phase` for the phase that needs it, with the requirements owner. Source: `.planning/research/SUMMARY.md`.

| # | Decision | Option A | Option B | Resolve in |
|---|----------|----------|----------|------------|
| D1 | Cross-document conversation storage | Store on disk under a per-owner folder, with a delete cascade that removes any conversation whose scope touches a deleted document (layout `data/uploads/_conversations/<owner key>/` or `data/conversations/<owner key>/`) | Refuse history for cross-document scope in this milestone: the ask still works and returns `conversation_id: null` with a clear message, not a silent ignore | Phase 2 |
| D2 | Rewrite-failure policy (server or tunnel down, timeout, empty output) | Fail-open: use the raw message, record `fallback` in the trace, show a visible flag; count as failure in experiments, never as "off" | Fail-closed: surface an HTTP status (502) before any SSE byte, no silent fall-back | Phase 3 |
| D3 | Stored-turn caps and window numbers | Window 6 turns, history block at most 400 words, answers cut to about 40 words, question about 60 words, stored cap about 50 turns | Window 6 turns, history block 600 words, answers about 60 words, stored cap 20 turns and 8,000 stored words; also named limits for window, per-turn caps and conversation cap with dropped turns reported | Phase 1 raises it, Phase 2 pins it after `max_model_len` is recorded |

Smaller points, each with the research lean, to settle in the phase named:

- **Conversation file format (Phase 2):** append-only JSONL under a lock, or one JSON file rewritten atomically; either goes in the subfolder `chat/conversations/` so existing `chat/*.json` trace counts are unchanged.
- **Concurrent requests on one conversation (Phase 2):** reject the second with 409 before any SSE byte (lock held across streaming), or lock only the write and accept that a later window may miss an earlier turn.
- **Conversation files when `keep_traces` is off (Phase 2):** research leans to keep them (history is functional state); flag to the owner.
- **Conversation id shape (Phase 2):** research recommends 32 hex from `secrets.token_hex(16)`, validated by a strict pattern before it becomes a path.
- **Rewriter model and its setting name (Phase 3 seam, Phase 4 decision):** local `ollama:qwen2.5:7b` is the lean over the reasoning generator (slow to first token); pick one setting name (`RAG_REWRITER` or `RAG_REWRITE_LLM`).
- **Question slot in the answer prompt (Phase 4):** the rewritten question, or the original message plus the history block; both texts are recorded, so measure both.
- **Reload-resume `GET` for one conversation:** not in v1 (listed as a v2 item in REQUIREMENTS.md); revisit only if the owner moves it in.

## Planning Notes

- **Research flags:** Phase 3 and Phase 4 warrant `--research-phase` (unmeasured rewriter behaviour, Ollama context and truncation, golden-set power and the shipping rule). Phase 2 needs light research only (D1, D3, lock choices). Phases 1 and 5 use in-repo patterns.
- **Parallelism:** after Phase 1, the conversation store and `rewrite.py` are separate files and can be built in separate worktrees cut from `flow/chat-memory`; `rag/api/service.py` must be edited in one worktree.
- **Expected outcome to plan for:** the golden set is probably too small to clear the noise band, so "rewrite ships off with the numbers recorded" is a likely and acceptable result under the project's own rule.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Safety net and prompt seam | 0/TBD | Not started | - |
| 2. Conversation store and memory in the answer prompt | 0/TBD | Not started | - |
| 3. Rewrite, clarify and topic switch | 0/TBD | Not started | - |
| 4. Multi-turn evaluation and the default decision | 0/TBD | Not started | - |
| 5. Chat page and honest docs | 0/TBD | Not started | - |
