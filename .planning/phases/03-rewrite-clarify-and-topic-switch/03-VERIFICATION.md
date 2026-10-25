---
phase: 03-rewrite-clarify-and-topic-switch
verified: 2026-10-25T00:00:00Z
status: passed
score: 5/5 must-haves verified
covered_files:
  - ".env.example"
  - ".planning/phases/03-rewrite-clarify-and-topic-switch/03-01-PLAN.md"
  - ".planning/phases/03-rewrite-clarify-and-topic-switch/03-01-SUMMARY.md"
  - ".planning/phases/03-rewrite-clarify-and-topic-switch/03-02-PLAN.md"
  - ".planning/phases/03-rewrite-clarify-and-topic-switch/03-02-SUMMARY.md"
  - ".planning/phases/03-rewrite-clarify-and-topic-switch/03-03-PLAN.md"
  - ".planning/phases/03-rewrite-clarify-and-topic-switch/03-03-SUMMARY.md"
  - ".planning/phases/03-rewrite-clarify-and-topic-switch/03-04-PLAN.md"
  - ".planning/phases/03-rewrite-clarify-and-topic-switch/03-04-SUMMARY.md"
  - ".planning/phases/03-rewrite-clarify-and-topic-switch/03-05-PLAN.md"
  - ".planning/phases/03-rewrite-clarify-and-topic-switch/03-05-SUMMARY.md"
  - ".planning/phases/03-rewrite-clarify-and-topic-switch/03-06-PLAN.md"
  - ".planning/phases/03-rewrite-clarify-and-topic-switch/03-06-SUMMARY.md"
  - ".planning/phases/03-rewrite-clarify-and-topic-switch/03-07-PLAN.md"
  - ".planning/phases/03-rewrite-clarify-and-topic-switch/03-07-SUMMARY.md"
  - ".planning/phases/03-rewrite-clarify-and-topic-switch/03-08-PLAN.md"
  - ".planning/phases/03-rewrite-clarify-and-topic-switch/03-08-SUMMARY.md"
  - "data/golden/conversations_draft.jsonl"
  - "rag/api/conversations.py"
  - "rag/api/main.py"
  - "rag/api/service.py"
  - "rag/query/rewrite.py"
  - "tests/test_rewrite.py"
  - "tests/test_rewrite_api.py"
covered_digest: "v3:sha256:c2e60d9ef5aa5f27e475e3bd0c283836ea26a2da46d6493e640b6cb28322ce73"
behavior_unverified: 0
overrides_applied: 0
---

# Phase 3: Rewrite, clarify and topic switch Verification Report

