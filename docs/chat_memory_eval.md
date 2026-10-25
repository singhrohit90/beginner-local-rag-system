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
