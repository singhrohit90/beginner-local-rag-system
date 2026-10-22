# Phase 3: Rewrite, clarify and topic switch - Context

**Gathered:** 2026-10-22
**Status:** Ready for planning
**Mode:** `--auto` (every gray area took the recommended option; each pick is recorded as an assumption below)

<domain>
## Phase Boundary

Rewrite-before-retrieval behind one switch that ships off. Delivers: a new pure module `rag/query/rewrite.py` (deterministic skip gate, one tagged-line rewriter call, deterministic output guards, a parsed `RewriteResult`); wiring in `DocumentService._retrieve` so that, with the switch on, a follow-up is turned into one standalone question before `RetrievalPipeline.run`; one clarifying question on genuine ambiguity, returned through the normal response and SSE contract, never two in a row; a topic switch that starts a clean history; the four named failure modes tested with deliberately bad fake rewrites; a visible, never-silent rewrite-failure policy (D2).

Requirements: RWR-01, RWR-02, RWR-03, RWR-04. Not in this phase: measuring the rewrite and flipping its default (Phase 4: EVAL-01..03), the multi-turn golden loader and experiment (Phase 4), the page's clarify bubble (Phase 5), docs (Phase 5).

</domain>

<decisions>
## Implementation Decisions

### Carried forward (locked earlier, not re-asked)
- History is server-side; `rag/query/` stays pure; `neutralize` and `render_block` from `rag/query/history.py` (Phase 1); conversation store, lease, 404/409 mappings, `_remember` on the success path, `trace.config["conversation"]` (Phase 2).
- Every service LLM is built with `get_llm(spec, cache_dir=None)`; the Phase 2 AST guard test covers new call sites in `rag/api/` (Phase 2 D-17).
- `SYSTEM_PROMPT` / `DOCUMENT_SYSTEM_PROMPT` wording unchanged; the rewriter owns its own system prompt in `rag/query/rewrite.py`.

### The switch and the rewriter model
- **D-01:** One switch for rewrite, clarify and topic switch together: `DocumentService(rewrite: bool = False, rewrite_llm: Optional[LLM] = None)`, set in `build_default_service` from the setting `RAG_REWRITE` (`"1"` on, anything else off; default off). With the switch off, behaviour is exactly Phase 2's (no rewrite call, no clarify, no topic logic). [auto: recommended — ARCHITECTURE.md open item 4; R4 is only meaningful with rewriting on]
- **D-02:** The rewriter model is a seam: setting name `RAG_REWRITER` (default `ollama:qwen2.5:7b`, spec-string convention of `RAG_LLM`/`RAG_JUDGE`), built with `get_llm(spec, cache_dir=None)` only when `RAG_REWRITE` is on. When unset and on, it is the local Ollama model, not the reasoning generator. Phase 4 decides the default model by measurement. Add `RAG_REWRITE` and `RAG_REWRITER` (commented, no values) to `.env.example`. [auto: recommended — STACK.md name listed first in ROADMAP; reasoning model is slow to first token]
- **D-03:** Rewriter call: temperature as the provider sets it (no provider change), `max_output_tokens=120`, a system prompt owned by `rag/query/rewrite.py` (`REWRITE_SYSTEM_PROMPT`) with the STACK.md hard rules (resolve pronouns from history only; never add facts, names, numbers or scope; keep every constraint verbatim; answer `STANDALONE` when self-contained; `CLARIFY:` when two earlier things are equally plausible; `NEW_TOPIC:` with the message unchanged when the subject changes), and the history passed as the Phase 1 `render_block` text (already neutralized, labelled as quoted text). [auto: recommended]

### Skip gate (RWR-01)
- **D-04:** `needs_rewrite(message, window) -> bool` is deterministic and runs first: no prior turns → False (no model call on a first turn); otherwise skip only when the message has at least 10 words AND contains no anaphora/ellipsis marker (it, its, they, them, their, this, that, these, those, he, she, one, ones; openers "and", "what about", "how about", "also", "why", "same", "other", "former", "latter", "compare"); messages under 6 words always go to the model. Errs toward calling the model. [auto: recommended — STACK.md table]
- **D-05:** A call-count test with a fake model proves: zero rewriter calls on turn 1; zero calls for a long marker-free later message; one call for "and how does that compare to the other book?". [auto: recommended]