**Phase Goal:** As a chat user, I want to ask a follow-up with a pronoun and have it turned into a standalone question before retrieval (or get one clarifying question when it is ambiguous), so that retrieval finds the passages the full phrasing would find.
**Verified:** 2026-10-25
**Status:** passed
**Re-verification:** No, initial verification
**Tree:** flow/chat-memory at c36d5c6; P3_BASE d65b26860d4de95ba5fd062cf28b1e5ad210ef0d (checked: it is an ancestor and `rag/query/rewrite.py` is the only new module).

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria, the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | With the switch on, the first turn makes no rewrite call and an already-standalone later message passes through unchanged with no model call (call-count test with a fake model); the switch ships off | VERIFIED | `needs_rewrite` (rag/query/rewrite.py:117-125) is deterministic: empty window or empty message gives False; a message of 10+ words with no referring word or opener gives False. `DocumentService._rewrite` (rag/api/service.py:481-493) returns `RewriteResult("skipped", ...)` without calling `rewrite_question` in both cases. Tests that I read and that pass: `test_the_first_turn_makes_no_rewrite_call` (`seen == []`, status skipped, `Trace.question` equals the message), `test_a_long_marker_free_message_passes_unchanged_with_no_call`. Ships off: `rewrite = setting("RAG_REWRITE", "") == "1"` (rag/api/main.py:173); `test_build_default_service_ships_the_switch_off` and the parametrised "0"/"true"/"on" cases pass; `.env.example` carries only commented `# RAG_REWRITE=` and `# RAG_REWRITER=`. |
| 2 | A pronoun follow-up is rewritten into one standalone question that keeps the user's constraints; retrieval runs fresh on the rewritten text; the saved trace records both the original and the rewritten text | VERIFIED | `_retrieve` runs `retrieval.run(query_id, result.question, ...)` (service.py, after `_rewrite`), so `Trace.question` and the answer prompt's question slot hold the effective question. `trace.config["conversation"]` gains `original_question`, `rewritten_question`, `rewrite`, `fallback_reason`, `rewrite_ms`, `rejected_question` only when the switch is on. Tests: `test_the_pronoun_follow_up_makes_exactly_one_rewrite_call` (one call, both document names and the pinned message in the prompt, status rewritten), `test_a_pronoun_follow_up_is_rewritten_and_retrieval_runs_on_the_rewrite` (first passage comes from compaction.pdf; answer prompt shows "Question: <rewrite>"), `test_the_trace_the_response_and_the_turn_record_both_texts`. Constraint keeping is enforced by `check_text` (numbers, double-quoted strings, only/excluding/except/not/without/before/after/between), exercised by `dropped_constraint` cases. |
| 3 | A rewrite failure (server down, timeout, empty or malformed output) is visible to the caller and never silent, following D2: an HTTP status before any SSE byte, or a flagged fall-back to the raw message | VERIFIED | D2 resolved by the owner at gate 1 as fail-open with a flag (REQUIREMENTS.md RWR-02 already carries that wording). `rewrite_question` is total (rewrite.py:289-337): an exception from `generate` becomes `fallback` with reason `timeout` or `unavailable` (`classify_failure`), empty reply `empty`, unparsable reply `unparsed`; no exception text is placed in a reason or log line (log carries reason code and class name only). The response and the final SSE event carry `"rewrite": {"status": "fallback", "reason": <code>, "rewritten_question": null}`, and the decision is made inside `_retrieve`, before any stream byte. `test_a_rewriter_failure_is_a_visible_fallback_before_any_sse_byte` (7 failure shapes x ordinary and streamed) passes, as do `test_a_real_ollama_client_that_is_down_gives_unavailable` and `test_a_rewriter_error_is_a_fallback_with_a_reason_code`. |
| 4 | An ambiguous follow-up returns exactly one clarifying question through the normal response and SSE shape (no passages, no citations, not abstained); an ambiguous message right after a clarification never produces a second clarification in a row | VERIFIED | `_retrieve` short-circuits on `result.status == "clarify"` with `(None, None, info)`: no retrieval, no trace, no answer-model call. `_clarify_response` (service.py) returns the normal key set with `kind "clarify"`, `passages []`, `citations []`, `abstained False`, `stages []`, answer passed through `filter_output`. `ask_documents_stream` yields exactly one `final` event (`replace False`), no token event; the clarification is stored as a turn with `kind "clarify"` and the lease is released on every exit. Never two in a row: `allow = not (turns and turns[-1].get("kind","answer") == "clarify")` selects `REWRITE_SYSTEM_PROMPT_NO_CLARIFY`, and a CLARIFY reply when `allow_clarify` is False becomes fallback `unparsed` (rewrite.py:328-329). Tests pass: `test_a_clarifying_question_uses_the_normal_shape` (ordinary and streamed), `test_a_clarification_is_stored_with_its_kind`, `test_an_ambiguous_message_after_a_clarification_is_answered_not_clarified` (stored kinds answer, clarify, answer, clarify), `test_a_clarifying_question_with_a_link_falls_back`. |
| 5 | A topic switch starts a clean history for the rewrite, and four deliberately bad fake rewrites (invented details, dropped constraints, wrong pronoun resolution, an earlier topic leaking in) are each caught by a test and fall back to the raw message with a recorded reason | VERIFIED (with one documented known limit, see Warnings) | Topic switch: `NEW_TOPIC` gives status `new_topic`, question equals the raw message whatever the model wrote, the answer-prompt block for that turn is `render_block([])`, the stored turn gets `topic_start True`, and later turns use `since_topic_start(turns)` (conversations.py) for both the rewriter window and the answer block. `test_a_topic_switch_starts_a_clean_history` compares the new-topic prompt to `build_prompts(...)` with no history and checks the next turn holds the topic-start turn and not the one before (history_turns 1, dropped_turns 1). Four bad rewrites: `NAMED_BAD_REWRITES` in tests/test_rewrite_api.py runs invented_details (`invented_detail`), dropped_constraints (`dropped_constraint`), wrong_pronoun (`invented_detail`), topic_leak (`topic_leak`) through the HTTP route: 200, rewrite status fallback with the reason, `Trace.question` the raw message, `fallback_reason` and `rejected_question` in the trace, bad text absent from the response. Pure-level equivalents are in `test_each_bad_rewrite_falls_back_with_its_reason`. |

