## Shipping rule (committed before the first run)

This section is committed on its own, before any run of `python -m rag.experiments.conversation` over `data/golden/ddia_conversations.jsonl`, and is never edited afterwards. The experiment module `rag/experiments/conversation.py` repeats this text in its docstring, and it refuses to run the `on` arm unless this file is committed, clean, and this section is unchanged since the file's first commit.

Scored items. n is the number of items in `data/golden/ddia_conversations.jsonl` with `expect == "answer"`. Clarify items (`expect == "clarify"`) are scored apart and are not in n.

Per item. For item i, `off_i` and `on_i` are strict, evidence-aware hit@5 (0 or 1) of the `context` stage with the `semantic` chunks and the `weighted` config, on the teacher-forced history of the item (its fixed prior turns, never model-generated answers). `off` retrieves on the raw message; `on` retrieves on the question the Phase 3 rewriter returns. When the rewriter returns `clarify` for an answer-expected item, `on_i = 0` (a false clarify: the user got no answer). When the rewriter falls back, retrieval runs on the raw message and the fallback is a counted failure in (e), never "off".

Counts. wins = the number of items with `on_i = 1` and `off_i = 0`; losses = the number with `on_i = 0` and `off_i = 1`; net = wins - losses; gain = 100 * net / n points; band = max(8, 300 / n) points (three items' worth, never below the project's 8-point band).

Rewriting ships default-on only if all of these hold:

- (a) gain > band, strictly. At n = 30 the band is 10.0 points and net = 3 gives exactly 10.0, which does not exceed it.
- (b) net >= 3. (b) is implied by (a) for every n and is recorded for the reader.
- (c) no item in `standalone_in_conversation` has `on_i < off_i`.
- (d) in the regression arm, all 37 answerable questions of `data/golden/ddia_questions.jsonl`, each asked as the first turn of a conversation with rewriting on, make zero rewriter calls and return the same context chunk ids as `off`.
- (e) fallbacks <= 10% of rewriter calls, both counted over the items on which the gate called the rewriter (answer and clarify items, the first call per item, repeat 1). With no gate call at all, (e) fails.
- (f) every item in `data/golden/ddia_conversations.jsonl` has `review == "approved"`.

Otherwise rewriting ships off and the numbers are recorded below this section.

Reported, not gating: the one-sided exact sign test p on (wins, losses) (when (a) holds but p >= 0.05 the results say "clears the project band; weak evidence (sign test p = ...)"); the fraction of the oracle gap closed; the `concat` baseline; per-category tables; the paired counts of the pronoun and constraint items alone; answer-level results; instability across repeats. The rule is evaluated on repeat 1; later repeats are reported as instability only.

Decisions taken by the same numbers, written before any run:

- Rewriter model (D-10). With a second rewriter measured on the same items, choose the second only if its `on` hit@5 exceeds the first's by more than the band; keep the first if it exceeds the second's by more than the band; otherwise choose the rewriter with the lower p50 latency. The rule above is then evaluated on the chosen rewriter's run. Without a second run the results say "qwen by default, not compared".
- Question slot in the answer prompt (D-11). Keep the rewritten question unless the original-message slot's fact-checklist correct rate is higher by more than the band (computed as above from the number of judged items). Without answer scoring the slot stays the rewritten question and is recorded as unmeasured.
- Judge (D-12). Answers are scored only with the per-question fact checklist (`judge_facts`); an answer-level difference inside the band never changes a default, and the results say when the judge and the rewriter are the same model.

The results end with exactly one line that starts `Decision: ships on` or `Decision: ships off`.

## Results

Command: python -m rag.experiments.conversation --repeats 3 --answers --name p4-qwen

Date: 2026-10-25T17:12:14+00:00

Git commit: eb3f61a9009db473b8edf6668be489317e94c3f1

Rule commit: 9baf0f3334f3158aeafd77db5a07bdbbef9cd02c

Rewriter: ollama:qwen2.5:7b

Rewriter chosen: ollama:qwen2.5:7b (qwen by default, not compared)

Rewriter latency: p50 2979.0 ms, p95 3342.9 ms over 28 calls

Question slot: rewritten question (unmeasured: answers not run)

Judge and rewriter are the same model: not applicable (answers not run)

Regression arm: 37/37 identical, rewriter calls 0 (off hit@5 0.865, mrr 0.663); after one unrelated turn (not gating): gate fired 21, rewritten 17, hit@5 changed 6 of 37

Owner review: 34 of 34 items pending-human; the numbers are provisional until every item is approved and the run is repeated

