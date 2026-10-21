# Phase 1: Safety net and prompt seam - Context

**Gathered:** 2026-10-21
**Status:** Ready for planning
**Mode:** `--auto` (every gray area took the recommended option; each pick is recorded as an assumption below)

<domain>
## Phase Boundary

Pin single-turn behaviour before any shared function is edited, then open the prompt seam that later phases fill. Delivers: (1) a committed snapshot test of the exact prompt bytes for every style and subject, written and committed on the unedited code; (2) an optional `history_block=""` parameter threaded through `build_user_prompt`, `spotlight_user_prompt`, `build_prompts`, `answer_from_context`, `RagPipeline.answer` and `RagPipeline.stream`, whose empty default returns today's bytes unchanged; (3) the pure, unwired history helpers and budget constants in a new `rag/query/history.py`; (4) the retrieval invariant and the pytest baseline re-run and recorded; (5) the model server's `max_model_len` read once and written into `docs/models.md`.

Not in this phase: any conversation store, any route or request-model change, any history reaching a prompt at runtime, the rewriter, the page. Requirement verified here: PRMT-02. Groundwork for PRMT-01, PRMT-03, PRMT-04 (verified in Phase 2).

</domain>

<decisions>
## Implementation Decisions

### Snapshot test shape
- **D-01:** Snapshot cases are the cross product of style (`standard`, `spotlight`, `naive`) x subject (`book`, `document`) x passages (zero, one single-page hit, one page-range hit, and the two-hit mix), built from fixed in-test `Hit` objects with fixed text and page numbers. Each case's `(system_prompt, user_prompt)` pair is stored as full text in one committed file per case under `tests/snapshots/prompts/` so a drift shows as a readable diff. [auto: recommended]
- **D-02:** The 45 golden questions (`data/golden/ddia_questions.jsonl`, loaded with `load_golden`) are snapshotted for the production path only (`standard` style, `book` subject, the two-hit fixed passage set) as `sha256` digests of the user prompt in one committed JSON manifest keyed by question id. Full text would be 45 near-identical files; digests catch any byte change. [auto: recommended]
- **D-03:** The snapshot test lives in `tests/test_prompt_snapshot.py`. It has no "update" switch; regenerating a snapshot is a deliberate edit of the fixture files in a commit whose message says why. [auto: recommended]
- **D-04:** The snapshot files and the test are committed on the unedited prompt code in their own commit, before any edit to `rag/query/prompt.py`, `rag/query/generate.py`, `rag/security/defenses.py` or `rag/query/pipeline.py`. The planner expresses this as a plan that every seam plan `depends_on`. — **Reversibility:** one-way — a snapshot taken after an edit cannot prove the edit was byte-neutral. [auto: recommended]

### Spotlight nonce in the snapshot
- **D-05:** The spotlight nonce is random per process (`rag/security/defenses.py` `_NONCE_KEY`), so the snapshot test fixes it by `monkeypatch.setattr("rag.security.defenses._NONCE_KEY", b"snapshot-fixed-key")` inside the test. It does not set `RAG_NONCE_KEY` in the environment (import-order dependent and the variable is documented as a secret). [auto: recommended]

### Seam shape (the only shared-code edit in this phase)
- **D-06:** One keyword parameter, `history_block: str = ""`, is added to `build_user_prompt`, `spotlight_user_prompt`, `build_prompts` and `answer_from_context`, and as a per-call keyword on `RagPipeline.answer(trace, history_block="")` and `RagPipeline.stream(trace, history_block="")` (not on the constructor, not on the trace). `RagPipeline.run` keeps its signature. [auto: recommended]
- **D-07:** The block is inserted between the passages and the `Question:` line, as a self-contained string that the caller has already rendered (the prompt builders do not know about turns). When `history_block` is the empty string the builders return the exact old expression: no header, no extra blank line, no changed whitespace. Rendering a non-empty block is the job of `render_block` in `rag/query/history.py`, which includes its own header and trailing separator so the builder only does `context + block + question`. [auto: recommended]
- **D-08:** `SYSTEM_PROMPT`, `DOCUMENT_SYSTEM_PROMPT`, `SPOTLIGHT_ADDENDUM` and `NAIVE_SYSTEM_PROMPT` are not touched; history is a user-prompt block only. [locked by REQUIREMENTS.md Out of Scope]