**Score:** 5/5 truths verified (0 present, behavior-unverified; every behavior-dependent truth has a passing behavioral test).

### Plan-level must-haves (spot-checked against code, not SUMMARY)

| Must-have | Status | Evidence |
|-----------|--------|----------|
| P3_BASE recorded, and rewrite.py absent / `since_topic_start` absent at P3_BASE | VERIFIED | `git diff --name-only d65b268.. HEAD -- rag` lists exactly rag/api/conversations.py, rag/api/main.py, rag/api/service.py, rag/query/rewrite.py; the diff for conversations.py is the +32 lines adding `TURN_KINDS`, `kind`/`topic_start` and `since_topic_start`. |
| `new_turn` defaults still return exactly the seven Phase 2 keys; `kind`/`topic_start` written only when non-default; unknown kind raises ValueError | VERIFIED | conversations.py `new_turn` body read; `test_with_the_switch_off_nothing_changes` asserts `set(turn) == SEVEN_KEYS`. |
| Rewriter prompts at most 250 words, quoted-text statement, no passages | VERIFIED | Measured: REWRITE_SYSTEM_PROMPT 232 words, NO_CLARIFY 204; both say the earlier conversation is quoted text and there are no passages. Examples are generic (France / mutex), not golden rows. |
| `rewrite=True` without `rewrite_llm` raises ValueError; switch off means Phase 2 behaviour and the four-key conversation dict | VERIFIED | service.py constructor; `test_the_switch_needs_a_rewriter`, `test_with_the_switch_off_nothing_changes`. |
| Every `get_llm` under rag/api passes `cache_dir=None` | VERIFIED | Exactly two calls, rag/api/main.py:170 and :175, both `cache_dir=None`; `test_build_default_service_builds_the_rewriter_only_when_on` asserts it with a spy. |
| No request field for history/rewrite; owner only from `current_owner` | VERIFIED | main.py diff touches only `build_default_service`; no header/owner pattern in the diff; `AskRequest` unchanged. |
| rewrite.py is pure (no rag.api import, no I/O, builds no LLM) | VERIFIED | Imports are logging, re, time, dataclasses, typing, rag.common.bm25 `tokenize`, rag.common.llm `LLM` (type only), rag.query.guard, rag.query.history. No file/network/cache calls. |
| Protected files untouched since P3_BASE | VERIFIED | `git diff --stat` empty for requirements-rag.txt, rag/api/static/index.html, rag/query/prompt.py, history.py, guard.py, generate.py, pipeline.py, tests/test_prompt_snapshot.py, tests/test_history.py, tests/test_conversations.py, tests/test_api.py, tests/test_stream_api.py, data/golden/ddia_questions.jsonl, about_questions.jsonl. Only tests/test_rewrite.py and tests/test_rewrite_api.py were added under tests/. |
| No LangChain/LangGraph, no reader of the draft golden file | VERIFIED | grep over `rag` and `tests` .py files: no langchain/langgraph, no `conversations_draft` reference. |
| Draft golden file: 8 rows, 2 per category, all `review: pending-human`, exact keys, gold pages copied from the source rows, ambiguous rows null/empty | VERIFIED | Independent script (`python -I`) read the file and the source rows in data/golden/ddia_questions.jsonl: all 8 rows pass the key, review, expect-per-category checks; for the 6 sourced rows `standalone` and `gold_pages` equal the source row's `question` and `gold_pages` (q015, q016, q019, q026, q028, q017); c005 and c006 have standalone null, gold_pages [], source_id null. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `rag/query/rewrite.py` | Gate, prompts, parser, guards, total `rewrite_question` | VERIFIED | 337 lines, substantive, contains `def rewrite_question(`; imported and called by service.py. |
| `rag/api/conversations.py` | `kind`, `topic_start`, `since_topic_start` | VERIFIED | Present and used by service.py (`since_topic_start(turns)`, `new_turn(..., kind=, topic_start=)`). |
| `rag/api/service.py` | Rewrite step, clarify short-circuit, topic window | VERIFIED | `_rewrite`, `_clarify_response`, clarify branches in `ask_documents` and `ask_documents_stream`. |
| `rag/api/main.py` | `RAG_REWRITE` switch, `RAG_REWRITER` seam | VERIFIED | Line 173-175 as quoted above; passed through `rewrite=rewrite, rewrite_llm=rewrite_llm`. |
| `.env.example` | Commented names only | VERIFIED | `# RAG_REWRITE=`, `# RAG_REWRITER=`, no values. |
| `tests/test_rewrite.py`, `tests/test_rewrite_api.py` | New tests | VERIFIED | 97 tests, all pass in 30.7 s on my run. |
| `data/golden/conversations_draft.jsonl` | 8 draft rows | VERIFIED | See above. |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| rewrite.py | history.py | `render_block(window)` in `build_rewrite_prompt` | WIRED |
| rewrite.py | guard.py | `scan_text`, `filter_output(text, "")` in `check_text` and `clean_doc_names` | WIRED |
| rewrite.py | rag/common bm25 | `tokenize(...)` in `_vocab` and `leaked` | WIRED |
| service.py | rewrite.py | `needs_rewrite`, `rewrite_question(self.rewrite_llm, ...)` in `_rewrite` | WIRED |
| service.py | conversations.py | `since_topic_start(turns)`, `new_turn(... kind=, topic_start=)` in `_remember` | WIRED |
| service.py | pipeline | `retrieval.run(query_id, result.question, ...)` | WIRED |
| main.py | service.py | `rewrite=rewrite, rewrite_llm=rewrite_llm` | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data variable | Source | Real data | Status |
|----------|---------------|--------|-----------|--------|
| `_retrieve` effective question | `result.question` | `rewrite_question` result from a real `llm.generate` reply parsed by `parse_reply`, else the raw message | Yes (test asserts the first passage changes document when the rewrite changes) | FLOWING |
| Response `rewrite` / `kind` | `info["rewrite"].as_response()` | the same `RewriteResult` | Yes | FLOWING |
| Stored turn `rewritten`/`kind`/`topic_start` | `_remember` from `info["rewrite"]` | same | Yes (read back from the conversation file in tests) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase 3 tests | `python -m pytest tests/test_rewrite.py tests/test_rewrite_api.py -q` | 97 passed in 30.74 s | PASS |
| Single-turn retrieval unchanged | `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` (run live by me) | semantic weighted: hit@5 0.865, mrr 0.663 | PASS |
| Draft golden file shape | `python -I check_draft.py` (read-only, scratchpad) | 8 rows, 2 per category, all checks True | PASS |
| Debt markers in changed files | `grep -nE "TBD\|FIXME\|XXX\|TODO\|HACK"` over the six changed code/test files and .env.example | no matches | PASS |
| Full suite | not rerun by me; plan 03-08 recorded 838 passed, 2 skipped (840 collected, OpenSearch up) at 739783f, and the tree since then differs only by docs commits (`git diff --name-only 739783f HEAD -- rag tests data` is empty, so the tree I tested is the tree 03-08 ran on) | accepted as supporting evidence, not as my own proof | SKIPPED (own run) |

