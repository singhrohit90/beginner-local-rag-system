# Phase 1: Safety net and prompt seam - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-21
**Phase:** 01-safety-net-and-prompt-seam
**Mode:** `--auto` — every question took the recommended option without a user prompt
**Areas discussed:** Snapshot test shape, Spotlight nonce, Seam shape, History helpers and D3 constants, Reading max_model_len, Recording the invariants

---

## Snapshot test shape

| Option | Description | Selected |
|--------|-------------|----------|
| Full-text files per hand-built case plus sha256 manifest for the golden set | Readable diffs for the 3x2x4 cases; digests keep 45 golden prompts to one file | ✓ |
| Full text for everything | 45 near-identical golden files | |
| Digests only | A drift gives no readable diff | |

**Auto choice:** full text for the hand-built cases, digests for the golden questions; no update switch; committed before any edit.

## Spotlight nonce

| Option | Description | Selected |
|--------|-------------|----------|
| `monkeypatch.setattr("rag.security.defenses._NONCE_KEY", ...)` in the test | Deterministic, no environment or import-order dependence | ✓ |
| Set `RAG_NONCE_KEY` via `monkeypatch.setenv` | Key is read at import time; fragile | |
| Exclude spotlight from the snapshot | Leaves one style unpinned | |

## Seam shape

| Option | Description | Selected |
|--------|-------------|----------|
| `history_block: str = ""` keyword on each builder and per call on `RagPipeline.answer/stream` | Empty default is the old expression; no trace or constructor state | ✓ |
| `history_block` on the `RagPipeline` constructor | A pipeline object would carry one conversation's state | |
| Store the block on `Trace` | Changes the trace dataclass and old trace files | |

Block position: between passages and the `Question:` line (chosen over "before the passages" so the question stays last).

## History helpers and D3 constants

| Option | Description | Selected |
|--------|-------------|----------|
| D3 Option A: window 6, block 400 words, answers 40, question 60, stored cap 50 | Safe even at an 8,192 context window | ✓ |
| D3 Option B: window 6, block 600 words, answers 60, stored cap 20 turns / 8,000 words | Needs the real `max_model_len` first | |

Provisional only; Phase 2 pins D3 after `max_model_len` is recorded.

## Reading max_model_len

| Option | Description | Selected |
|--------|-------------|----------|
| One-off `GET {REMOTE_URL}/models`, number written into `docs/models.md` | No code change in the hook-flagged `rag/common/` folder | ✓ |
| Extend `rag.common.llm_check` to print it | Touches `rag/common/`; not needed at runtime | |

Tunnel-down fallback: record "not read", use an 8192 floor, write a blocker to STATE.md, re-read in Phase 2.

## Recording the invariants

| Option | Description | Selected |
|--------|-------------|----------|
| Paste outputs into the plan SUMMARY.md and phase VERIFICATION.md | `CLAUDE.md` already holds the invariant; no new docs file | ✓ |
| New `docs/baselines.md` | Duplicates `CLAUDE.md` | |

## Claude's Discretion

- History block header wording and truncation marker
- Snapshot fixture passage text and page numbers
- Whether the digest manifest also stores question text

## Deferred Ideas

- Dropped-turn reporting from `window()` (Phase 2)
- `llm_check` printing `max_model_len` (later, if needed at runtime)
- Per-turn caps with a longer last assistant turn (Phase 2, D3)