### Arms (answer items, strict evidence-aware retrieval)

| arm | n | hit@5 | mrr | recall@5 |
|-----|---|-------|-----|----------|
| off | 30 | 0.633 | 0.461 | 0.600 |
| on | 30 | 0.733 | 0.592 | 0.700 |
| oracle | 30 | 0.867 | 0.686 | 0.833 |
| concat | 30 | 0.833 | 0.569 | 0.817 |

Oracle gap closed by on: 0.429. False clarifies on answer items: 1.

### Paired on vs off (hit@5)

| items | win | tie | loss | n |
|-------|-----|-----|------|---|
| all answer items | 6 | 21 | 3 | 30 |
| pronoun and constraint | 6 | 9 | 1 | 16 |

Net 3, gain 10.0 points, band 10.0 points, sign test p = 0.2539.

### Per category

| category | n | gate fired | off | on | oracle | concat | win/tie/loss |
|----------|---|------------|-----|----|--------|--------|--------------|
| pronoun_follow_up | 10 | 9 | 0.400 | 0.900 | 0.900 | 0.900 | 5/5/0 |
| constraint_follow_up | 6 | 6 | 0.667 | 0.667 | 1.000 | 1.000 | 1/4/1 |
| topic_switch | 6 | 3 | 0.833 | 0.667 | 0.833 | 0.500 | 0/5/1 |
| ambiguous_follow_up | 4 | 4 | clarify: asked 0, named both 0, second clarify 0 | | | | |
| standalone_in_conversation | 8 | 6 | 0.750 | 0.625 | 0.750 | 0.875 | 0/7/1 |

### Rewrite statuses and gate

Statuses: clarify 1, fallback 1, rewritten 26, skipped 6.
Fallback reasons: dropped_constraint 1.
Gate: precision 0.679, recall 0.950, fired 28, misses none. Rewriter calls counted for (e): 28, fallbacks 1.
must_contain kept rate 0.500; must_not_contain leak rate 0.333.
Clarify items: 4, asked 0, named both 0, second clarification 0.

### Instability across repeats (reported, not gating)

- repeat 1: on hit@5 0.733, changed vs repeat 1: none
- repeat 2: on hit@5 0.733, changed vs repeat 1: none
- repeat 3: on hit@5 0.733, changed vs repeat 1: none

### Answers (fact checklist, last turn)

unmeasured (generator: vllm:/models/gpt-oss-20b unreachable (RuntimeError))

### Shipping rule conditions

- (a) gain > band, strictly: failed; gain 10.0 points, band 10.0 points (n = 30)
- (b) net >= 3: passed; net 3 (wins 6, losses 3)
- (c) no standalone_in_conversation loss: failed; 1 standalone items lost
- (d) regression arm identical with zero rewriter calls: passed; identical yes, rewriter calls 0
- (e) fallbacks <= 10% of rewriter calls: passed; 1 fallbacks of 28 rewriter calls
- (f) every item approved: failed; some items are not approved

Decision: ships off (failed: a, c, f; provisional: items pending human review)


## Results, 2026-10-26 (runs p6-qwen and p6-gptoss)

Command: python -m rag.experiments.conversation --repeats 3 --answers --name p6-qwen; compare: python -m rag.experiments.conversation --rewriter vllm:/models/gpt-oss-20b --arms off,on --name p6-gptoss

Date: 2026-10-26T11:43:25+00:00

Git commit: 71fa0d971a1331adddbbe1bd889a8bacecb042cc

Rule commit: bfcba2c8e510dd37ea361d2c747d8b67ba63a919

Rewriter: ollama:qwen2.5:7b; compare: vllm:/models/gpt-oss-20b

Rewriter chosen: vllm:/models/gpt-oss-20b (inside the band; lower p50 latency)

Rewriter latency: p50 1955.7 ms, p95 2989.2 ms over 28 calls

Question slot: rewritten question (on rate 0.621, on_original rate 0.643)

Judge and rewriter are the same model: yes (ollama:qwen2.5:7b)

Regression arm: 37/37 identical, rewriter calls 0 (off hit@5 0.865, mrr 0.663); after one unrelated turn (not gating): gate fired 21, rewritten 17, hit@5 changed 6 of 37

Owner review: 34 of 34 items pending-human; the numbers are provisional until every item is approved and the run is repeated