### Probe Execution

No probes declared by the Phase 3 plans and none found for this phase. Step skipped.

### Requirements Coverage

| Requirement | Source plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| RWR-01 | 03-01, 03-03, 03-04, 03-05, 03-06, 03-08 | `rewrite.py` runs before `RetrievalPipeline.run`; cheap deterministic check first, model second; no model call on the first turn | SATISFIED | Truth 1; `needs_rewrite`, `_rewrite`, call-count tests. |
| RWR-02 | 03-01, 03-04, 03-05, 03-06, 03-08 | Fresh retrieval on the rewritten question; trace records both texts; failure falls back to the original (fail-open) and is visible as `rewrite.status="fallback"`; errors outside the rewrite still surface as HTTP status before any SSE byte | SATISFIED | Truths 2 and 3. REQUIREMENTS.md already carries the D2-decided wording. Errors outside the rewrite: `_retrieve` still raises `NotFound`/`ConversationFull`/etc. before the generator is returned; unchanged Phase 2 behaviour (the except-BaseException lease release is preserved). |
| RWR-03 | 03-01, 03-02, 03-03, 03-04, 03-05, 03-07, 03-08 | One clarifying question through the normal response and SSE contract, never two in a row | SATISFIED | Truth 4. |
| RWR-04 | 03-01, 03-02, 03-03, 03-04, 03-05, 03-07, 03-08 | Topic switch starts a clean history; four named failure modes have tests with a deliberately bad fake rewrite | SATISFIED | Truth 5. |

