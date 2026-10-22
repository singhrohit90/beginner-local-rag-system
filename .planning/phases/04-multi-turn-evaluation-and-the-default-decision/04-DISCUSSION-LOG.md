# Phase 4: Multi-turn evaluation and the default decision - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-22
**Phase:** 04-multi-turn-evaluation-and-the-default-decision
**Mode:** `--auto` — every question took the recommended option without a user prompt
**Areas discussed:** Golden set, Experiment, Shipping rule, Rewriter model, Question slot, Judge, Applying the decision

---

## Golden set

Selected: `data/golden/ddia_conversations.jsonl`, five categories, at least 30 scored follow-ups with half baseline misses; own loader `rag/observe/golden_conversations.py`; executor-drafted rows marked `pending-human` (unattended run). Rejected: blocking human authoring checkpoint.

## Experiment

Selected: `python -m rag.experiments.conversation`, arms off / on / oracle / concat, teacher-forced histories, paired win/tie/loss, per-category, gate precision/recall, latency, regression arm on the 37 questions; offline smoke test.

## Shipping rule

| Option | Description | Selected |
|--------|-------------|----------|
| Band `max(8, 300/n)` on hit@5, net wins ≥ 3, no standalone loss, regression identical, fallback ≤ 10%, all items approved | Written before the run | ✓ |
| Fixed 8-point band only | Ignores n of the new set | |

## Rewriter model

Selected: qwen2.5:7b vs gpt-oss-20b low effort when the tunnel is up; higher hit@5, then lower latency.

## Question slot

Selected: score both slots with `--answers`; keep rewritten unless original wins by more than the band.

## Judge

Selected: retrieval drives the rule (no judge); answer scoring via `judge_facts`, flagged when rewriter and judge share a model.

## Applying the decision

Selected: default flips only by the rule, in its own commit; tunnel/Ollama down → default off, blocker recorded.

## Claude's Discretion

- Table layout, helper names, concat join

## Deferred Ideas

- Independent hosted judge, Ollama JSON format, larger set
