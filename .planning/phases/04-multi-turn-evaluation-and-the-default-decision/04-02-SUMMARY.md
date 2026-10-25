---
phase: 04-multi-turn-evaluation-and-the-default-decision
plan: 02
status: complete
requirements: [EVAL-03]
---

# 04-02 Summary: the shipping rule, committed before any run

`docs/chat_memory_eval.md` holds only the rule section, verbatim from the plan, committed alone.

RULE_COMMIT=9baf0f3334f3158aeafd77db5a07bdbbef9cd02c

## Verify outputs

- First-commit check (single adding commit, first line is the rule heading, no `## Results`, only the doc in the
  commit): exit 0.
- Pinned phrases: 9 of 9 found.
- `grep -c '^## '` = 1; address/IP/URL grep = 0.

## Rule arithmetic

```
rule arithmetic ok [4, 4, 4, 4, 4, 4, 4, 4, 5] 0.194
```

Full suite in the worktree: see `.planning/runs/20261021-1840-chat-memory/wave-p4-04-02-1.txt`.

## Deviations

None.