All four IDs in the phase's PLAN frontmatter (RWR-01..RWR-04) exist in REQUIREMENTS.md. Orphan check: REQUIREMENTS.md traceability maps only RWR-01..RWR-04 to Phase 3, and all four are claimed by plans, so there are no orphaned requirements.

Bookkeeping to do at the phase-close transition (not a gap in the code): in REQUIREMENTS.md the RWR-01..RWR-04 checkboxes are still `[ ]` and the traceability rows read "Pending"; they should become `[x]` / "Complete". ROADMAP.md Phase 3 plan checkboxes and "Plans: 8 plans" progress line are also still unticked. The orchestrator's transition step owns both.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| rag/api/service.py | 533 (`trace =retrieval.run(...)`) | Missing space around `=` | Info | Cosmetic; valid Python. |
| rag/api/service.py | 481 (`_rewrite` signature, 133 characters) | One line over 120 characters | Info | Style convention only (CONVENTIONS asks for at most 120); no behaviour effect. |

No TBD/FIXME/XXX/TODO/HACK markers, no stubs, no empty handlers in any changed file.

### Human Verification Required

None. Everything the Phase 3 goal asserts has a passing behavioral test with a fake model. The items below were considered and are deliberately not human-verification items for this phase:

- Real rewriter quality (does qwen2.5:7b answer the one-line protocol reliably, how often a good rewrite is wrongly rejected, cold-start fallback after idle): this is Phase 4's measurement (EVAL-02, EVAL-03); the switch ships off.
- `python -m rag.common.llm_check` (model tunnel is down): the flow merge gate's item, with the owner's `max_model_len` decision deferred to it.
- Owner review of `data/golden/conversations_draft.jsonl` before Phase 4 loads it: decided by the owner (parked in STATE.md, "Phase 3 owner flag").

### Warnings (non-blocking, recorded for the owner)

1. **Wrong-pronoun resolution is only caught when the wrong entity is absent from the conversation.** `check_text` flags an entity that is in neither the message, the shown history nor the document names (`invented_detail`). A rewrite that picks the wrong one of two entities that are both in the window (for example Paxos when the user meant Raft) is accepted as `rewritten`. This is documented in the `check_text` docstring, characterised by `test_a_wrong_pick_between_two_names_in_the_window_is_a_known_limit`, and mitigated by the clarify path and by the trace recording both texts. ROADMAP criterion 5 as written ("wrong pronoun resolution ... caught by a test") is met by the absent-entity case; the in-window case is a real residual risk that Phase 4's oracle arm should measure.
2. **Other documented guard limits:** lowercase invented context, numbers spelled out, capitalised non-ASCII names, constraints outside the fixed word list. A false rejection falls back to the raw message (safe direction).
3. **Cold Ollama load (about 30 s):** the first follow-up after idle may fall back with reason `timeout`. Visible, not silent; fail-open by decision D2.
4. **Rejected rewrite text is stored in single-document traces** as `rejected_question` (trace only, never in the response; tested). It is derived from upload text, so it is deleted with the document folder like every other trace.
5. **ROADMAP criterion 3 still reads "following open decision D2"**; D2 is now resolved (fail-open, flagged). Wording tidy-up only.

### Gaps Summary

No gaps. The goal is achieved in the codebase: with the switch on, a pronoun follow-up is rewritten into a standalone question before retrieval (retrieval, trace, answer prompt and stored turn all reflect it), an ambiguous follow-up gets exactly one clarifying question in the normal response and SSE shape (never two in a row), a topic switch cuts the history for both the rewriter and the answer prompt, and the four named bad rewrites fall back with a recorded reason. The switch ships off, single-turn behaviour is unchanged with it off (Phase 2 key-set tests), the protected prompt, history, guard, pipeline and index files are byte-identical to P3_BASE, and the retrieval invariant (hit@5 0.865, mrr 0.663) was reproduced live.

---

_Verified: 2026-10-25_
_Verifier: Claude (gsd-verifier)_
