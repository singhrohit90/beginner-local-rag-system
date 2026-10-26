# Multi-turn golden set: review state

Step-by-step instructions for reviewing these rows, written for someone new to the project: `docs/chat_memory_owner_tasks.md`, Task A.

`data/golden/ddia_conversations.jsonl` was drafted by the executor in an unattended run (Phase 4, D-03). Every row is
an executor draft and is marked `"review": "pending-human"`. Answer rows reuse the gold pages, key facts and evidence
terms of the single-turn question named by `source_id`; the turns, the message and the shortened or converted
wordings are the executor's.

How to review: read each row against the book (PDF page numbers, printed page + 22). When the turns are true to the
book, the message reads like a real follow-up and the standalone question is what the message means, change
`"review": "pending-human"` to `"review": "approved"`. If any row's text changes, re-run
`python -m rag.experiments.conversation --check-set` and repeat the scored run of plan 04-08. Condition (f) of the
committed shipping rule in `docs/chat_memory_eval.md` keeps rewriting off until every row is approved.
`data/golden/conversations_draft.jsonl` (the Phase 3 draft) is superseded by this set and is read by no code.

## Baseline check (off and oracle arms only, no rewriter)

Command: `python -m rag.experiments.conversation --check-set --name p4-check-set`

Date: 2026-10-25T15:45Z, commit ba6900e (the set as committed; no rewording round was needed).

```
discriminating 8/16 pronoun+constraint items miss with off
oracle misses 4
```

Labels: `discriminating` (off misses, oracle hits), `control` (off equals oracle), `oracle-miss` (even the standalone
question misses at hit@5), `clarify` (scored apart, no retrieval).

| id | category | expect | source_id | off | oracle | label | review |
|----|----------|--------|-----------|-----|--------|-------|--------|
| c001 | pronoun_follow_up | answer | q015 | 1 | 1 | control | pending-human |
| c002 | pronoun_follow_up | answer | q016 | 0 | 1 | discriminating | pending-human |
| c003 | topic_switch | answer | q019 | 0 | 0 | oracle-miss | pending-human |
| c004 | topic_switch | answer | q026 | 1 | 1 | control | pending-human |
| c005 | ambiguous_follow_up | clarify | - | - | - | clarify | pending-human |
| c006 | ambiguous_follow_up | clarify | - | - | - | clarify | pending-human |
| c007 | standalone_in_conversation | answer | q028 | 1 | 1 | control | pending-human |
| c008 | standalone_in_conversation | answer | q017 | 1 | 1 | control | pending-human |
| c009 | pronoun_follow_up | answer | q021 | 1 | 1 | control | pending-human |
| c010 | pronoun_follow_up | answer | q027 | 1 | 1 | control | pending-human |
| c011 | pronoun_follow_up | answer | q031 | 0 | 1 | discriminating | pending-human |
| c012 | pronoun_follow_up | answer | q034 | 0 | 1 | discriminating | pending-human |
| c013 | pronoun_follow_up | answer | q022 | 1 | 1 | control | pending-human |
| c014 | pronoun_follow_up | answer | q023 | 0 | 1 | discriminating | pending-human |
| c015 | pronoun_follow_up | answer | q014 | 0 | 0 | oracle-miss | pending-human |
| c016 | pronoun_follow_up | answer | q025 | 0 | 1 | discriminating | pending-human |
| c017 | topic_switch | answer | q018 | 1 | 1 | control | pending-human |
| c018 | topic_switch | answer | q020 | 1 | 1 | control | pending-human |
| c019 | topic_switch | answer | q037 | 1 | 1 | control | pending-human |
| c020 | topic_switch | answer | q040 | 1 | 1 | control | pending-human |
| c021 | standalone_in_conversation | answer | q002 | 1 | 1 | control | pending-human |
| c022 | standalone_in_conversation | answer | q030 | 0 | 0 | oracle-miss | pending-human |
| c023 | standalone_in_conversation | answer | q036 | 0 | 0 | oracle-miss | pending-human |
| c024 | standalone_in_conversation | answer | q042 | 1 | 1 | control | pending-human |
| c025 | standalone_in_conversation | answer | q008 | 1 | 1 | control | pending-human |
| c026 | standalone_in_conversation | answer | q010 | 1 | 1 | control | pending-human |
| c027 | ambiguous_follow_up | clarify | - | - | - | clarify | pending-human |
| c028 | ambiguous_follow_up | clarify | - | - | - | clarify | pending-human |
| c029 | constraint_follow_up | answer | q041 | 1 | 1 | control | pending-human |
| c030 | constraint_follow_up | answer | q029 | 1 | 1 | control | pending-human |
| c031 | constraint_follow_up | answer | q003 | 0 | 1 | discriminating | pending-human |
| c032 | constraint_follow_up | answer | q012 | 1 | 1 | control | pending-human |
| c033 | constraint_follow_up | answer | q011 | 1 | 1 | control | pending-human |
| c034 | constraint_follow_up | answer | q013 | 0 | 1 | discriminating | pending-human |

The `discriminating 8/16` line counts every pronoun or constraint row whose off hit@5 is 0, including the oracle-miss
row c015; with the oracle-miss rows set apart, 7 pronoun and constraint rows can show a gain.