### Output protocol and guards (RWR-01, RWR-04)
- **D-06:** The rewriter answers one line: `STANDALONE`, `REWRITE: <question>`, `CLARIFY: <question>` or `NEW_TOPIC: <question>`, parsed by regex on the first non-empty line. Anything else is a parse failure. [auto: recommended]
- **D-07:** Deterministic guards on a `REWRITE:` result, each a named reason: `dropped_constraint` (every number, year, quoted string and constraint word — only, excluding, except, not, without, before, after, between — of the message must survive), `invented_detail` (no capitalised name or number absent from the message and the window), `too_long` (rewrite longer than message words + 40, or over 80 words), `flagged` (`scan_text` finds a rule), `topic_leak` (after a `NEW_TOPIC:` or for a message the gate judged standalone, the rewrite must not add terms found only in earlier turns). A failed guard falls back to the raw message with `fallback_reason` recorded. Wrong pronoun resolution is tested as a fake rewrite that resolves to the less recent entity when the window names only one candidate per the test fixture and is caught by `invented_detail`; if no deterministic check can catch a case, the test records it as a known limit rather than hiding it. [auto: recommended — PITFALLS.md Pitfall 2]
- **D-08:** The four named failure modes each have a test with a deliberately bad fake rewrite (`FakeLLM` returning a fixed bad line): invented details, dropped constraints, wrong pronoun resolution, earlier-topic leak. Each asserts retrieval ran on the raw message and the trace records the reason. [locked by RWR-04]

