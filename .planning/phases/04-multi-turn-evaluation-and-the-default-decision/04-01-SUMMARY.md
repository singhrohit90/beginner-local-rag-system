---
phase: 04-multi-turn-evaluation-and-the-default-decision
plan: 01
status: complete
requirements: [EVAL-01]
---

# 04-01 Summary: contract check and the multi-turn golden loader

## Contract check (Wave 0)

```
contract ok
1
2
```

(`grep -c 'setting("RAG_REWRITE", "") == "1"' rag/api/main.py` = 1;
`grep -cE 'def (spied_settings|test_build_default_service_ships_the_switch_off)\(' tests/test_rewrite_api.py` = 2.)

Taken on flow/chat-memory with `git status --porcelain -- rag tests` empty, before any Phase 4 code commit:

P4_BASE=3744d3c325c9100ba59f928f15471c1c07417b1d

## What was built

`rag/observe/golden_conversations.py`: `CATEGORIES`, `EXPECTS`, `REVIEW_STATES`, `REQUIRED_KEYS`, `OPTIONAL_KEYS`,
`TURN_KEYS`, `MIN_CLARIFY_CANDIDATES`; frozen `GoldTurn` and `GoldConversation` (`validate`, `to_question`,
`expects_rewrite`); `normalise`, `parse_row`, `load_conversations`, `check_against_pages`, `main` CLI.
`rag/observe/golden.py` is unchanged (`git diff --quiet P4_BASE -- rag/observe/golden.py` exits 0).

## Verification

Tracer (one scratchpad row built from q015, checked against `data/processed/ddia.pages.jsonl`):

```
conversations 1 (answer 1, clarify 0)
...
problems 0
```

Task 2 verify: `validation ok` (14 bad shapes rejected; touching ranges kept apart; file order; blank line; empty
file; duplicate id). Fail-first: the same script against the Task 1 commit fails with
`AttributeError: 'GoldConversation' object has no attribute 'expects_rewrite'`.

`grep -cE 'raise ValueError\(f"\{self\.id\}'` = 23. No `rag.api`, `get_llm` or `data/uploads` in the module.

Full suite in the worktree: 838 passed, 2 skipped (tests are plan 04-06).

## Commits

- 49c1dd4 feat(04-01): add the multi-turn golden loader
- caafa3a feat(04-01): validate conversation rows

## Deviations

None. Task 1 was committed from a cut-down copy of the finished file so each task has its own commit.