Notes added when recording this run (not produced by the tool): the run folders are `runs/conversation/p6-qwen` (qwen rewriter, `--repeats 3 --answers`) and `runs/conversation/p6-gptoss` (gpt-oss rewriter, arms off and on, `REMOTE_REASONING_EFFORT=low`); both are git-ignored. `max_model_len` was read as 131072 on this date (`docs/models.md`). The "Regression arm" line above is the qwen run's; in the gpt-oss run the same unrelated-turn check (not gating) had the gate fire on 21, rewrote 0 and changed hit@5 on 0 of 37 (gpt-oss answered `standalone` for those), so the over-rewriting seen with qwen (17 rewritten, 6 changed) was not seen with gpt-oss; the over-rewriting fix is still out of scope here. The answers table was produced with the qwen rewriter's retrieval (the gpt-oss run did not run answers), the judge is qwen2.5:7b, and the answer differences (on 0.621 against off 0.500, 18 of 29 against 13 of 26) are about 12 points on 26 to 29 judged items, judged by qwen, which is also the rewriter in that run; the rule says an answer-level difference never changes a default, so they are reported only. The first Results section above (run p4-qwen, 2026-10-25) is kept unchanged; its "answers unmeasured" line is superseded by the table here. The 34 rows are still `pending-human`, so condition (f) fails and rewriting still ships off.

### Rewriter comparison

| rewriter | on hit@5 | p50 ms | p95 ms | fallbacks | reasoning effort |
|----------|----------|--------|--------|-----------|------------------|
| ollama:qwen2.5:7b | 0.733 | 2968.9 | 3346.8 | 1 | unset |
| vllm:/models/gpt-oss-20b | 0.833 | 1955.7 | 2989.2 | 0 | low |

### Arms (answer items, strict evidence-aware retrieval)

| arm | n | hit@5 | mrr | recall@5 |
|-----|---|-------|-----|----------|
| off | 30 | 0.633 | 0.461 | 0.600 |
| on | 30 | 0.833 | 0.647 | 0.800 |

Oracle gap closed by on: n/a. False clarifies on answer items: 0.

### Paired on vs off (hit@5)

| items | win | tie | loss | n |
|-------|-----|-----|------|---|
| all answer items | 7 | 22 | 1 | 30 |
| pronoun and constraint | 7 | 9 | 0 | 16 |

Net 6, gain 20.0 points, band 10.0 points, sign test p = 0.0352.

### Per category

| category | n | gate fired | off | on | oracle | concat | win/tie/loss |
|----------|---|------------|-----|----|--------|--------|--------------|
| pronoun_follow_up | 10 | 9 | 0.400 | 0.900 | n/a | n/a | 5/5/0 |
| constraint_follow_up | 6 | 6 | 0.667 | 1.000 | n/a | n/a | 2/4/0 |
| topic_switch | 6 | 3 | 0.833 | 0.833 | n/a | n/a | 0/6/0 |
| ambiguous_follow_up | 4 | 4 | clarify: asked 1, named both 1, second clarify 0 | | | | |
| standalone_in_conversation | 8 | 6 | 0.750 | 0.625 | n/a | n/a | 0/7/1 |

### Rewrite statuses and gate

Statuses: clarify 1, rewritten 18, skipped 6, standalone 9.
Fallback reasons: none.
Gate: precision 0.679, recall 0.950, fired 28, misses none. Rewriter calls counted for (e): 28, fallbacks 0.
must_contain kept rate 0.889; must_not_contain leak rate 0.000.
Clarify items: 4, asked 1, named both 1, second clarification 0.

### Instability across repeats (reported, not gating)

- repeat 1: on hit@5 0.733, changed vs repeat 1: none
- repeat 2: on hit@5 0.733, changed vs repeat 1: none
- repeat 3: on hit@5 0.733, changed vs repeat 1: none

### Answers (fact checklist, last turn)

| variant | correct | judged | rate |
|---------|---------|--------|------|
| off | 13 | 26 | 0.500 |
| on | 18 | 29 | 0.621 |
| on_original | 18 | 28 | 0.643 |
| oracle | 18 | 27 | 0.667 |

### Shipping rule conditions

- (a) gain > band, strictly: passed; gain 20.0 points, band 10.0 points (n = 30)
- (b) net >= 3: passed; net 6 (wins 7, losses 1)
- (c) no standalone_in_conversation loss: failed; 1 standalone items lost
- (d) regression arm identical with zero rewriter calls: passed; identical yes, rewriter calls 0
- (e) fallbacks <= 10% of rewriter calls: passed; 0 fallbacks of 28 rewriter calls
- (f) every item approved: failed; some items are not approved

Decision: ships off (failed: c, f; provisional: items pending human review)
