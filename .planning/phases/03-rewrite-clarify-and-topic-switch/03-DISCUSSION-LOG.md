# Phase 3: Rewrite, clarify and topic switch - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-22
**Phase:** 03-rewrite-clarify-and-topic-switch
**Mode:** `--auto` — every question took the recommended option without a user prompt
**Areas discussed:** Switch and rewriter model, Skip gate, Output protocol and guards, Rewrite-failure policy (D2), Response and trace, Clarify, Topic switch, Golden authoring timing

---

## Switch and rewriter model

| Option | Description | Selected |
|--------|-------------|----------|
| One switch `RAG_REWRITE` (default off) for rewrite + clarify + topic switch | Simpler; R4 only meaningful with rewrite on | ✓ |
| Separate switches | More combinations to test | |

| Option | Description | Selected |
|--------|-------------|----------|
| `RAG_REWRITER`, default `ollama:qwen2.5:7b` | Local, fast; listed first | ✓ |
| `RAG_REWRITE_LLM`, default = service LLM (reasoning model) | Slow to first token | |

## Skip gate

Selected: deterministic gate (no history → skip; ≥10 words and no anaphora marker → skip; <6 words → call), erring toward calling the model.

## Output protocol and guards

Selected: one tagged line (`STANDALONE` / `REWRITE:` / `CLARIFY:` / `NEW_TOPIC:`), regex parse; guards `dropped_constraint`, `invented_detail`, `too_long`, `flagged`, `topic_leak`; failed guard → raw message with recorded reason.

## Rewrite-failure policy (D2)

| Option | Description | Selected |
|--------|-------------|----------|
| A: fail-open, raw message, `rewrite.status = "fallback"` visible in response and trace | Chat stays usable when the rewriter is down | ✓ |
| B: fail-closed, HTTP 502 before any SSE byte | Literal RWR-02 wording; no silent fallback | |

Note: RWR-02's literal wording favours B; the requirement marks the policy as open (D2) and ROADMAP SC3 allows either. Recorded as an assumption for the owner.

## Response and trace

Selected: retrieval on the effective question; trace and response carry original, rewritten, status, reason, `rewrite_ms`; answer prompt uses the rewritten question until Phase 4 measures the alternative.

## Clarify

Selected: short-circuit before retrieval, normal response shape with `kind: "clarify"`, no tokens on the stream, stored as a `kind: "clarify"` turn; `allow_clarify=False` after a clarification.

## Topic switch

Selected: `NEW_TOPIC:` from the same rewriter call; history window restarts at the latest `topic_start` turn. Rejected: embedding-similarity detection.

## Golden authoring timing

Selected: draft multi-turn items in `data/golden/conversations_draft.jsonl` during this phase, before tuning the rewriter prompt; loader and experiment in Phase 4.

## Claude's Discretion

- Rewriter prompt wording, gate/guard regex details, `RewriteResult` field names

## Deferred Ideas

- Measurement and default flip (Phase 4); Ollama JSON-schema format; page panel for the rewritten question (v2); separate switches