### History helpers (`rag/query/history.py`, unwired in this phase)
- **D-09:** Module `rag/query/history.py` holds: `HistoryTurn` (frozen dataclass: `question`, `answer`, `asked_at`; `rewritten: Optional[str] = None`), `window(turns, n=HISTORY_WINDOW_TURNS) -> List[HistoryTurn]` (last n, oldest first), `neutralize(text, max_words) -> str` (run `scan_text`, strip `[S n]` markers, apply the `filter_output`-style defang to any flagged span, truncate to `max_words` words with a marker), `render_block(turns) -> str` (returns `""` for no turns; otherwise a header that labels the turns as quoted text, not instructions, `User:` / `Assistant:` lines, and a trailing blank line), and the budget constants. Pure functions, no I/O, no owner, no LLM. [auto: recommended]
- **D-10 (D3 provisional, Option A):** Constants start at `HISTORY_WINDOW_TURNS = 6`, `HISTORY_BLOCK_MAX_WORDS = 400`, `HISTORY_ANSWER_MAX_WORDS = 40`, `HISTORY_QUESTION_MAX_WORDS = 60`, `CONVERSATION_MAX_TURNS = 50`, `TOKENS_PER_WORD = 1.5`, plus `MODEL_CONTEXT_TOKENS` set from the `max_model_len` read in this phase. Option A was chosen because it stays safe even at an 8,192-token context window; Phase 2 pins the numbers after the recorded `max_model_len` and may raise them. [auto: recommended; D3 stays open for Phase 2]
- **D-11:** A worst-case budget unit test asserts `system prompt + 1500-word passages + HISTORY_BLOCK_MAX_WORDS + HISTORY_QUESTION_MAX_WORDS` (all at `TOKENS_PER_WORD`) `+ 3000 thinking + 600 answer <= MODEL_CONTEXT_TOKENS`. If `max_model_len` could not be read, `MODEL_CONTEXT_TOKENS` is set to 8192 with a comment naming it a floor to be replaced. [auto: recommended]

