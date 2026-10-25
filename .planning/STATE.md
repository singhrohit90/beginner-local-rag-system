---
gsd_state_version: "1.0"
current_phase: 03
current_phase_name: Rewrite, clarify and topic switch
status: executing
stopped_at: Phase 2 complete, ready to execute Phase 03
last_updated: "2026-10-25T06:01:38.035Z"
last_activity: 2026-10-25
last_activity_desc: Phase 2 complete, transitioned to Phase 03
state_head: c157aad897d1cbf7435a49671720f83eb2610e67
progress:
  total_phases: 5
  completed_phases: 2
  total_plans: 39
  completed_plans: 16
  percent: 40
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-21)

**Core value:** A follow-up question with a pronoun retrieves the passages the standalone phrasing would, while a single-turn question produces exactly the prompt bytes and cached answer it produces today.
**Current focus:** Phase 1 - Safety net and prompt seam

## Current Position

Phase: 03 — Rewrite, clarify and topic switch
Plan: Not started
Status: Ready to execute
Last activity: 2026-10-25 — Phase 2 complete, transitioned to Phase 03

Progress: [████░░░░░░] 40%

## Performance Metrics

**Velocity:**
- Total plans completed: 16
- Average duration: - min
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 7 | - | - |
| 2 | 9 | - | - |

**Recent Trend:**
- Last 5 plans: none yet
- Trend: -

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Five phases (safety net, store plus memory, rewrite, evaluation, page plus docs); work stays on `flow/chat-memory`, no phase branches, no pushes
- [Roadmap]: A requirement split across phases is mapped to the phase where it is verified complete (history in the prompt, untrusted history and the hard cap are Phase 2; the page id handling is Phase 5)
- [Roadmap]: The rewrite sits behind one switch that defaults to off until Phase 4 measures it; "off with the numbers recorded" is an acceptable result

### Pending Todos

Open decisions (not settled; do not pick a side outside discuss-phase). Detail in ROADMAP.md "Open Decisions" and `.planning/research/SUMMARY.md`:

- D1 resolved in Phase 2 (D-01): cross-document conversations are stored under `data/uploads/_conversations/{owner_key}/` and removed when any document in their scope is deleted.
- D2 Rewrite-failure policy: fail-open with a visible flag, or fail-closed with an HTTP status. Resolve in discuss-phase for Phase 3.
- D3 pinned in Phase 2 (D-15): window 6 turns, block 400 words, answers 40 and questions 60 words, 50 turns and 20000 stored words per conversation, `MODEL_CONTEXT_TOKENS` from `docs/models.md`.
- Smaller points: conversation file format (JSONL or atomic JSON), concurrent-request policy (409 or write-only lock), `keep_traces` gating of conversation files, rewriter model and setting name, question slot in the answer prompt (Phase 4), reload-resume GET (v2).

### Blockers/Concerns

- [Phase 2, 2026-10-25]: max_model_len not read on 2026-10-25 (`ConnectionResetError: [WinError 10054]`, the tunnel forward resets; owner deferred the re-read to the merge gate); `MODEL_CONTEXT_TOKENS` stays at the 8192 floor for Phase 2; re-read it with the command in `docs/models.md` (Context window) before raising any history cap.
- [Phase 2, done 2026-10-25]: `test_the_streamed_response_equals_the_ordinary_one` needed no edit (it compares a fixed key tuple; RESEARCH Pitfall 10 superseded D-06's clause); separate ids are pinned by `test_questions_without_an_id_start_separate_conversations`; conversation files live in `chat/conversations/` or `_conversations/`, and every `chat/*.json` trace-count test passed unchanged.
- [Phase 2, owner flag]: conversation files are kept when `keep_traces` is off (D-11: history is functional state); they live until a document in their scope is deleted; until Phase 5 the page sends no `conversation_id`, so every page question writes an orphan one-turn conversation file, including all-documents answers that no trace keeps today; a retention period is not built yet (Phase 5 docs and backlog); the budget refusal reuses the full-conversation 409 (D-16), wording left for Phase 5.
- [Phase 3]: Rewriter behaviour is unmeasured (constraint dropping, parse failures, Ollama context size and silent truncation); the provider module is hook-flagged, so test with a spy instead of reading it.
- [Phase 4]: Golden-set power is low (one question is 2.7 points; a 12-16 turn set cannot clear an 8-point band); rewriter and judge are both `qwen2.5:7b`, so re-score a borderline result with another judge.
- Standing constraints: pytest baseline after Phase 2 is 741 passed, 2 skipped (743 collected; OpenSearch up on 2026-10-25); after Phase 1 it was 702 passed, 2 skipped (704 collected; OpenSearch up on 2026-10-25); before Phase 1 it was 591 passed, 2 skipped (593 collected); retrieval invariant hit@5 0.865, mrr 0.663, unchanged after Phase 2.
- Standing constraints: never name `rag/common/llm.py` or `tests/test_vllm.py` in a shell command, never glob `tests/` or `rag/common/`, never read `.env`; commit messages go through `git commit -F <file>`; `SYSTEM_PROMPT` and `DOCUMENT_SYSTEM_PROMPT` stay word for word; `get_llm(..., cache_dir=None)` for every service LLM.

## Parked

From the approval brief (gate 1, 2026-10-24); see `.planning/runs/20261021-1840-chat-memory/brief.md`.
- Review level -- Park until it hurts: local `/code-review high`; raise to ultra when a merged phase shows a bug review should have caught.
- Rewrite ships OFF this run -- decided: draft golden rows go to the user after the merge (`MULTITURN_REVIEW.md`), then phase 4's scored run is rerun.
- Compaction -- what: rolling summary at ~70% of the history budget; why later: the hard cap is enough; back when a 409 "conversation full" appears in use.
- CONV-05..08 -- what: resume on reload, delete one conversation, per-turn citations, show rewritten question; why later: beyond R1-R10; back when phase 5 merges.
- Cost/tracing then tool calling -- why later: next project; back when this run merges.
- Keycloak then Docker -- why later: single local user; back when the API is shared.
- Coding-standards gate -- why later: needs its own session; back when the doc exists.
- Rest of docs/backlog.md -- why later: unrelated to memory; back after this run.

- max_model_len -- **Park until step: merge gate**: re-read with the command in docs/models.md once the tunnel forward works (2026-10-25: listener up, forward resets with WinError 10054); replace the 8192 floor in docs/models.md and MODEL_CONTEXT_TOKENS; owner deferred it in chat.

- D-11 retention (phase 2 keeps answer text for every page question until phase 5 adds the page conversation_id) -- **Park until step: phase 5**; listed at the merge gate.
- Flaky test tests/test_api.py::test_a_delete_during_a_load_leaves_nothing_in_the_store[one document] -- **Park until it hurts**: failed once under load in a worktree, passed every rerun; unparked when it fails in a gate run.

## Deferred Items

Items acknowledged and deferred at milestone close, most recent first:

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| *(none)* | | | | |

## Session Continuity

Last session: 2026-10-22T12:36:27.826Z
Stopped at: Phase 2 complete, ready to execute Phase 03
Resume file: .planning/phases/05-chat-page-and-honest-docs/05-CONTEXT.md
