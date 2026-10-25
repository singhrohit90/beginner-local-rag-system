---
gsd_state_version: "1.0"
current_phase: 5
current_phase_name: Chat page and honest docs
status: executing
stopped_at: Phase 5 context gathered
last_updated: "2026-10-23T06:19:26.972Z"
last_activity: 2026-10-21
last_activity_desc: Roadmap created (5 phases, 18/18 v1 requirements mapped)
state_head: abaf8e28cabb336cfd663b42fa0ff455c27c1f59
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 39
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-21)

**Core value:** A follow-up question with a pronoun retrieves the passages the standalone phrasing would, while a single-turn question produces exactly the prompt bytes and cached answer it produces today.
**Current focus:** Phase 1 - Safety net and prompt seam

## Current Position

Phase: 5 (Chat page and honest docs) — READY TO EXECUTE
Plan: 0 of TBD in current phase
Status: Ready to execute
Last activity: 2026-10-21 - Roadmap created (5 phases, 18/18 v1 requirements mapped)

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: - min
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

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

- D1 Cross-document conversation storage: per-owner folder with delete cascade, or refuse history for cross-document scope. Resolve in discuss-phase for Phase 2.
- D2 Rewrite-failure policy: fail-open with a visible flag, or fail-closed with an HTTP status. Resolve in discuss-phase for Phase 3.
- D3 Cap and window numbers: raise in Phase 1 (constants), pin in Phase 2 after `max_model_len` is recorded.
- Smaller points: conversation file format (JSONL or atomic JSON), concurrent-request policy (409 or write-only lock), `keep_traces` gating of conversation files, rewriter model and setting name, question slot in the answer prompt (Phase 4), reload-resume GET (v2).

### Blockers/Concerns

- [Phase 2 start]: max_model_len not read on 2026-10-24 (tunnel down, connection refused on 127.22.10.1:30007); `MODEL_CONTEXT_TOKENS` in `rag/query/history.py` uses the 8192 floor; re-read it with the command in `docs/models.md` (Context window) before pinning D3.
- [Phase 2]: Existing test `test_the_streamed_response_equals_the_ordinary_one` must ignore `conversation_id`; the new conversation subfolder must not change `chat/*.json` trace-count assertions.
- [Phase 3]: Rewriter behaviour is unmeasured (constraint dropping, parse failures, Ollama context size and silent truncation); the provider module is hook-flagged, so test with a spy instead of reading it.
- [Phase 4]: Golden-set power is low (one question is 2.7 points; a 12-16 turn set cannot clear an 8-point band); rewriter and judge are both `qwen2.5:7b`, so re-score a borderline result with another judge.
- Standing constraints: pytest baseline after Phase 1 is 702 passed, 2 skipped (704 collected; OpenSearch up on 2026-10-25); before Phase 1 it was 591 passed, 2 skipped (593 collected); retrieval invariant hit@5 0.865, mrr 0.663, unchanged after the Phase 1 seam.
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

## Deferred Items

Items acknowledged and deferred at milestone close, most recent first:

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| *(none)* | | | | |

## Session Continuity

Last session: 2026-10-22T12:36:27.826Z
Stopped at: Phase 5 context gathered
Resume file: .planning/phases/05-chat-page-and-honest-docs/05-CONTEXT.md
