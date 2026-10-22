# Phase 4: Multi-turn evaluation and the default decision - Context

**Gathered:** 2026-10-22
**Status:** Ready for planning
**Mode:** `--auto` (every gray area took the recommended option; each pick is recorded as an assumption below)

<domain>
## Phase Boundary

Measure rewriting off, on and against an oracle on a multi-turn golden set, and let the numbers set the rewrite default. Delivers: a committed multi-turn golden set under `data/golden/` with its own loader (`load_golden` unchanged); one experiment command under `rag/experiments/` that prints the arms with teacher-forced histories, paired win/tie/loss and per-category tables, plus a regression arm over the 37 answerable single-turn questions; a shipping rule committed before the first scored run; a committed results file; the `RAG_REWRITE` default set by the rule; the rewriter model and the answer-prompt question slot decided from recorded numbers.

Requirements: EVAL-01, EVAL-02, EVAL-03. Not in this phase: the page and the docs relabel (Phase 5); compaction; any change to the single-turn golden set, its loader, the chunkers or the retrieval configs.

</domain>

<decisions>
## Implementation Decisions

### Carried forward (locked earlier)
- Rewrite, clarify and topic switch sit behind one switch `RAG_REWRITE` (default off) with `RAG_REWRITER` default `ollama:qwen2.5:7b`; fallback is fail-open with `rewrite.status="fallback"` (Phase 3 D-01, D-02, D-09). Experiments count a fallback as a rewrite failure, never as "off".
- Draft rows exist in `data/golden/conversations_draft.jsonl`, marked `"review": "pending-human"` (Phase 3 D-15 and orchestrator resolution).
- Gaps under about 8 points are noise on 37 questions; use the per-question fact checklist and strict evidence-aware relevance; never the holistic correctness judge or page-overlap-only relevance (CLAUDE.md).