### Rewrite-failure policy (D2)
- **D-09 (D2 resolved, Option A fail-open with a visible flag):** a rewriter error (connection refused, timeout, empty output) or a parse failure does not fail the request: retrieval runs on the raw message, the trace records `rewrite: "fallback"` with `fallback_reason` (`unavailable`, `timeout`, `empty`, `unparsed`, or a guard reason), and the response (and the `final` SSE event) carries `"rewrite": {"status": "fallback", "reason": ...}` so the caller sees it. Experiments count a fallback as a rewrite failure, never as "off". The failure is decided before any SSE byte (rewrite runs in `_retrieve`). — **Reversibility:** costly — switching to fail-closed later changes the error contract of four routes and the page. [auto: recommended — option listed first in ROADMAP and STACK.md/PITFALLS.md lean; a down second model must not make chat unusable. Note: RWR-02's wording "any rewrite error surfaces as an HTTP status before any SSE byte" is satisfied in spirit by the visible flag decided before any SSE byte; the requirement text marks the policy as open decision D2, and ROADMAP Phase 3 success criterion 3 allows either form]

### What the response and trace carry (RWR-02)
- **D-10:** Retrieval runs fresh on the effective question (rewritten when accepted, else raw). `Trace.question` holds the text retrieval ran on; `trace.config["conversation"]` gains `original_question`, `rewritten_question` (or `null`), `rewrite` status (`off`, `skipped`, `standalone`, `rewritten`, `clarify`, `new_topic`, `fallback`), `fallback_reason`, `rewrite_ms`. The stored turn's `rewritten` field (Phase 2 D-09) is filled. The response gains `"rewrite": {"status", "reason", "rewritten_question"}` (status `off` when the switch is off). [auto: recommended]
- **D-11:** The answer prompt's question slot uses the effective (rewritten) question in this phase, with the history block from Phase 2 unchanged; Phase 4 measures the alternative (original message plus history) and decides. [auto: recommended — STACK.md/ARCHITECTURE.md lean; Phase 4 decides]

### Clarify (RWR-03)
- **D-12:** A `CLARIFY:` result short-circuits before retrieval: no retrieval, no answer-model call. The response uses the normal shape with `kind: "clarify"`, `answer` = the clarifying question (after `filter_output`), `passages: []`, `citations: []`, `abstained: false`, `stages: []`; the stream route sends no `token` events and one `final` event with the same data. `_describe` gets a clarify branch that does not read `trace.stage("context")`. Ordinary answers carry `kind: "answer"`. The clarification is stored as a turn with `kind: "clarify"`. [auto: recommended]
- **D-13:** Never two clarifications in a row: if the last stored turn has `kind: "clarify"`, the rewriter is called with `allow_clarify=False` (the prompt drops the CLARIFY option) and a `CLARIFY:` answer anyway is treated as a parse failure (fallback to raw). [auto: recommended — ARCHITECTURE.md]

### Topic switch (RWR-04)
- **D-14:** Topic switch is detected by the same rewriter call (`NEW_TOPIC:` tag), not by embeddings. On `NEW_TOPIC`, the rewrite uses the message unchanged, the stored turn is marked `topic_start: true`, and both the rewrite window and the answer prompt's history block for this and later turns start from the most recent `topic_start` turn. [auto: recommended — PITFALLS.md: do not gate on embedding similarity]

### Golden authoring timing
- **D-15:** Multi-turn golden items are drafted during this phase in `data/golden/conversations_draft.jsonl` (human-written standalone question and PDF gold pages per follow-up) before the rewriter prompt is tuned, so the rewriter is not tuned to its own examples; the loader, the experiment and the shipping rule are Phase 4. The draft file is not loaded by any test in this phase. [auto: recommended — ROADMAP Phase 4 scope note]

### Claude's Discretion
- Exact `REWRITE_SYSTEM_PROMPT` wording within D-03's rules; regex details of the gate and guards within D-04/D-07; `RewriteResult` field names beyond `status`, `question`, `reason`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scope and requirements
- `.planning/REQUIREMENTS.md` — RWR-01..04 (and EVAL-01..03 for what is deferred)
- `.planning/ROADMAP.md` §"Phase 3" — success criteria 1-5, D2, rewriter seam and switch name; §"Phase 4" scope note on golden authoring timing

### Earlier phases
- `.planning/phases/01-safety-net-and-prompt-seam/01-CONTEXT.md`, `01-05-PLAN.md` — `history.py` symbols (`HistoryTurn`, `window`, `neutralize`, `render_block`)
- `.planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-CONTEXT.md`, `02-03-PLAN.md`, `02-04-PLAN.md` — store API, lease, `_retrieve` order, `_describe`, `_remember`, response fields, AST guard on `get_llm`

### Design and research
- `.planning/research/STACK.md` — skip-gate table (line ~61), output protocol (~63), failure isolation (~80), `RAG_REWRITER` (~84), rewriter prompt rules (~97)
- `.planning/research/ARCHITECTURE.md` — `rewrite_question(llm, message, window, allow_clarify)` (~248), no two clarifications (~113, ~317), one switch (~386)
- `.planning/research/PITFALLS.md` — Pitfalls 2, 3, 9, 13, 14, 15, 20 (distortion, injection via rewrite output, errors before SSE, clarify shape, topic leak)
- `interview/05_conversation_memory_and_cost.md` — design of rewrite, clarify, topic switch

### Code
- `rag/api/service.py` (`_retrieve`, `_describe`, `ask_documents*`), `rag/api/main.py` (`build_default_service`, `guarded`), `rag/query/history.py`, `rag/query/guard.py` (`scan_text`, `filter_output`), `rag/query/generate.py` (`_CITATION`), `.env.example`
- `tests/test_api.py`, `tests/test_stream_api.py`, `tests/test_conversations.py` (Phase 2)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `FakeLLM` (`from rag.common.llm import FakeLLM`) with a function `lambda system, user: "..."` and a call record — the fake rewriter for every gate, guard and failure-mode test
- `scan_text` / `filter_output` in `rag/query/guard.py` — guard the rewrite output and the clarifying text
- `render_block` / `neutralize` / `window` from `rag/query/history.py` — the history text the rewriter sees
- Phase 2's `GatedLLM` and `seed_turns` test helpers in `tests/test_conversations.py`

### Established Patterns
- `_retrieve` does all pre-model work so errors and short-circuits happen before any SSE byte
- Settings read through `setting(...)` in `build_default_service`; spec strings for models
- Service raises domain exceptions; routes map them in `guarded()`

### Integration Points
- `_retrieve`: after the window is built and before `retrieval.run`, call `needs_rewrite` then `rewrite_question`; on clarify, return a short-circuit marker that `ask_documents` / `ask_documents_stream` turn into a clarify response and a stored `kind: "clarify"` turn
- `_describe`: clarify branch and the `rewrite` / `kind` fields
- `build_default_service`: `RAG_REWRITE`, `RAG_REWRITER`

</code_context>

<specifics>
## Specific Ideas

- The pronoun test uses "and how does that compare to the other book?" after a turn about replication in one named document.
- A clarify test asserts the stream route returns zero `token` events and one `final` event with `kind: "clarify"`, and that an ambiguous message right after it produces an answer, not a second clarification.
- A rewriter-down test patches the fake rewriter to raise `URLError(ConnectionRefusedError())` and asserts the answer still arrives with `rewrite.status == "fallback"` and `reason == "unavailable"`.

</specifics>

<deferred>
## Deferred Ideas

- Measuring rewrite on/off/oracle, choosing the default model and the question slot, flipping the default — Phase 4
- Ollama JSON-schema `format` upgrade — only if Phase 4 measures a high parse-failure rate
- Showing the rewritten question in the page's "what the pipeline saw" panel — v2 CONV-08
- Separate switches for clarify and topic switch — rejected for now (one switch)

</deferred>

---

*Phase: 03-rewrite-clarify-and-topic-switch*
*Context gathered: 2026-10-22 (auto mode)*
