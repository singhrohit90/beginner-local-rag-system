---
phase: 05-chat-page-and-honest-docs
plan: 03
status: complete
requirements: [DOCS-01]
---

# 05-03 Summary: Step 11 in the pipeline README and the backlog

## Commits

| Task | Commit | Subject |
|------|--------|---------|
| 1 | f69011e | docs(05-03): add Step 11 chat memory to the pipeline README |
| 2 | fac0604 | docs(05-03): mark chat memory done in the backlog and point Step 8 to Step 11 |

Each commit used an explicit pathspec (`rag/README.md`; then `rag/README.md docs/backlog.md`).

## Decision line copied

`Decision: ships off (failed: a, c, f; provisional: items pending human review)`

The results are provisional: `docs/chat_memory_eval.md` says "34 of 34 items pending-human; the numbers are
provisional until every item is approved and the run is repeated". Step 11 says so in those words, and says the
answer arm, the question slot and the judge-versus-rewriter question are not measured (generator unreachable).

## What was written

- `rag/README.md` `## Step 11: chat memory` (last Step): request line; conversations and routes; storage
  and delete (`rag/api/conversations.py`, `purge_document`); history block with `HISTORY_WINDOW_TURNS = 6`,
  `HISTORY_QUESTION_MAX_WORDS = 60`, `HISTORY_ANSWER_MAX_WORDS = 40`, `HISTORY_BLOCK_MAX_WORDS = 400`; caps
  `CONVERSATION_MAX_TURNS = 50`, `CONVERSATION_MAX_STORED_WORDS = 20000`; `MODEL_CONTEXT_TOKENS = 8192` stated as a
  floor in the code with the server's real context length not read; the three `guarded()` strings; `RAG_REWRITE`
  (off by default) and `RAG_REWRITER` default `ollama:qwen2.5:7b`; the page; the `Measured:` paragraph (30 answer
  items, off 0.633 / on 0.733 hit@5, mrr 0.461 / 0.592, oracle 0.867, gain 10.0 vs band 10.0, 6 wins 3 losses,
  p = 0.2539, one standalone loss, regression 37/37 identical with zero rewriter calls).
- Step 8 ends with a pointer sentence to Step 11.
- `docs/backlog.md`: `**Chat memory: done** (2026-10-26)` replacing "Chat has no memory"; four open bullets in
  order (compaction at about 70%, reload-resume GET, rewrite shown in the pipeline panel, turn counter); a
  Conversation retention bullet after the traces retention bullet; the rewriting line split into a done
  rewriting item (decision copied) and an open intent-classification item.

## Check outputs

- `numbers ok`
- `sources ok`
- `backlog ok`
- `order ok`
- `git diff --quiet HEAD -- docs/chat_memory_eval.md rag/api rag/query` holds.
- Full suite in the worktree: `932 passed, 3 skipped` (saved to
  `.planning/runs/20261021-1840-chat-memory/wave-p5-05-03-1.txt`; the third skip is the absent
  `data/processed/ddia.pages.jsonl` of a fresh worktree).

## Deviations

- Added after Task 2 (third commit): an "Over-rewriting" paragraph after the Measured paragraph in Step 11:
  with one unrelated earlier turn, qwen rewrote 16 of the 37 single-turn questions in the phase gate run (17 in
  the p4-qwen run in the eval file) and hit@5 changed on 6 of 37, citing 04-10-SUMMARY.md; stated as not part
  of the shipping rule. It sits outside the Measured paragraph, so the numbers check is unaffected; both
  checks were rerun and print `numbers ok` and the path and privacy part of `sources ok`.
