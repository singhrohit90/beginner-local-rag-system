---
phase: 01-safety-net-and-prompt-seam
plan: 02
subsystem: docs
tags: [max_model_len, context-window, vllm, docs]
requires: []
provides:
  - "docs/models.md Context window section (dated not-read record, 8192 floor, re-read command)"
  - "STATE.md Phase 2 blocker line for max_model_len"
affects: [01-05, phase-2-history-caps]
tech-stack:
  added: []
  patterns: []
key-files:
  created: []
  modified: [docs/models.md, .planning/STATE.md]
key-decisions:
  - "Used the 8192-token floor (D-11) because the server was unreachable (D-13); prompt budget at the floor is 8192 - 3600 = 4592 tokens"
requirements-completed: [PRMT-02]
duration: 5min
completed: 2026-10-24
status: complete
actuals:
  tokens: 1200
  tasks: 2
  commits: 2
plan_head_before: 939cffe021dd82439bf89c8daccebd532bd50c43
plan_head_after: 9e2e9e0cac7c62118221aedcd1ba27eeb5b361dd
---

# Phase 1 Plan 02: Generator context window record Summary

The generator server's `max_model_len` could not be read (PuTTY tunnel down), so `docs/models.md` and `STATE.md` record the dated not-read reason, the 8192-token floor and the command to re-read it at the start of Phase 2.

## Probe result

- Probe attempted once (10 s timeout), no retry.
- Case: **(b) tunnel down**
- Printed error line: `urllib.error.URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>`
- Date: 2026-10-24
- Floor recorded: 8192 tokens for `MODEL_CONTEXT_TOKENS`; output limit 3600 (600 answer + 3000 thinking), so 4592 prompt tokens at the floor.

## Commits

| Task | Name | Commit |
|------|------|--------|
| 1 | Record that max_model_len could not be read (`docs/models.md`) | 85dfecd |
| 2 | Note the max_model_len outcome for phase 2 (`.planning/STATE.md`, one bullet) | 9e2e9e0 |

## Verification

- `grep -n '^## Context window' docs/models.md` printed line 22.
- Not-read regex matched line 24 of `docs/models.md`; `MODEL_CONTEXT_TOKENS` appears once in the file.
- STATE.md regex `max_model_len (not read on ...)` matched line 78; `git show 9e2e9e0` changes one line only.
- `git diff --name-only 853f021 -- rag` lists only allowed files (exit 0): nothing under `rag/` changed.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None.

## Self-Check: PASSED

- docs/models.md and STATE.md edits present; commits 85dfecd and 9e2e9e0 are ancestors of HEAD.
