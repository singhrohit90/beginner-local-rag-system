---
phase: 05-chat-page-and-honest-docs
plan: 04
status: complete
requirements: [DOCS-01]
---

# 05-04 Summary: honest relabel of the conversation-memory interview note

## Commits

| Task | Commit | Subject |
|------|--------|---------|
| 1 | 104efc2 | docs(05-04): label follow-up memory built with its recorded numbers |
| 2 | 53e1257 | docs(05-04): split compaction into the built cap and the unbuilt summary and fix the interview index |

Each commit used an explicit pathspec and holds only the interview files.

## What changed

- `interview/05_conversation_memory_and_cost.md` line 5: conversation memory **built**, rewriting off by default
  with the Decision text quoted and the provisional wording; compaction, cost tracking and a tracing tool
  **not built**. No "single-turn" left.
- Line 7: `**Not measured**` defined (the note uses it).
- Section 1 "In this repo": five **Built.** bullets (store, history block, rewrite step, page, golden set and
  experiment; tests cited only where the files exist), one **Measured.** bullet, one **Measured, rerun.** bullet
  (phase gate: 16 rewritten, hit@5 changed on 6, citing 04-10-SUMMARY.md), one **Not measured.** bullet (answer
  arm, question slot, judge-as-rewriter not run because the generator was unreachable; qwen not compared with
  gpt-oss; `max_model_len` not read, `MODEL_CONTEXT_TOKENS` floor 8192), where it plugs in, and the backlog pointer.
- Section 2 "In this repo": three **Built.** bullets (window and word cuts with their constants, the hard cap
  and its 409, the prompt-budget check with the passage budget) then one **Not built.** bullet (rolling summary,
  structured memory, retrieval over history, the 70% trigger). The stateless sentence is gone.
- Section 3 and the One-line revision are unchanged since P5_BASE.
- `interview/README.md` index row: follow-ups built and measured in `docs/chat_memory_eval.md` (rewriting ships
  off); compaction and cost tracking not built. Line 10 unchanged.

## Measured bullet as written

- **Measured.** On 30 answer items, strict evidence-aware hit@5 was 0.633 with rewriting off and 0.733 with it on (mrr 0.461 and 0.592; hand-written standalone questions 0.867): a gain of 10.0 points against a band of 10.0 points, 6 wins and 3 losses, and one standalone question lost. The 37 golden questions asked as first turns gave identical results with zero rewriter calls; with one unrelated earlier turn in front of them (reported, not gating) the rewriter rewrote 17 and hit@5 changed on 6 of 37. Decision: ships off (failed: a, c, f; provisional: items pending human review). Why: the rule ships rewriting only when all six of its conditions hold, among them a gain strictly above the band, no standalone question lost and every item approved; here the gain equals the band, one standalone question was lost, and all 34 items are pending human review, so the numbers are provisional. Source: `docs/chat_memory_eval.md`.

Not measured was used (and defined on line 7).

## Check outputs

- `section 1 ok`
- `paths ok`
- `section 2 ok`
- `index ok` (run with `tr -d '\r'` on the working-copy side of the three equality comparisons: the worktree
  checkout has CRLF line ends while `git show` prints the LF blob)
- Full suite in the worktree: `932 passed, 3 skipped` (saved to
  `.planning/runs/20261021-1840-chat-memory/wave-p5-05-04-1.txt`; third skip is the fresh-worktree
  `data/processed` skip).
