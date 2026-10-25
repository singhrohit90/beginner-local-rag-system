---
phase: 03-rewrite-clarify-and-topic-switch
plan: 03
subsystem: evaluation data
tags: [golden-set, multi-turn, draft]
requires: []
provides:
  - data/golden/conversations_draft.jsonl (8 draft rows, pending human review)
affects: [phase-04 loader and experiment]
key-files:
  created:
    - data/golden/conversations_draft.jsonl
  modified: []
decisions:
  - "D-15 authorship: executor drafts, every row marked \"review\": \"pending-human\"; owner review carried to STATE.md by the orchestrator / plan 03-08"
  - "Gold pages reused verbatim from committed ddia_questions.jsonl rows; no page looked up or invented"
metrics:
  tasks: 2
  files: 1
---

# Phase 3 Plan 03: Draft multi-turn golden items Summary

Eight draft conversation rows (c001 to c008) in `data/golden/conversations_draft.jsonl`, two per category, built on committed single-turn golden rows so every gold page is already a PDF page. No code; nothing under `rag/` or `tests/` reads the file.

## Commits

- 0bdc297 `data(03-03): draft multi-turn golden items for owner review`
- Task 2 made no row changes (verify passed first time), so no second data commit.

## Rows and sources

| Row | Category | expect | source_id | gold_pages |
|-----|----------|--------|-----------|------------|
| c001 | pronoun_follow_up | rewrite | q015 (B-tree writes data twice) | [[106, 106]] |
| c002 | pronoun_follow_up | rewrite | q016 (fencing a stale write after lock expiry); a more recent distractor turn about leader failure detection | [[325, 325]] |
| c003 | topic_switch | new_topic | q019 (Bloom filters in log-structured engines); earlier turn on two-phase commit | [[101, 101]] |
| c004 | topic_switch | new_topic | q026 (monotonic reads); earlier turn on column-oriented storage | [[187, 187]] |
| c005 | ambiguous_follow_up | clarify | none (leader-based vs leaderless replication, "it") | [] |
| c006 | ambiguous_follow_up | clarify | none (LSM-trees vs B-trees, "that one") | [] |
| c007 | standalone_in_conversation | standalone | q028 (preventing dirty writes) | [[258, 258]] |
| c008 | standalone_in_conversation | standalone | q017 (linearizability vs eventual consistency) | [[346, 346]] |

Six distinct sources: q015, q016, q019, q026, q028, q017.

## Verification

All four lines below were run before the data commit and printed exactly as shown.

- Task 1 shape check: `draft ok 8`
- Task 1 isolation check: `draft isolated` (no `conversations_draft` reference under `tests` or `rag`; `ddia_questions.jsonl` and `about_questions.jsonl` unchanged)
- Task 2 referent and leak check: `rows ok`
- `grep -c '"review": "pending-human"' data/golden/conversations_draft.jsonl`: 8
- `git ls-files data/golden/conversations_draft.jsonl`: prints the path after commit 0bdc297 (tracked)

## Deviations from Plan

- STATE.md was not edited by this executor (orchestrator instruction); the owner flag below must be carried into `.planning/STATE.md` by the orchestrator (plan 03-08 does this).

## Owner flag

The eight rows in `data/golden/conversations_draft.jsonl` are drafts written by the Phase 3 executor, not by a human; D-15 asks for human-written standalone questions, so each row is marked `"review": "pending-human"`. Before Phase 4 loads the set, the owner must confirm or rewrite every row, delete the `review` key once a row is reviewed, add items until the set covers at least the categories ROADMAP Phase 4 criterion 1 names, and check baseline misses (PITFALLS.md Pitfall 11: a pronoun follow-up that rewrite-off retrieval already answers does not test the rewriter). Until then no code reads the file. Orchestrator: carry this paragraph to STATE.md.

## Self-Check: PASSED
