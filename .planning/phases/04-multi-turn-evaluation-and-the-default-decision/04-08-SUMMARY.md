---
phase: 04-multi-turn-evaluation-and-the-default-decision
plan: 08
status: complete
requirements: [EVAL-02, EVAL-03]
---

# 04-08 Summary: live scored run and the committed Results

Run unattended inside a `/flow` run on 2026-10-25, from worktree `work/04-08` cut at eb3f61a, with
`data/processed` and `runs` junctioned to the main checkout (run folders land in the main `runs/`).

## Precondition

- `python -m rag.experiments.conversation --check-rule` -> `rule commit 9baf0f3334f3158aeafd77db5a07bdbbef9cd02c;
  committed yes; clean yes; unchanged yes; first commit has results no` (exit 0)
- `git status --porcelain -- docs/chat_memory_eval.md data/golden rag` -> empty
- `python -m pytest tests/test_conversation_experiment.py tests/test_golden_conversations.py -q` -> `76 passed`

## Preflight

- `python -m rag.common.llm_check ollama:qwen2.5:7b` -> `OK    ollama:qwen2.5:7b  9.9s  tokens in/out 27/14  finish=stop`
- `python -m rag.common.llm_check` -> `FAIL  cannot reach the model server` (connection refused: the PuTTY tunnel is
  down). Recorded outcome; the plan continued per D-14.

## Scored run

Command: `python -m rag.experiments.conversation --repeats 3 --answers --name p4-qwen` (background, 3600 s ceiling,
exit 0, no retry needed; no `arm skipped: model unreachable: on` line).

Skip lines: `preflight failed: RuntimeError`; `arm skipped: model unreachable: answers (generator
vllm:/models/gpt-oss-20b: RuntimeError)`. The retrieval arms off, on, oracle and concat all ran.

```
arm          n   hit@5     mrr   rec@5
off         30   0.633   0.461   0.600
on          30   0.733   0.592   0.700
oracle      30   0.867   0.686   0.833
concat      30   0.833   0.569   0.817
paired on vs off: win 6 tie 21 loss 3 (n 30, gain 10.0, band 10.0, sign test p 0.2539)
  pronoun_follow_up            n  10  off 0.400  on 0.900  oracle 0.900  concat 0.900
  constraint_follow_up         n   6  off 0.667  on 0.667  oracle 1.000  concat 1.000
  topic_switch                 n   6  off 0.833  on 0.667  oracle 0.833  concat 0.500
  ambiguous_follow_up          n   4  asked 0 named both 0 second clarify 0
  standalone_in_conversation   n   8  off 0.750  on 0.625  oracle 0.750  concat 0.875
statuses: clarify 1, fallback 1, rewritten 26, skipped 6; fallback reasons: dropped_constraint 1
gate precision 0.679 recall 0.950; latency p50 2979.0 ms p95 3342.9 ms over 28
regression: 37/37 identical, rewriter calls 0 (off hit@5 0.865, mrr 0.663); after one unrelated turn (not gating): gate fired 21, rewritten 17, hit@5 changed 6 of 37
repeat 2: on hit@5 0.733, changed vs repeat 1: none
repeat 3: on hit@5 0.733, changed vs repeat 1: none
answers: unmeasured
(a) failed: gain 10.0 points, band 10.0 points (n = 30)
(b) passed: net 3 (wins 6, losses 3)
(c) failed: 1 standalone items lost
(d) passed: identical yes, rewriter calls 0
(e) passed: 1 fallbacks of 28 rewriter calls
(f) failed: some items are not approved
Decision: ships off (failed: a, c, f; provisional: items pending human review)
```

Task 1 verify printed `run recorded; every arm ran` (the report's `arms_not_run` lists retrieval arms only; the
answers skip is in `answers_not_run`) and the Decision line above.

## Rewriter comparison

Rewriter comparison: not run (tunnel down); qwen by default, not compared.

## Regression

`python -m rag.experiments.conversation --regression-only --name p4-regression`:

```
regression: 37/37 identical, rewriter calls 0
regression off hit@5 0.865 mrr 0.663
regression with one unrelated turn (not gating): gate fired 21, rewritten 17, hit@5 changed 6 of 37
```

## Results

- Rendered with `python -m rag.experiments.conversation --results runs/conversation/p4-qwen` into the scratchpad
  `results.md`, appended after one blank line; the doc's tail from `## Results` equals the rendered file byte for byte
  (CRLF kept, as the rest of the file).
- Decision line: `Decision: ships off (failed: a, c, f; provisional: items pending human review)`
- Rewriter chosen: `ollama:qwen2.5:7b (qwen by default, not compared)`; Question slot: `rewritten question
  (unmeasured: answers not run)`; Judge and rewriter are the same model: `not applicable (answers not run)`.
- Results commit: e114e36 `docs(04-08): record the chat memory evaluation results`. After it, `--check-rule` prints
  `clean yes; unchanged yes; first commit has results no` and the order check prints `rule-first`.
- Address/IP/URL/traceback grep on the doc: 0 matches.

## STATE.md blocker

Commit 3b9d2a3 adds: `[Phase 4]: arms not run on 2026-10-25: answers: generator_unreachable (vLLM tunnel down);
gpt-oss rewriter comparison: tunnel_down (qwen by default, not compared); rerun python -m rag.experiments.conversation
--repeats 3 --answers (and the gpt-oss comparison) when Ollama and the tunnel are up, then python -m
rag.experiments.conversation --results ...; the rewrite default stays off (D-14)`

## Deviations

- The first append used `printf '\n'`, which left one bare LF in a CRLF file; it was reverted and the separator
  written as CRLF with a short Python append so the file stays CRLF and the tail matches `results.md` byte for byte.

Full suite in the worktree: `.planning/runs/20261021-1840-chat-memory/wave-p4-04-08-1.txt`; run lines:
`.planning/runs/20261021-1840-chat-memory/wave-p4-04-08-run.txt`.