### Reading `max_model_len`
- **D-12:** Read it with one `GET {REMOTE_URL}/models` request (vLLM's OpenAI-compatible model list carries `max_model_len`) from a one-off command in the plan, not by editing `rag/common/` (that folder is hook-flagged and no production code needs the number). Record the number, the model id, the date and the command in a "Context window" paragraph of `docs/models.md`. [auto: recommended]
- **D-13:** If the tunnel is down (connection refused on `127.22.10.1:30007`), the task records "not read on <date>: tunnel down" in `docs/models.md`, uses the 8192 floor (D-11), writes a blocker to `.planning/STATE.md`, and the phase still completes; the number is re-read at the start of Phase 2. No task waits on the user. [auto: recommended]

### Recording the invariants
- **D-14:** The exact output lines of `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` (expected hit@5 0.865, mrr 0.663) and `python -m pytest tests -q` are pasted into the plan SUMMARY.md and the phase VERIFICATION.md. The pytest baseline is "the 593 already-collected tests still pass (591 passed, 2 skipped)"; the new total after this phase's tests is recorded next to it. No new docs file; `CLAUDE.md` already states the invariant. [auto: recommended]
- **D-15:** The retrieval invariant is run twice in this phase: once before any edit (with the snapshot commit) and once after the seam edits; both outputs are recorded. [auto: recommended]

### Claude's Discretion
- Exact wording of the history block header (must say the turns are quoted text, not instructions) and the truncation marker.
- Fixture passage text and page numbers used by the snapshot cases.
- Whether the golden-set digest manifest also stores the question text (helps a reader; not required).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scope and requirements
- `.planning/REQUIREMENTS.md` — PRMT-02 (this phase), PRMT-01/03/04 (groundwork), Out of Scope table (no prompt wording change, no tokenizer package, no cache for uploads)
- `.planning/ROADMAP.md` §"Phase 1: Safety net and prompt seam" — success criteria 1-4 and the D3 open decision
- `.planning/PROJECT.md` §Constraints — prompt stability, retrieval invariant, working rules

### Design and research
- `.planning/research/SUMMARY.md` §"Phase 1" and §"Open Decisions" D3 — helper module shape, budget arithmetic, pitfalls 1, 4, 12
- `.planning/research/ARCHITECTURE.md` — prompt seam ("five edits ... each a new optional parameter whose empty default returns the old expression"), `rag/query/history.py` design
- `.planning/research/PITFALLS.md` — Pitfall 1 (prompt drift), Pitfall 4 (stale `[S n]`, defanged history), Pitfall 12 (overflow)
- `interview/05_conversation_memory_and_cost.md` — the budget formula (context window minus system prompt, passages at 1500 words, answer budget with thinking tokens)

### Code the phase edits or snapshots
- `rag/query/prompt.py` — `build_user_prompt`, `format_context`, `SYSTEM_PROMPT`, `DOCUMENT_SYSTEM_PROMPT` (wording locked)
- `rag/query/generate.py` — `build_prompts` (line 51), `answer_from_context`
- `rag/security/defenses.py` — `spotlight_user_prompt`, `SPOTLIGHT_ADDENDUM`, `NAIVE_SYSTEM_PROMPT`, `_NONCE_KEY`, `nonce_for`
- `rag/query/pipeline.py` — `RagPipeline.answer` and `RagPipeline.stream` (line 194 calls `build_prompts`)
- `rag/query/guard.py` — `scan_text`, `filter_output`, `_PROMPT_ECHO` (reused by `neutralize`)
- `rag/observe/golden.py` — `load_golden`, `GoldQuestion`
- `docs/models.md` — gains the "Context window" paragraph
- `.env.example` — `REMOTE_URL=http://127.22.10.1:30007/v1` (the `/models` endpoint hangs off it)

### Conventions and tests
- `.planning/codebase/TESTING.md` — flat `tests/test_<area>.py`, `tmp_path`, `FakeLLM`, parametrize tables, prove-fails-on-old-code recipe
- `.planning/codebase/CONVENTIONS.md` — typing generics not `|`, absolute imports, `UPPER_SNAKE_CASE` constants, frozen dataclasses for values
- `CLAUDE.md` (repo root) — commit via `git commit -F <file>`; never name `rag/common/llm.py` or `tests/test_vllm.py` in a command; never glob `tests/` or `rag/common/`; never read `.env`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `rag.common.types.Hit` — build fixed passages for snapshot cases (`page_start == page_end` gives "PDF page N", otherwise "PDF pages A-B")
- `rag.observe.golden.load_golden` — loads the 45 golden questions for the digest manifest
- `rag.query.guard.scan_text` / `filter_output` — the scanner and defang logic `neutralize` reuses; `_CITATION = re.compile(r"\[S(\d+)\]")` in `rag/query/generate.py` is the marker pattern to strip
- `tests/test_generation.py` already imports `build_user_prompt` and checks "(no passages were retrieved)"; `tests/test_security.py` already monkeypatches around `nonce_for` — follow those patterns
- `rag.common.llm.FakeLLM` (via `from rag.common.llm import FakeLLM`; name the module only in Python imports, never in a shell command) for any test that calls `answer_from_context`

### Established Patterns
- Prompt builders are pure string functions; `build_prompts` dispatches on `style` and `subject` and raises `ValueError` for an unknown style
- `RagPipeline.answer` and `RagPipeline.stream` both call the builders with `trace.question`; `stream` is the only place that calls `build_prompts` directly (line 194)
- Spotlight nonce is an HMAC over the question with a per-process key; the LLM disk cache keys on the full prompt
- Tests use `monkeypatch.setattr` with dotted string paths and never a mocking library

### Integration Points
- Phase 2 will pass `render_block(window(turns))` into `RagPipeline.answer/stream` from `DocumentService._retrieve` (`rag/api/service.py:441`); nothing in this phase touches `rag/api/`
- The budget constants and `MODEL_CONTEXT_TOKENS` are read by Phase 2's cap check; keep them in `rag/query/history.py`, not in `rag/common/config.py`

</code_context>

<specifics>
## Specific Ideas

- The empty-history identity must hold three ways: builder called with no argument, builder called with `history_block=""`, and the committed snapshot; one parametrized test asserts all three equal.
- The snapshot commit is the first commit of the phase and contains only `tests/test_prompt_snapshot.py` and `tests/snapshots/`; the retrieval invariant output from the same unedited tree is recorded with it.
- `docs/models.md` records `max_model_len` next to the generator row's reasoning note, with the date and the exact command used.

</specifics>

<deferred>
## Deferred Ideas

- Reporting the number of dropped turns when `window()` trims (PITFALLS.md) — Phase 2, where the trace block exists to carry it.
- Extending `python -m rag.common.llm_check` to print `max_model_len` — later, if the number is ever needed at runtime; this phase reads it once by hand.
- Per-turn caps with a longer last assistant turn (PITFALLS.md variant of D3) — Phase 2 when D3 is pinned.

</deferred>

---

*Phase: 01-safety-net-and-prompt-seam*
*Context gathered: 2026-10-21 (auto mode)*