### Golden set (EVAL-01)
- **D-01:** File `data/golden/ddia_conversations.jsonl`, one conversation per line: `id`, `category` (`pronoun_follow_up`, `topic_switch`, `ambiguous_follow_up`, `standalone_in_conversation`, plus `constraint_follow_up`), `turns` (fixed prior turns: `question`, `answer` short text), `message` (the scored last turn), `standalone` (the human-written standalone question), `gold_pages` (PDF pages, list of `[start, end]`), `expect` (`answer` or `clarify`), `key_facts`, `must_contain` / `must_not_contain` (for topic leak), `review`. Pages are PDF page numbers (DDIA printed page + 22). — **Reversibility:** costly — later experiments and docs read this schema. [auto: recommended]
- **D-02:** Size target: at least 30 scored follow-up turns, with every category at least 4 items and at least half the pronoun/constraint follow-ups being items where the raw message misses the gold page at hit@5 (measured with rewrite off before the set is frozen), so the set can discriminate. If fewer than 30 can be authored, the run still happens and the rule (D-07) uses the actual n. [auto: recommended — PITFALLS.md Pitfall 11; SUMMARY.md "about 30 follow-up turns"]
- **D-03:** Authorship: the run is unattended, so the executor drafts items from the Phase 3 draft rows and the existing single-turn golden questions (reusing their verified `gold_pages` and `key_facts` where a follow-up's standalone form matches one), marks each row `"review": "pending-human"`, and records that the owner must review them. The shipping rule (D-07) makes rewriting default-on only if every scored item is `"review": "approved"`; with any `pending-human` rows the default stays off and the numbers are recorded as provisional. [auto: recommended — keeps the human-written requirement honest in an unattended run]
- **D-04:** Loader: `rag/observe/golden_conversations.py` with `load_conversations(path) -> List[GoldConversation]`, a frozen dataclass per item and `validate()` that rejects unknown keys, bad page ranges, unknown categories and duplicate ids. `rag/observe/golden.py` / `load_golden` are not edited. [locked by EVAL-01]

### Experiment (EVAL-02)
- **D-05:** Command `python -m rag.experiments.conversation` (module `rag/experiments/conversation.py`, `__main__` guard). Arms: `off` (retrieve on the raw message), `on` (Phase 3 `rewrite_question` with the configured rewriter, then retrieve on the effective question), `oracle` (retrieve on the human `standalone`), and `concat` (raw message prefixed with the previous user question — the cheap baseline). Every arm sees the same teacher-forced history from the item's `turns` (not model-generated earlier answers). Retrieval uses the same chunker and config as the invariant (`semantic`, `weighted`) through `RetrievalPipeline` on the book chunks; no service, no conversation store. [auto: recommended — PITFALLS.md Pitfall 10]
- **D-06:** Outputs: per arm hit@5, mrr, recall@5 on the scored turns; "fraction of the oracle gap closed" for `on`; paired per-item win/tie/loss `on` vs `off` on hit@5; per-category table; rewrite status counts (`skipped`, `standalone`, `rewritten`, `clarify`, `new_topic`, `fallback` with reasons); gate precision/recall against the item's need for a rewrite; rewriter latency p50/p95 (`rewrite_ms`); answer scoring on the last turn with the per-question fact checklist (`judge_facts`) for `off`, `on` and `oracle` when `--answers` is passed (needs the generator; skipped with a printed note when the tunnel is down); clarify items scored separately (did it clarify when `expect == "clarify"`, never two in a row). Results are written to `runs/conversation/<timestamp>/report.json` (gitignored) and summarised into the committed results file (D-08). [auto: recommended]
- **D-07 (shipping rule, committed before the first scored run):** with n scored follow-up turns that expect an answer, the noise band is `max(8, 300 / n)` points of hit@5 (three items' worth, never below the project's 8-point band). Rewriting ships default-on only if ALL hold: (a) `on` minus `off` hit@5 on those turns exceeds the band; (b) net paired wins (wins − losses) ≥ 3; (c) no loss on the `standalone_in_conversation` category; (d) the regression arm (D-09) is identical to `off`; (e) fallback rate ≤ 10% of rewriter calls; (f) every scored item has `"review": "approved"`. Otherwise it ships off with the numbers recorded. The rule lives in the committed results file's first section and in the experiment module docstring, committed in its own commit before any scored run. — **Reversibility:** one-way for this milestone — a rule written after seeing the numbers is not a rule. [auto: recommended — EVAL-03, PITFALLS.md Pitfall 10]
- **D-08:** Committed results: `docs/chat_memory_eval.md` (shipping rule, command, date, git commit, rewriter spec, n per category, the arm table, paired counts, per-category table, regression result, latency, gate numbers, decision and reason). The raw report stays in gitignored `runs/`. [auto: recommended]
- **D-09:** Regression arm: replay each of the 37 answerable single-turn golden questions as the first turn of a conversation with `on`; the gate must skip (no rewriter call) and retrieval must equal `off` exactly (same hit lists). The single-turn invariant command must still print hit@5 0.865 / mrr 0.663. [locked by ROADMAP SC5]

### Decisions taken by measurement
- **D-10:** Rewriter model: arms run with `RAG_REWRITER=ollama:qwen2.5:7b` (default) and, when the tunnel is up, the generator `vllm:/models/gpt-oss-20b` at low reasoning effort (`REMOTE_REASONING_EFFORT=low`) as a comparison. Choose the model with the higher `on` hit@5; within the noise band choose the lower p50 latency; record both. If the tunnel is down, only qwen runs and the choice is recorded as "qwen by default, not compared". [auto: recommended]
- **D-11:** Question slot in the answer prompt: with `--answers`, score `on` twice — answer prompt question = rewritten question vs = original message (history block present in both). Keep the rewritten question (Phase 3 D-11) unless the original-message slot scores higher by more than the band; record both. Without `--answers` (tunnel down), the slot stays rewritten and the decision is recorded as unmeasured. [auto: recommended]
- **D-12:** Judge: the primary scoring metric for the shipping rule is retrieval (hit@5 on gold pages; no judge). Answer scoring uses `judge_facts` with `RAG_JUDGE` (`ollama:qwen2.5:7b`); because the rewriter and the judge can be the same model, the results file flags it, and a borderline answer result (within the band) is not used to flip anything. [auto: recommended — rewriter/judge correlation, STATE.md Phase 4 concern]

### Applying the decision
- **D-13:** The rule's outcome sets the default: if on, `build_default_service` treats an unset `RAG_REWRITE` as on and `.env.example` documents it; if off, nothing changes in code and the results file says "ships off". The default change, if any, is its own small commit after the results commit. [auto: recommended]
- **D-14:** Live model runs need the tunnel (generator) and local Ollama (rewriter). If either is unavailable when the plan runs, the plan records which arms could not run, writes a STATE.md blocker, keeps the default off, and still commits the rule, the golden set, the loader and the experiment with tests that run offline (`FakeLLM`, `HashingEmbedder`, tiny fixtures). [auto: recommended]

### Claude's Discretion
- Exact report table layout; helper names inside the experiment module; how the `concat` baseline joins text.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scope
- `.planning/REQUIREMENTS.md` — EVAL-01..03
- `.planning/ROADMAP.md` §"Phase 4" — success criteria 1-5, scope note, open decisions (question slot, rewriter model)

### Earlier phases
- `.planning/phases/03-rewrite-clarify-and-topic-switch/03-CONTEXT.md`, `03-01-PLAN.md` (`rewrite_question`, `needs_rewrite`, `RewriteResult`), `03-03-PLAN.md` (draft golden rows), `03-04-PLAN.md` (`RAG_REWRITE`, `RAG_REWRITER` in `build_default_service`)
- `.planning/phases/01-safety-net-and-prompt-seam/01-05-PLAN.md` — `HistoryTurn`, `render_block`

### Research
- `.planning/research/PITFALLS.md` — Pitfalls 10, 11 (evaluation power, golden-set design), 7 (experiment cache keys)
- `.planning/research/SUMMARY.md` §"Phase 4" and "Gaps to Address"
- `.planning/research/ARCHITECTURE.md` — `rag/experiments/conversation.py`, `data/golden/ddia_conversations.jsonl`

### Code
- `rag/experiments/retrieval.py` (argparse, table printing, `RetrievalPipeline` over book chunks), `rag/experiments/answer.py` (answer scoring loop)
- `rag/observe/golden.py` (`GoldQuestion`, `load_golden`, `validate`), `rag/observe/retrieval_quality/metrics.py`, `rag/observe/generation_quality/answers.py` (`score_answer`), `judge.py` (`judge_facts`)
- `data/golden/ddia_questions.jsonl`, `data/golden/BATCHES.md`, `data/golden/question_writer_rules.md`
- `docs/models.md`, `.env.example`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `rag/experiments/retrieval.py` — argparse flags (`--chunkers`, `--configs`, `--chunks-dir`, `--golden`, `--prefix`), embedding index reuse, `print_table`
- `rag/observe/retrieval_quality/metrics.py` — hit@k, mrr, recall@k on gold pages
- `rag/observe/generation_quality/judge.py` `judge_facts` — fact checklist judge
- `rag/observe/golden.py` — the dataclass + `validate()` pattern to copy for the new loader
- `FakeLLM`, `HashingEmbedder` — offline tests of the experiment

### Established Patterns
- Experiments are `python -m` modules that print a table and write a JSON report under gitignored `runs/`
- Golden files are JSONL with PDF pages; `load_golden` rejects unknown keys via the dataclass constructor

### Integration Points
- The experiment imports `rewrite_question`/`needs_rewrite` from `rag/query/rewrite.py` and `HistoryTurn`/`render_block`/`neutralize` from `rag/query/history.py`; it never imports `rag/api/`
- `build_default_service` in `rag/api/main.py` is the only place the default flips (D-13)

</code_context>

<specifics>
## Specific Ideas

- The results file's first heading is "Shipping rule (committed before the first run)" and its commit precedes the commit that adds numbers; the verifier checks the order with `git log`.
- An offline smoke test runs the experiment on a 3-item fixture with fake models and asserts the report has all four arms and the paired counts.

</specifics>

<deferred>
## Deferred Ideas

- A stronger, independent judge (hosted) for answer scoring — later, when quota allows
- Ollama JSON-schema `format` for the rewriter — only if the parse-failure rate measured here is high
- Growing the multi-turn set past ~30 turns for power — later

</deferred>

---

*Phase: 04-multi-turn-evaluation-and-the-default-decision*
*Context gathered: 2026-10-22 (auto mode)*
