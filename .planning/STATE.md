---
gsd_state_version: "1.0"
current_phase: 3
current_phase_name: Rewrite, clarify and topic switch
status: executing
stopped_at: Phase 3 context gathered
last_updated: "2026-10-22T05:21:11.006Z"
last_activity: 2026-10-21
last_activity_desc: Roadmap created (5 phases, 18/18 v1 requirements mapped)
state_head: 5b38a68b5de40858fff56cd66a88a995699974da
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 24
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-21)

**Core value:** A follow-up question with a pronoun retrieves the passages the standalone phrasing would, while a single-turn question produces exactly the prompt bytes and cached answer it produces today.
**Current focus:** Phase 1 - Safety net and prompt seam

## Current Position

Phase: 3 (Rewrite, clarify and topic switch) — READY TO EXECUTE
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

- [Phase 1]: Server `max_model_len` is not recorded anywhere; reading it needs the PuTTY tunnel to `127.22.10.1:30007` to be up (the user reconnects it if the model-server check says "connection refused").
- [Phase 2]: Existing test `test_the_streamed_response_equals_the_ordinary_one` must ignore `conversation_id`; the new conversation subfolder must not change `chat/*.json` trace-count assertions.
- [Phase 3]: Rewriter behaviour is unmeasured (constraint dropping, parse failures, Ollama context size and silent truncation); the provider module is hook-flagged, so test with a spy instead of reading it.
- [Phase 4]: Golden-set power is low (one question is 2.7 points; a 12-16 turn set cannot clear an 8-point band); rewriter and judge are both `qwen2.5:7b`, so re-score a borderline result with another judge.
- Standing constraints: baseline `python -m pytest tests -q` is 591 passed, 2 skipped (593 collected); retrieval invariant hit@5 0.865, mrr 0.663.
- Standing constraints: never name `rag/common/llm.py` or `tests/test_vllm.py` in a shell command, never glob `tests/` or `rag/common/`, never read `.env`; commit messages go through `git commit -F <file>`; `SYSTEM_PROMPT` and `DOCUMENT_SYSTEM_PROMPT` stay word for word; `get_llm(..., cache_dir=None)` for every service LLM.

## Deferred Items

Items acknowledged and deferred at milestone close, most recent first:

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| *(none)* | | | | |

## Session Continuity

Last session: 2026-10-22T00:07:57.904Z
Stopped at: Phase 3 context gathered
Resume file: .planning/phases/03-rewrite-clarify-and-topic-switch/03-CONTEXT.md
