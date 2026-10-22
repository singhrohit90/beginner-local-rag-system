# Phase 4: Multi-turn evaluation and the default decision - Research

**Researched:** 2026-10-22
**Domain:** Offline-testable multi-turn retrieval/answer evaluation in a brownfield plain-Python RAG repo; small-n paired statistics; a pre-registered shipping rule
**Confidence:** HIGH for repo reuse and statistics (read and computed this session); MEDIUM for Phase 1-3 symbols (planned, not executed); LOW for live-model behaviour (not run, by instruction)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Carried forward (locked earlier)
- Rewrite, clarify and topic switch sit behind one switch `RAG_REWRITE` (default off) with `RAG_REWRITER` default `ollama:qwen2.5:7b`; fallback is fail-open with `rewrite.status="fallback"` (Phase 3 D-01, D-02, D-09). Experiments count a fallback as a rewrite failure, never as "off".
- Draft rows exist in `data/golden/conversations_draft.jsonl`, marked `"review": "pending-human"` (Phase 3 D-15 and orchestrator resolution).
- Gaps under about 8 points are noise on 37 questions; use the per-question fact checklist and strict evidence-aware relevance; never the holistic correctness judge or page-overlap-only relevance (CLAUDE.md).

#### Golden set (EVAL-01)
- **D-01:** File `data/golden/ddia_conversations.jsonl`, one conversation per line: `id`, `category` (`pronoun_follow_up`, `topic_switch`, `ambiguous_follow_up`, `standalone_in_conversation`, plus `constraint_follow_up`), `turns` (fixed prior turns: `question`, `answer` short text), `message` (the scored last turn), `standalone` (the human-written standalone question), `gold_pages` (PDF pages, list of `[start, end]`), `expect` (`answer` or `clarify`), `key_facts`, `must_contain` / `must_not_contain` (for topic leak), `review`. Pages are PDF page numbers (DDIA printed page + 22). - **Reversibility:** costly - later experiments and docs read this schema. [auto: recommended]
- **D-02:** Size target: at least 30 scored follow-up turns, with every category at least 4 items and at least half the pronoun/constraint follow-ups being items where the raw message misses the gold page at hit@5 (measured with rewrite off before the set is frozen), so the set can discriminate. If fewer than 30 can be authored, the run still happens and the rule (D-07) uses the actual n. [auto: recommended - PITFALLS.md Pitfall 11; SUMMARY.md "about 30 follow-up turns"]
- **D-03:** Authorship: the run is unattended, so the executor drafts items from the Phase 3 draft rows and the existing single-turn golden questions (reusing their verified `gold_pages` and `key_facts` where a follow-up's standalone form matches one), marks each row `"review": "pending-human"`, and records that the owner must review them. The shipping rule (D-07) makes rewriting default-on only if every scored item is `"review": "approved"`; with any `pending-human` rows the default stays off and the numbers are recorded as provisional. [auto: recommended - keeps the human-written requirement honest in an unattended run]
- **D-04:** Loader: `rag/observe/golden_conversations.py` with `load_conversations(path) -> List[GoldConversation]`, a frozen dataclass per item and `validate()` that rejects unknown keys, bad page ranges, unknown categories and duplicate ids. `rag/observe/golden.py` / `load_golden` are not edited. [locked by EVAL-01]

#### Experiment (EVAL-02)
- **D-05:** Command `python -m rag.experiments.conversation` (module `rag/experiments/conversation.py`, `__main__` guard). Arms: `off` (retrieve on the raw message), `on` (Phase 3 `rewrite_question` with the configured rewriter, then retrieve on the effective question), `oracle` (retrieve on the human `standalone`), and `concat` (raw message prefixed with the previous user question - the cheap baseline). Every arm sees the same teacher-forced history from the item's `turns` (not model-generated earlier answers). Retrieval uses the same chunker and config as the invariant (`semantic`, `weighted`) through `RetrievalPipeline` on the book chunks; no service, no conversation store. [auto: recommended - PITFALLS.md Pitfall 10]
- **D-06:** Outputs: per arm hit@5, mrr, recall@5 on the scored turns; "fraction of the oracle gap closed" for `on`; paired per-item win/tie/loss `on` vs `off` on hit@5; per-category table; rewrite status counts (`skipped`, `standalone`, `rewritten`, `clarify`, `new_topic`, `fallback` with reasons); gate precision/recall against the item's need for a rewrite; rewriter latency p50/p95 (`rewrite_ms`); answer scoring on the last turn with the per-question fact checklist (`judge_facts`) for `off`, `on` and `oracle` when `--answers` is passed (needs the generator; skipped with a printed note when the tunnel is down); clarify items scored separately (did it clarify when `expect == "clarify"`, never two in a row). Results are written to `runs/conversation/<timestamp>/report.json` (gitignored) and summarised into the committed results file (D-08). [auto: recommended]
- **D-07 (shipping rule, committed before the first scored run):** with n scored follow-up turns that expect an answer, the noise band is `max(8, 300 / n)` points of hit@5 (three items' worth, never below the project's 8-point band). Rewriting ships default-on only if ALL hold: (a) `on` minus `off` hit@5 on those turns exceeds the band; (b) net paired wins (wins - losses) >= 3; (c) no loss on the `standalone_in_conversation` category; (d) the regression arm (D-09) is identical to `off`; (e) fallback rate <= 10% of rewriter calls; (f) every scored item has `"review": "approved"`. Otherwise it ships off with the numbers recorded. The rule lives in the committed results file's first section and in the experiment module docstring, committed in its own commit before any scored run. - **Reversibility:** one-way for this milestone - a rule written after seeing the numbers is not a rule. [auto: recommended - EVAL-03, PITFALLS.md Pitfall 10]
- **D-08:** Committed results: `docs/chat_memory_eval.md` (shipping rule, command, date, git commit, rewriter spec, n per category, the arm table, paired counts, per-category table, regression result, latency, gate numbers, decision and reason). The raw report stays in gitignored `runs/`. [auto: recommended]
- **D-09:** Regression arm: replay each of the 37 answerable single-turn golden questions as the first turn of a conversation with `on`; the gate must skip (no rewriter call) and retrieval must equal `off` exactly (same hit lists). The single-turn invariant command must still print hit@5 0.865 / mrr 0.663. [locked by ROADMAP SC5]

#### Decisions taken by measurement
- **D-10:** Rewriter model: arms run with `RAG_REWRITER=ollama:qwen2.5:7b` (default) and, when the tunnel is up, the generator `vllm:/models/gpt-oss-20b` at low reasoning effort (`REMOTE_REASONING_EFFORT=low`) as a comparison. Choose the model with the higher `on` hit@5; within the noise band choose the lower p50 latency; record both. If the tunnel is down, only qwen runs and the choice is recorded as "qwen by default, not compared". [auto: recommended]
- **D-11:** Question slot in the answer prompt: with `--answers`, score `on` twice - answer prompt question = rewritten question vs = original message (history block present in both). Keep the rewritten question (Phase 3 D-11) unless the original-message slot scores higher by more than the band; record both. Without `--answers` (tunnel down), the slot stays rewritten and the decision is recorded as unmeasured. [auto: recommended]
- **D-12:** Judge: the primary scoring metric for the shipping rule is retrieval (hit@5 on gold pages; no judge). Answer scoring uses `judge_facts` with `RAG_JUDGE` (`ollama:qwen2.5:7b`); because the rewriter and the judge can be the same model, the results file flags it, and a borderline answer result (within the band) is not used to flip anything. [auto: recommended - rewriter/judge correlation, STATE.md Phase 4 concern]

#### Applying the decision
- **D-13:** The rule's outcome sets the default: if on, `build_default_service` treats an unset `RAG_REWRITE` as on and `.env.example` documents it; if off, nothing changes in code and the results file says "ships off". The default change, if any, is its own small commit after the results commit. [auto: recommended]
- **D-14:** Live model runs need the tunnel (generator) and local Ollama (rewriter). If either is unavailable when the plan runs, the plan records which arms could not run, writes a STATE.md blocker, keeps the default off, and still commits the rule, the golden set, the loader and the experiment with tests that run offline (`FakeLLM`, `HashingEmbedder`, tiny fixtures). [auto: recommended]

### Claude's Discretion
- Exact report table layout; helper names inside the experiment module; how the `concat` baseline joins text.

### Deferred Ideas (OUT OF SCOPE)
- A stronger, independent judge (hosted) for answer scoring - later, when quota allows
- Ollama JSON-schema `format` for the rewriter - only if the parse-failure rate measured here is high
- Growing the multi-turn set past ~30 turns for power - later
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EVAL-01 | Multi-turn golden set under `data/golden/` (pronoun, topic switch, ambiguous, standalone-in-conversation) with human-written standalone question and PDF gold pages, own loader, `load_golden` unchanged | Loader pattern copied from `rag/observe/golden.py`; reusable `verify()` for page/evidence checks; schema gaps in D-01 vs the Phase 3 draft rows (see "Schema reconciliation"); authoring seeds table |
| EVAL-02 | Experiment scoring retrieval on the rewritten query and the answer on the last turn, on/off/oracle, identical teacher-forced histories, fact-checklist judge | Reuse map for `RetrievalPipeline`, `get_index`, `strict_trace`, `score_hits`, `judge_facts`; pure-core/`main()` split for offline tests; arm definitions; preflight for optional live arms |
| EVAL-03 | Ships on only if the gain clears the noise band recomputed for n; otherwise off with numbers recorded; rule written before the first run | Exact arithmetic of `max(8, 300/n)`, redundancy of condition (b), exact sign test table, power table, rule text draft, commit-order enforcement |
</phase_requirements>

## Summary

Phase 4 is almost entirely reuse. Everything the experiment needs already exists in the repo: `RetrievalPipeline.from_chunkset` over the cached semantic chunks and mpnet index, `strict_trace` + `score_hits` for evidence-aware hit@5/mrr/recall@5, `judge_facts` for the fact checklist, and `verify_golden.verify` for checking gold pages and evidence terms. The new code is a loader (`rag/observe/golden_conversations.py`), one experiment module (`rag/experiments/conversation.py`) split into a pure, offline-testable core and a thin `main()`, a committed golden file, `docs/chat_memory_eval.md`, and (conditionally) a one-line default flip. Nothing in the existing retrieval path is touched, so hit@5 0.865 / mrr 0.663 cannot move from this phase's code. No package is installed (stdlib `math.comb` is enough for the exact test).

The statistics are the part that needs care. With binary per-item hit@5 the gain equals net paired wins divided by n, so D-07 condition (a) is "net wins > max(0.08 n, 3)". That means (a) always implies (b) (net >= 3): (b) is redundant but harmless. At n = 30 the band is 10 points and an item is 3.33 points, so the rule needs net >= 4. An exact one-sided sign test on discordant pairs is STRICTER than the band rule: 4 wins and 0 losses passes the band but has p = 0.0625, and 8 wins / 4 losses (net 4) has p = 0.19. A simulation shows n = 30 reliably detects only large effects (power of the D-07 rule: 0.51 at a true +12 points, 0.74 at +17, 0.95 at +27). The rule text should therefore define n precisely (answer-expected items only), define how a false clarify and a fallback count, and report the sign-test p-value beside the band verdict without making it gating (D-07 is locked).

The likely outcome, and an acceptable one under the project's own rule, is "ships off with the numbers recorded": condition (f) (every scored item `approved`) cannot be met in an unattended run because the executor can only author `pending-human` rows (D-03). The plan should still evaluate (a)-(e) separately and print them so the owner can see what would happen after review. The one process trap is ordering: the rule must be committed (docs file with only the rule section, and the module docstring) before any `on` arm run; the experiment should refuse to run the `on` arm unless that file is committed and clean.

**Primary recommendation:** Build `golden_conversations.py` and a pure `conversation.py` core first (loader, arms, paired counts, sign test, `evaluate_rule`) with offline `HashingEmbedder` + `FakeLLM` tests; commit the rule text before any scored run; author the golden set with a `--check-set` mode (off and oracle arms only, no rewriter) that proves at least half the pronoun/constraint items are baseline misses; then do the live run and let `evaluate_rule` set the default.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Golden conversation file and loader | `rag/observe/` (evaluation layer) | `data/golden/` (committed data) | Evaluation code never runs on the request path; `golden.py` is the pattern |
| Retrieval scoring per arm | `rag/observe/retrieval_quality/metrics.py` (reused) | `rag/experiments/conversation.py` | Metrics are pure functions on hits and gold pages |
| Rewrite step inside the experiment | `rag/query/rewrite.py` (Phase 3, imported) | `rag/experiments/conversation.py` (orchestrates) | The experiment must call the same `needs_rewrite` + `rewrite_question` the service calls, never a copy |
| Teacher-forced history building | `rag/experiments/conversation.py` | `rag/query/history.py` (`HistoryTurn`, `window`, `render_block`) | No conversation store, no `rag/api` import (CONTEXT integration points) |
| Answer scoring (optional) | `rag/observe/generation_quality/judge.py` (`judge_facts`) | `rag/query/pipeline.py` (`RagPipeline.answer`) | Fact checklist is the project's accepted judge |
| Shipping-rule evaluation | `rag/experiments/conversation.py` (pure `evaluate_rule`) | `docs/chat_memory_eval.md` (human-readable rule + result) | Rule as code is testable; rule as prose is the committed pre-registration |
| Default switch | `rag/api/main.py` `build_default_service` | `.env.example` | Only place the default flips (D-13); conditional commit |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| (stdlib only) `math.comb`, `statistics`, `argparse`, `json`, `dataclasses`, `subprocess`, `datetime` | Python 3.10.11 [VERIFIED: `python --version` this session] | Sign test, percentiles, CLI, report, git sha | No new dependency (REQUIREMENTS Out of Scope: no new framework); `scipy` happens to import here but must not be relied on (not in `requirements-rag.txt`) |
| In-repo modules (reused) | n/a | See "Reuse map" below | Brownfield rule: reuse, do not reimplement |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` (already `>=8`) | existing | Offline tests | All new tests |
| `HashingEmbedder`, `FakeLLM` | in repo | Offline fixtures | Smoke test of the experiment |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Own 5-line scoring loop (`strict_trace` + `score_hits`) | `run_eval(...)` | `run_eval` returns only an aggregate and writes per-question rows to disk; the experiment needs per-item scores in memory for pairing. Use the loop; optionally save traces with `Trace.save`. |
| `scipy.stats.binomtest` | `math.comb` exact sum | scipy is not a declared dependency; the exact sum is 3 lines |

**Installation:** none. `requirements-rag.txt` is unchanged.

**Version verification:** no external package is recommended, so no registry check applies. [VERIFIED: nothing to install]

### Reuse map (all read this session)

| Need | Reuse | Verbatim signature or line |
|------|-------|-----------------------------|
| Build pipeline over book chunks | `load_chunkset`, `get_index`, `RetrievalPipeline.from_chunkset` | `def load_chunkset(directory: Path, strategy: str) -> ChunkSet:` (`rag/ingestion/chunking/base.py:46`); `def get_index(chunkset: ChunkSet, embedder: Embedder, variant: str = "plain", rebuild: bool = False, root: Path = PROCESSED_DIR) -> VectorIndex:` (`rag/ingestion/index.py:16-19`); `pipeline = RetrievalPipeline.from_chunkset(chunkset, index, embedder, reranker, stem=args.bm25_stem)` (`rag/experiments/retrieval.py:118`) |
| Run retrieval on a string | `RetrievalPipeline.run` | `def run(self, query_id: str, question: str, config: RetrievalConfig) -> Trace:` (`rag/query/pipeline.py:62`) |
| Same config as the invariant | `CONFIGS["weighted"]` | `"weighted": RetrievalConfig("weighted", fusion="weighted"),` (`rag/query/configs.py:34`) |
| Evidence-aware relevance | `strict_trace`, `score_hits` | `def strict_trace(trace: Trace, terms: Sequence[str]) -> Trace:` (`metrics.py:43`); `def score_hits(hits: Sequence[Hit], gold_pages: Sequence[PageRange], ks: Sequence[int]) -> Dict[str, float]:` (`metrics.py:109-111`); `return 1.0 if any(is_relevant(h, gold_pages) for h in hits[:k]) else 0.0` (`metrics.py:77`) - so hit@5 is exactly 0 or 1 per item |
| Same ks and strictness as the invariant | constants | `KS = (1, 3, 5, 10, 30)` (`retrieval.py:39`); `strict=not args.page_level` (`retrieval.py:129`) - the invariant is strict by default |
| Fact checklist judge | `judge_facts`, `FactVerdict` | `def judge_facts(judge: LLM, answer: str, facts: List[str]) -> FactVerdict:` (`judge.py:84`); `correct` returns `None` if any fact unparsed, else `all(self.stated)` (`judge.py:77-81`) |
| Abstention counts as wrong | `looks_like_abstention` | `from rag.query.generate import citation_is_valid, looks_like_abstention` (`answers.py:22`); `correct, faithful, reasons = False, True, ("abstained", "")` (`answers.py:84`) |
| Page/evidence verification of the new set | `verify` + `load_pages` | `def verify(questions: Sequence[GoldQuestion], texts: Dict[int, str]) -> List[str]:` (`verify_golden.py:28`); `from rag.ingestion.extract import load_pages` (`verify_golden.py:17`); `texts = {p.page_no: p.text for p in load_pages(args.pages_file)}` (`verify_golden.py:67`) |
| Paths | `GOLDEN_DIR`, `RUNS_DIR`, `PROCESSED_DIR` | `GOLDEN_DIR = DATA_DIR / "golden"`, `RUNS_DIR = ROOT / "runs"` (`config.py:7-8`) |
| Settings | `setting` | `def setting(name: str, default: str) -> str:` (`secrets.py:34`) |
| Preflight of a model | pattern | `python -m rag.common.llm_check ollama:qwen2.5:7b` exists; it builds `get_llm(spec, cache_dir=None)` and calls `llm.generate("Answer in one short sentence.", "What does BM25 stand for?", 60)` inside `except Exception` (`rag/common/llm_check.py:22-34`) |
| Experiment file shape | `rag/experiments/about.py` | pure functions first, `main()` last, `from rag.common.llm import get_llm  # imported here so the pure functions above load without a backend` inside `main` (`about.py:85`) |
| Offline test shape | `tests/test_about_experiment.py` | `fake_judge(stated_for)` returns `FakeLLM(reply)` producing `{"results": [...]}` JSON; tests call the pure functions, never `main()` |

### Phase 1-3 symbols this phase imports (PLANNED, not executed - Wave 0 must verify)

| Symbol | Contract per plan | Source |
|--------|-------------------|--------|
| `HistoryTurn` | `@dataclass(frozen=True)`: `question: str`, `answer: str`, `asked_at: str` ISO-8601 UTC, `rewritten: Optional[str] = None` | [CITED: 01-05-PLAN.md lines 96] |
| `window(turns: Sequence[HistoryTurn], n: int = HISTORY_WINDOW_TURNS) -> List[HistoryTurn]`, `render_block(turns: Sequence[HistoryTurn]) -> str` (`render_block([])` is `""`), `HISTORY_WINDOW_TURNS = 6`, `HISTORY_ANSWER_MAX_WORDS = 40`, `HISTORY_QUESTION_MAX_WORDS = 60` | | [CITED: 01-05-PLAN.md lines 97-100] |
| `RagPipeline.answer(trace, history_block="")` | per-call keyword | [CITED: 01-03-PLAN.md line 23] |
| `needs_rewrite(message: str, window: Sequence[HistoryTurn]) -> bool` | deterministic gate; `False` on empty window or empty message | [CITED: 03-01-PLAN.md line 22, 106] |
| `rewrite_question(llm: LLM, message: str, window: Sequence[HistoryTurn], allow_clarify: bool = True, doc_names: Sequence[str] = ()) -> RewriteResult` | total (never raises); one `generate(system, user, max_output_tokens=120)` call | [CITED: 03-01-PLAN.md line 106] |
| `RewriteResult` | `@dataclass(frozen=True)`: `status: str`, `question: str`, `reason: Optional[str] = None`, `rewritten_question: Optional[str] = None`, `clarify_question: Optional[str] = None`, `rejected_question: Optional[str] = None`, `elapsed_ms: float = 0.0` | [CITED: 03-01-PLAN.md line 106] |
| `STATUSES = ("off", "skipped", "standalone", "rewritten", "clarify", "new_topic", "fallback")`, `REASONS = ("unavailable", "timeout", "empty", "unparsed", "dropped_constraint", "invented_detail", "too_long", "flagged", "topic_leak", "input_too_long")` | closed tuples | [CITED: 03-01-PLAN.md line 106] |
| Gate behaviour | `False` only when the message has at least 10 `str.split()` words and no anaphora/opener marker; every shorter message goes to the model | [CITED: 03-01-PLAN.md line 22] |

Risk: the executed Phase 3 may deviate (names, `elapsed_ms` semantics). The first Phase 4 task must be a contract check like 03-01 Task 1 (an `import` one-liner), and must stop on a mismatch.

## Package Legitimacy Audit

No external package is recommended for this phase; no install command is in any recommended task. `gsd_run query package-legitimacy check` was therefore not needed.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none) | - | - | - | - | - | n/a |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
data/golden/ddia_conversations.jsonl
        |  load_conversations()  (rejects unknown keys, bad pages, dup ids, bad category/expect/review)
        v
 [GoldConversation x N]  ---- to_question() ----> GoldQuestion adapter (standalone, gold_pages,
        |                                          evidence_terms, key_facts)  --> verify_golden.verify()
        |   per item: history = [HistoryTurn(q, a, FIXED_TS) for each fixed turn]   (teacher-forced,
        |             win = window(history)   same for every arm)
        v
 +-----------------------------------------------------------------------------------+
 | query per arm                                                                      |
 |  off    : message                                                                  |
 |  oracle : standalone                                                               |
 |  concat : previous user question + " " + message                                   |
 |  on     : needs_rewrite(message, win)?                                             |
 |             no  -> RewriteResult("skipped", message)                               |
 |             yes -> rewrite_question(rewriter, message, win, allow_clarify=True,    |
 |                       doc_names)  -> status: standalone | rewritten | new_topic |  |
 |                       clarify | fallback  (fallback = counted failure, retrieve    |
 |                       on message)                                                  |
 |             clarify on an expect=="answer" item => no retrieval, hit = 0           |
 +-----------------------------------------------------------------------------------+
        |  query string
        v
 RetrievalPipeline.run(item_id, query, CONFIGS["weighted"])  (semantic chunks, mpnet index,
        |                                                     memory store, same as invariant)
        v
 strict_trace(trace, evidence_terms) -> score_hits(context hits, gold_pages, KS)
        |  per item, per arm: hit@5 in {0,1}, mrr, recall@5, context chunk ids
        v
 paired(on vs off) -> wins/ties/losses  --> sign test (one-sided exact)
 per-category table, status counts, gate P/R, latency p50/p95, oracle gap closed
        |
        +--> regression arm: 37 answerable single-turn questions as FIRST turn (empty window):
        |      rewriter calls == 0 and context chunk ids == off
        +--> clarify items scored apart: asked? named both candidates? second call with
        |      allow_clarify=False never clarifies
        +--> (--answers, optional) RagPipeline.answer(trace, history_block) for off / on(rewritten slot)
        |      / on(original slot) / oracle -> judge_facts -> correct
        v
 evaluate_rule(summary) -> [(a..f, passed, detail)] -> ship_on? 
        v
 runs/conversation/<UTC timestamp>/report.json (gitignored)  --> docs/chat_memory_eval.md (committed)
        v
 decision commit: build_default_service default (only if ship_on)
```

### Recommended Project Structure

```
rag/observe/golden_conversations.py   # GoldTurn, GoldConversation, load_conversations (loader only; no model, no retrieval)
rag/experiments/conversation.py       # pure core (arms, scoring, pairing, stats, evaluate_rule, report) + build_parser() + main()
data/golden/ddia_conversations.jsonl  # frozen set (committed)
data/golden/MULTITURN_REVIEW.md       # per-item review state + baseline check output (Pitfall 11 asks for it)
docs/chat_memory_eval.md              # first section = shipping rule (own commit), then results
tests/test_golden_conversations.py    # loader + committed-file tests
tests/test_conversation_experiment.py # offline smoke + rule + regression arm tests
```

### Pattern 1: Pure core, thin `main()` (copy `rag/experiments/about.py`)
**What:** All logic in functions that take a ready `RetrievalPipeline`, a rewriter LLM object (or `None`), optional generator/judge, and return plain dicts. `main()` only parses args, builds models, calls the core, prints, and writes `report.json`. Lazy-import `get_llm` inside `main()`.
**When to use:** Always here; it is what makes the offline smoke test (CONTEXT "Specifics") possible without monkeypatching the world.

### Pattern 2: Arms differ only in the query string (and, for answers, the slot)
**What:** One function `arm_queries(item, rewrite_result) -> Dict[str, str]` returns the four query strings; one function `score_query(pipeline, config, item, query, arm)` runs retrieval and scoring. Identical history means identical `win` object passed to the rewriter and identical `history_block` to the answer prompt. A test spies on both.
**Source:** CONTEXT D-05; PITFALLS Pitfall 10.

### Pattern 3: Rule as code and as prose
**What:** `evaluate_rule(summary) -> RuleResult` (list of `(label, passed, detail)` plus `ship_on`) is unit tested over a table of (n, wins, losses, ...) cases; the prose in `docs/chat_memory_eval.md` and the module docstring is the same text. A test asserts that the constants quoted in the prose (`8`, `300`, `3`, `10%`) equal the constants in code.

### Pattern 4: Refuse to score before the rule is committed
**What:** `rule_is_committed()` runs `git log -1 --format=%H -- docs/chat_memory_eval.md` and `git diff --quiet HEAD -- docs/chat_memory_eval.md` (argv lists, no shell). `main()` exits with a message if the `on` arm is requested and either check fails; the report stores the sha. This turns "committed before the first scored run" from a promise into a checked precondition. [recommendation]

### Anti-Patterns to Avoid
- **Importing `rag/api` or the conversation store:** the experiment retrieves through `RetrievalPipeline` only (CONTEXT Integration Points).
- **Using model-generated earlier answers as history:** breaks "identical teacher-forced histories" (Pitfall 10).
- **Treating a fallback as `off`:** a fallback is a counted failure; retrieval for that item still runs on the raw message (that is what the service does), but it is counted in (e) and in the status table.
- **Scoring ambiguous items with hit@5:** they have no gold pages; score them as clarify items (Pitfall 11).
- **Choosing the threshold after seeing numbers:** commit the rule text first; the suggested order is in "Plan outline".
- **Using the LLM disk cache for the rewriter in this experiment:** see Pitfall 3 below.

## Schema reconciliation (D-01 versus the Phase 3 draft rows)

The draft rows from plan 03-03 do not match D-01 and cannot be loaded by a strict loader as they stand [CITED: 03-03-PLAN.md lines 21, 123 and artifacts row]:

| Item | Draft (03-03) | D-01 | Recommendation |
|------|---------------|------|----------------|
| `expect` | `rewrite`, `new_topic`, `clarify`, `standalone` | `answer` or `clarify` | Use D-01. The authoring step converts: all non-clarify drafts become `answer`; the category carries the finer expectation (a `topic_switch` item is where `new_topic` is expected). |
| `evidence_terms` | absent | absent | ADD to the schema. Strict relevance (`strict_trace`) needs it, and the invariant is strict. Copy it from the source single-turn row when `standalone` equals that row's question; new standalone texts need terms checked by `verify()`. Without it the scorer silently falls back to page overlap (`strictify` returns hits untouched when `terms` is empty, `metrics.py:33-34`), which CLAUDE.md says not to use. |
| `source_id`, `notes` | present | absent | Keep as optional fields (`source_id: Optional[str] = None`, `notes: str = ""`) so provenance survives; the loader still rejects any other key. |
| `standalone` | `null` for ambiguous | "human-written standalone" | Type `Optional[str]`; validate `None` iff `expect == "clarify"`. |
| `key_facts` | absent | present | Required non-empty for `expect == "answer"`; copy from the source row. |
| `constraint_follow_up` | no draft rows | category required | At least 4 items must be authored from scratch (see seeds). |
| `reference_answer` | absent | absent | Not needed: `to_question()` sets `reference_answer=" ".join(key_facts)` so `GoldQuestion.validate()` (which demands a reference answer for answerable questions, `golden.py:56-57`) passes. |

Recommended validation rules in `validate()` (all mechanical, all unit-testable):
- unknown key, missing key, wrong type -> `ValueError` naming `path:line` and the key (do not rely on the dataclass `TypeError`, which `golden.py` does; a `ValueError` with the key name is the better message and matches the repo's "28 sites raise `ValueError`" convention).
- `category` in the five; `expect` in `("answer", "clarify")`; `review` in `("pending-human", "approved")`; `id` unique.
- `turns` non-empty list of `{question, answer}` (a first turn never reaches the rewriter); answers longer than `HISTORY_ANSWER_MAX_WORDS` (40) would be truncated at render time, so warn or reject over about 60 words so what the rewriter sees equals what was authored.
- `expect == "clarify"` -> category `ambiguous_follow_up`, `standalone is None`, `gold_pages == []`, `key_facts == []`, `must_contain` = the two candidate terms (reused to score "named both candidates").
- `expect == "answer"` -> `standalone` non-empty, `gold_pages` non-empty with `1 <= start <= end`, `key_facts` and `evidence_terms` non-empty.
- `standalone_in_conversation` and `topic_switch` -> normalised `standalone == message`; `pronoun_follow_up` and `constraint_follow_up` -> `standalone != message`.
- `topic_switch` -> `must_not_contain` non-empty and none of those words in `standalone`; `constraint_follow_up` -> `must_contain` non-empty, each term present in `message` (lower-cased).

## Experiment design (arm semantics the plan must pin)

1. **History:** `HistoryTurn(question, answer, "1970-01-01T00:00:00+00:00")` per fixed turn (constant timestamp; no wall clock in a deterministic experiment). `win = window(history)`.
2. **`off`:** query = `message`.
3. **`oracle`:** query = `standalone` (skipped for clarify items).
4. **`concat`:** query = `turns[-1].question + " " + message` (discretion; document it).
5. **`on`:** `if not needs_rewrite(message, win): RewriteResult("skipped", message)` else `rewrite_question(rewriter, message, win, allow_clarify=True, doc_names=["ddia.pdf"])`. Pass the one document name that `data/raw/ddia.pdf` has [VERIFIED: `ls data/raw` shows `ddia.pdf`] so the prompt has the same shape as a one-document service call [ASSUMED: the service passes scoped document names, per 03-04 Task 1]. Effective query = `result.question` (equals `message` for every status except `rewritten`). Retrieval for `fallback`, `standalone`, `new_topic` and `skipped` is on `message`.
6. **False clarify:** an `expect == "answer"` item whose `on` status is `clarify` gets `hit@5 = 0` and `mrr = 0` for `on` (the user got no answer; the service does no retrieval on the clarify path, 03-04 truths) and is counted in a `false_clarify` rate. Not scoring it as `off`'s result is the honest choice and must be in the rule text.
7. **New topic:** `new_topic` retrieves on `message` (identical to `off` for retrieval). For the answer arm, the `on` history block is `render_block([])` (the service starts clean after a topic switch, 03-04 truths), while `off` and `oracle` get the full block.
8. **Scored set:** n = number of items with `expect == "answer"` across all non-ambiguous categories. Clarify items are scored apart and are excluded from n. If D-02's "30 scored turns" is read as including clarify items the rule would be computed on fewer than 30; the authoring target should therefore be at least 30 answer-expected items plus at least 4 clarify items (about 34-35 rows).
9. **Rewriter construction:** `get_llm(spec, cache_dir=None)` (no disk cache). One warm-up call (not recorded) before timing so p50 is not dominated by a cold model load.
10. **Preflight:** a one-token `generate` inside `except Exception` with a logged class name. If the rewriter is unreachable, skip the `on` arm and print/record "not run: rewriter unreachable" instead of recording 100% fallbacks, which would look like a measurement. Same for the generator when `--answers` is passed (D-14).
11. **Repeats:** `--repeats N` (default 1; the committed run uses 3). The rule is evaluated on repeat 1; repeats 2 and 3 report per-repeat `on` hit@5 and "items whose hit changed" as instability. The rewriter is built without cache so repeats are real draws.
12. **Two-rewriter comparison (D-10):** run the command twice with different `--rewriter`, retrieval only (`--arms off,on`), the second as `REMOTE_REASONING_EFFORT=low python -m rag.experiments.conversation --rewriter vllm:/models/gpt-oss-20b ...`. The environment variable is documented in `.env.example:15` as `# REMOTE_REASONING_EFFORT=low    # low, medium or high; lower is faster and cheaper`, and the provider reads it when it is constructed; so keep it out of any run that also uses the same generator for `--answers`. Selection rule written precisely: choose the second model only if its `on` hit@5 exceeds qwen's by more than the band; otherwise the lower p50. The shipping rule (a)-(f) is then evaluated on the chosen model. Because switching needs a margin larger than the band, the winner's-curse inflation is bounded.
13. **Answer arms (`--answers`):** build `RagPipeline(retrieval, generator, style="standard", subject="book")`, call `answer(trace, history_block=render_block(win))` for `off` (question slot = message), `oracle` (slot = standalone), and `on` twice with the same retrieval trace: slot = rewritten question vs slot = original message (`dataclasses.replace(trace, question=message)` before the second call). Passages are identical across the two `on` calls, so the difference is the slot alone. Score `correct` as: abstention -> False, else `judge_facts(judge, answer, key_facts).correct` (skip the faithfulness call; D-06 names only the fact checklist and it halves judge calls). Items with identical prompts (skipped gate) reuse one generation. The answer generator may use the default LLM cache (public book text; `rag/README.md:144-145` says replies are cached by prompt); the judge and rewriter flag in the results file that rewriter and judge can be the same model (D-12).
14. **Metrics to print (D-06):** per arm hit@5, mrr, recall@5 (means over n); `oracle_gap_closed = (on_hits - off_hits) / (oracle_hits - off_hits)` printed `n/a` when the denominator is below 3 items (it is a ratio of two small counts); wins/ties/losses and sign-test p; per-category table of the same; status counts with fallback reasons; gate precision and recall where "needs a rewrite" = `normalised standalone != message` (so topic switch and standalone items are negatives, pronoun and constraint items positives; ambiguous items count as positives for the gate because the model is needed to clarify) and "gate misses" = items the gate skipped where `off` missed and `oracle` hit; latency p50/p95 over items where the gate fired and the status is not `fallback` with reason `input_too_long` (nearest-rank percentile; print the count behind it); must_contain kept rate and must_not_contain leak rate on the effective question; clarify items: asked, named both (every `must_contain` term in `clarify_question`, case-insensitive), and a second call with `allow_clarify=False` that must not return `clarify`.
15. **Fallback rate for (e):** fallbacks (any reason, including guard rejections such as `invented_detail`) divided by items where the gate fired. Expect this to be the condition most likely to fail with a 7B model and conservative guards; record the reason breakdown.
16. **Regression arm (D-09):** for each of the 37 answerable questions in `data/golden/ddia_questions.jsonl` (`load_golden`, `answerable`), history = `[]`; call `needs_rewrite(q.question, [])`; assert no rewriter call (spy) and `[h.chunk_id for h in context] == ` the `off` list. This is literal D-09. Optional informational variant (non-gating, recommended): put one unrelated prior turn (question and a one-sentence answer taken from another golden row's `reference_answer`) before each of the 37, count how many the rewriter touched and how many hit@5 results changed; this is Pitfall 10's "over-rewriting detector" and costs about 37 extra gate checks and up to 37 rewriter calls.

## Statistics behind D-07 (computed this session; script in scratchpad `stats.py`, `stats2.py`)

hit@5 per item is exactly 0 or 1 (`metrics.py:77`), so `gain_points = 100 * (wins - losses) / n`, and "gain exceeds the band" is equivalent to `net > band * n / 100`.

| n | one item (points) | band = max(8, 300/n) | smallest net that satisfies (a) |
|---|-------------------|----------------------|---------------------------------|
| 20 | 5.00 | 15.00 | 4 |
| 25 | 4.00 | 12.00 | 4 |
| 28 | 3.57 | 10.71 | 4 |
| 30 | 3.33 | 10.00 | 4 (net 3 is exactly 10.0, not "exceeds") |
| 33 | 3.03 | 9.09 | 4 |
| 37 | 2.70 | 8.11 | 4 |
| 38 | 2.63 | 8.00 | 4 |
| 40 | 2.50 | 8.00 | 4 |
| 50 | 2.00 | 8.00 | 5 |

Consequences for the rule text [VERIFIED: computed]:
1. For every n >= 1, `band * n / 100 >= 3`, so (a) implies net >= 4 and therefore (b) (net >= 3). (b) never binds. Keep it (D-07 is locked and it costs nothing) but write "(b) is implied by (a) and recorded for the reader".
2. "Exceeds" must be strict. State `gain_points > band` with the exact arithmetic in the rule text, so n = 30 with net = 3 (exactly 10.0 points) is "not exceeded".
3. The exact one-sided sign test on discordant pairs (wins W, losses L, null P(win)=0.5) is stricter than the band rule:

| losses | fewest wins with one-sided p < 0.05 | band rule at n = 30 needs wins >= |
|--------|-------------------------------------|-----------------------------------|
| 0 | 5 (p = 0.031) | 4 |
| 1 | 7 (p = 0.035) | 5 |
| 2 | 9 (p = 0.033) | 6 |
| 3 | 10 (p = 0.046) | 7 |
| 4 | 12 (p = 0.038) | 8 |
| 5 | 13 (p = 0.048) | 9 |

   Examples: 4 wins / 0 losses passes the band but p = 0.0625; 8 / 4 (net 4) passes the band with p = 0.194. So the results file must print the p-value and, when the band is cleared but p >= 0.05, say "clears the project band; weak evidence (sign test p = ...)". Do not make it gating (D-07 is locked); report it.
4. Power (simulation, 20,000 trials, independent items, P(win) / P(loss) per item): at n = 30 the D-07 rule (a and b) passes with probability 0.23 at P(win)=0.10, P(loss)=0.03 (true gain +7 points), 0.51 at +12, 0.74 at +17, 0.95 at +27; the sign test alone reaches 0.26 at +12, 0.48 at +17, 0.81 at +27. At n = 37 the rule passes 0.64 at +12 and 0.85 at +17. So the set can show only a large effect; "ships off, inside the band" is a probable and legitimate outcome (ROADMAP Planning Notes say the same).
5. Dilution: standalone and topic-switch items should tie (the gate skips long marker-free messages), so the discriminating items are the pronoun and constraint ones (about half of n). Defining n as all answer-expected items is the literal D-07 reading and the conservative one; also print the pronoun+constraint subset's paired counts and p, non-gating.
6. Items are paired by construction (same item, same retrieval, only the query differs), which is more powerful than comparing two proportions. Items seeded from the same source question are correlated; limit to one item per source question per category where possible.
7. 32 of 37 gives the invariant: `32/37 = 0.8649` [VERIFIED: computed], so a single changed answerable question moves the single-turn hit@5 to 0.838 or 0.892; the invariant check is therefore sensitive to one flipped question.

### Draft of the rule text (to commit first, in `docs/chat_memory_eval.md` under `## Shipping rule (committed before the first run)` and in the module docstring)

> n is the number of items in `data/golden/ddia_conversations.jsonl` with `expect == "answer"` (clarify items are scored apart and not in n). For item i, `off_i` and `on_i` are strict, evidence-aware hit@5 (0 or 1) of the context stage with semantic chunks and the `weighted` config, on the teacher-forced history of the item. When the rewriter returns `clarify` for an answer-expected item, `on_i = 0`. When the rewriter falls back, retrieval runs on the raw message and the fallback is counted in (e). wins = #(on=1, off=0); losses = #(on=0, off=1); net = wins - losses; gain = 100 * net / n points; band = max(8, 300 / n) points. Rewriting ships default-on only if all hold: (a) gain > band (strictly); (b) net >= 3 (implied by (a)); (c) no item in `standalone_in_conversation` has `on_i < off_i`; (d) in the regression arm all 37 answerable questions make zero rewriter calls and return the same context chunk ids as `off`; (e) fallbacks <= 10% of the items on which the gate called the rewriter; (f) every scored item has `review == "approved"`. Reported, not gating: the one-sided exact sign test p on (wins, losses), the oracle gap closed, per-category tables, answer-level results, instability across repeats. Otherwise rewriting ships off and the numbers are recorded. This text is committed before any run that uses the rewriter.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| hit@5 / mrr / recall@5 on gold pages | own page-overlap scorer | `strict_trace` + `score_hits` | Evidence-aware strictness is what the 0.865 invariant uses; a different scorer would not be comparable |
| Fact-checklist judging | own prompt | `judge_facts` | Calibrated (rag/README Step 6); the holistic judge is forbidden |
| Verifying new gold pages and evidence terms | own page grep | `verify_golden.verify` via `GoldConversation.to_question()` | Handles whitespace-aligned code, multi-range checks, distractor pages |
| Gate and rewriter | a copy in the experiment | `needs_rewrite` + `rewrite_question` from `rag/query/rewrite.py` | The experiment must measure the shipped code; a copy measures something else |
| History block | hand-built text | `window` + `render_block` | It neutralizes and caps exactly as the service will |
| Exact test | scipy | `math.comb` | 3 lines; no dependency |
| Percentiles | numpy percentile with interpolation | nearest-rank on a sorted list | With ~20 calls interpolation gives numbers no call produced; state the rank rule |
| Rule-before-run proof | trusting memory | `rule_is_committed()` guard + `git log` order check | Cheap and checkable |

**Key insight:** every number in the results file must come from a function that also has a unit test on a 3-item fixture; the live run only supplies the inputs.

## Common Pitfalls

### Pitfall 1: The set cannot discriminate (Pitfall 11)
**What goes wrong:** the follow-up still contains the topic word, `off` already hits, every arm ties.
**Why:** authors write natural follow-ups that repeat the noun.
**How to avoid:** a `--check-set` mode (arms `off` and `oracle` only, no rewriter, no tunnel) prints per item `off`/`oracle` hit@5 and the count of baseline misses among pronoun and constraint items; require at least half (D-02). Items where `off` equals `oracle` are labelled `control` in `MULTITURN_REVIEW.md` and kept.
**Warning signs:** most pronoun items have `off == oracle`.

### Pitfall 2: Standalone items never exercise the gate
**What goes wrong:** condition (c) ("no loss on `standalone_in_conversation`") passes trivially because every standalone message is 10 or more words with no marker, so the gate skips it and `on == off` by construction. Most source questions are 12-20 words.
**How to avoid:** make at least half of the standalone items short (under 10 words) or marker-bearing ("that" in a complete sentence), so the model is called and can over-rewrite. Report the gate-fired count per category.

### Pitfall 3: Cache makes repeats meaningless and may hide history
**What goes wrong:** with the default disk cache the second and third repeat return the first draw; instability reads 0. PITFALLS Pitfall 7 also warns an experiment cache keyed without the history conflates arms.
**Why:** the cache key composition lives in the provider module, which the project rules keep unread in this session.
**How to avoid:** rewriter `get_llm(spec, cache_dir=None)` in this experiment. [ASSUMED: the default `OllamaLLM` sampling is not deterministic; repeats are the safeguard.] The answer generator may keep the default cache because the prompt (passages + history block + question) is the key and a changed question changes the prompt.

### Pitfall 4: Judge and rewriter are the same model
**What goes wrong:** `qwen2.5:7b` rewrites and judges; a rewrite that echoes the judge's blind spots inflates answer scores (STATE.md Phase 4 concern).
**How to avoid:** retrieval is the decision metric (D-12). Flag the identity in the results file; do not act on answer results inside the band; if the owner wants to act on a borderline answer result, re-score with another judge (a deferred idea).

### Pitfall 5: A false guard rejection looks like a rewriter failure
**What goes wrong:** `invented_detail` rejects a correct rewrite (a capitalised word not shown), the status becomes `fallback`, (e) fails.
**How to avoid:** print `rejected_question` next to `reason` for every fallback in the report so the owner can tell a bad rewrite from an over-strict guard; do not adjust the guards inside Phase 4 (that would be tuning on the eval set; Phase 3 owns them).

### Pitfall 6: The default flip breaks a Phase 3 test
**What goes wrong:** plan 03-06 contains `test_build_default_service_ships_the_switch_off` asserting an unset `RAG_REWRITE` builds no rewriter [CITED: 03-06-PLAN.md lines 22, 187]. If D-13 flips the default on, that test fails.
**How to avoid:** the flip commit must change that test in the same commit (and any other test that relies on the default). Add `test_the_default_matches_the_recorded_decision`, which reads the decision line from `docs/chat_memory_eval.md` and asserts the same outcome through the Phase 3 `spied_settings` helper, so the default can only differ from the decision by failing a test.

### Pitfall 7: Changing the question slot needs code
**What goes wrong:** if D-11 measures that the original-message slot wins by more than the band, `Trace.question` (the effective question) is no longer the slot; this edits `rag/api/service.py`.
**How to avoid:** the expected result is "keep rewritten" (no code). Reserve a conditional task; if triggered it is a small separate commit with its own test, and only if `--answers` actually ran.

### Pitfall 8: Mixing printed and PDF pages in new items
**How to avoid:** reuse `gold_pages` from the source row where possible; run `verify()` over every item through `to_question()`; for new items take pages from `data/processed/ddia.pages.jsonl` (PDF page numbers).

### Pitfall 9: Windows multiprocessing and stdin
**What goes wrong:** none expected (no multiprocessing), but the sandbox is not used; do not invoke the experiment from stdin. Write helper scripts as files (project rule).

## Code Examples

Values below come from the verbatim quotes above or from the planned Phase 3 contract; they are skeletons, not final code.

### Loader skeleton (copy the `golden.py` shape, add explicit key checks)
```python
# Source pattern: rag/observe/golden.py:65-80 (load_golden)
CATEGORIES = ("pronoun_follow_up", "constraint_follow_up", "topic_switch",
              "ambiguous_follow_up", "standalone_in_conversation")
EXPECTS = ("answer", "clarify")
REVIEW_STATES = ("pending-human", "approved")

@dataclass(frozen=True)
class GoldConversation:
    id: str
    category: str
    turns: List[GoldTurn]
    message: str
    standalone: Optional[str]
    gold_pages: List[Tuple[int, int]]  # inclusive PDF page ranges
    expect: str
    key_facts: List[str]
    evidence_terms: List[str]
    must_contain: List[str]
    must_not_contain: List[str]
    review: str
    source_id: Optional[str] = None
    notes: str = ""

    def validate(self) -> None: ...        # rules in "Schema reconciliation"
    def to_question(self) -> GoldQuestion: # for verify() and score_answer()
        return GoldQuestion(id=self.id, question=self.standalone or self.message, type="factual",
                            answerable=self.expect == "answer",
                            reference_answer=" ".join(self.key_facts),
                            gold_pages=list(self.gold_pages), evidence_terms=list(self.evidence_terms),
                            key_facts=list(self.key_facts))
```

### Scoring one query (strict, in memory)
```python
def score_query(pipeline, config, item, query, run_id):
    trace = pipeline.run(run_id, query, config)               # RetrievalPipeline.run, pipeline.py:62
    judged = strict_trace(trace, item.evidence_terms)          # metrics.py:43
    context = judged.stage("context").hits
    scores = score_hits(context, item.gold_pages, KS)          # metrics.py:109, KS = (1, 3, 5, 10, 30)
    return {"hit@5": scores["hit@5"], "mrr": scores["mrr"], "recall@5": scores["recall@5"],
            "chunk_ids": [h.chunk_id for h in trace.stage("context").hits]}, trace
```

### Paired counts, exact sign test, noise band
```python
from math import comb

def noise_band(n: int) -> float:
    return max(8.0, 300.0 / n)          # D-07; n = answer-expected items

def paired(off: Dict[str, float], on: Dict[str, float]) -> Dict[str, int]:
    wins = sum(1 for i in off if on[i] > off[i]); losses = sum(1 for i in off if on[i] < off[i])
    return {"win": wins, "tie": len(off) - wins - losses, "loss": losses}

def sign_test_p(wins: int, losses: int) -> float:
    """One-sided exact binomial P(X >= wins | wins + losses, 0.5); 1.0 with no discordant pair."""
    d = wins + losses
    return sum(comb(d, k) for k in range(wins, d + 1)) / 2 ** d if d else 1.0
```

### Rule evaluation (pure, table-tested)
```python
def evaluate_rule(n, counts, standalone_losses, regression_identical, regression_calls,
                  fallbacks, gate_calls, all_approved):
    wins, losses = counts["win"], counts["loss"]
    gain = 100.0 * (wins - losses) / n if n else 0.0
    band = noise_band(n) if n else float("inf")
    checks = [("a gain > band", gain > band, f"gain {gain:.1f} vs band {band:.1f}"),
              ("b net wins >= 3", wins - losses >= 3, f"net {wins - losses}"),
              ("c no standalone loss", standalone_losses == 0, f"{standalone_losses} losses"),
              ("d regression identical", regression_identical and regression_calls == 0, ""),
              ("e fallback rate <= 10%", gate_calls > 0 and fallbacks <= 0.10 * gate_calls, f"{fallbacks}/{gate_calls}"),
              ("f every item approved", all_approved, "")]
    return checks, all(ok for _, ok, _ in checks)
```
(With `gate_calls == 0` the `on` arm made no rewriter call at all, which cannot be shown to be a gain; (a) fails first in that case.)

### Offline fixture (copy `tests/test_retrieval.py:105-114`)
```python
def _pipeline(chunkset):
    embedder = HashingEmbedder()
    return RetrievalPipeline.from_chunkset(chunkset, VectorIndex.build(chunkset.chunks, embedder), embedder, None)

PAGES = [Page(1, "Cats chase mice around the garden every single morning. " * 12),
         Page(2, "A write ahead log records every change before it reaches the tree page. " * 12),
         Page(3, "Stream processors join an event stream with a table of user profiles. " * 12)]
chunkset = RecursiveChunker(size=40, overlap=5).chunk(Document.from_pages(PAGES))
```
The fake rewriter replies by looking up the message after the final `Last message: ` of the user prompt [CITED: 03-01-PLAN.md line 23] and returning a one-line `REWRITE: ...` payload written in lower case from words that appear in the turns, so the Phase 3 guards (`invented_detail`, `dropped_constraint`) accept it. `FakeLLM(lambda system, user: ...)` is the established call shape (`tests/test_api.py:31`).

## Authoring seeds (unverified; baseline-miss status must be measured with `--check-set`)

Source single-turn rows whose gold pages and key facts can be reused, chosen because the subject can be named in an earlier turn and elided in the follow-up [VERIFIED: ids, types and pages read from `data/golden/ddia_questions.jsonl` this session]:

| Use | Source ids (gold pages are PDF pages) | Why |
|-----|----------------------------------------|-----|
| pronoun follow-up | q015 (B-tree writes more than once, p106), q019 (Bloom filter, p101), q021 (sloppy quorum, p203-205), q026 (monotonic reads, p187), q027 (hot-key prefix, p227), q016 (fencing, p325), q031 (read repair, p201), q034 (pessimistic vs optimistic, p284), q022 (LSM vs B-tree, p105-106), q023 (document vs term partitioned indexes, p229-231) | Short, one clear subject; put a more recent distractor entity in a second turn for at least 3 of them (Pitfall 11) |
| constraint follow-up | q041 (2^53 identifiers, p136), q029 (unbounded delays, p304), q003 (Table 3-1, p113), q012 (two functions, p69), q011 (SQL:1999, p76), q013 (Example 12-2, p540) | Message carries a number, a table/example name or a quoted term the rewrite must keep (`must_contain`) |
| standalone in conversation | q002, q017, q028, q030, q036, q042 plus 2 short ones such as q008 ("2PC vs 3PC") | See Pitfall 2: include short or marker-bearing messages |
| topic switch | any two sources whose topics are in different chapters (replication vs storage engines, partitioning vs batch processing) | `must_not_contain` = a content word of the earlier turn absent from the standalone |
| ambiguous | two turns naming two candidates equally (leader-based vs leaderless replication; B-tree vs LSM-tree) | `expect: clarify`, `must_contain` = the two candidate terms |

All 37 answerable ids: q001-q003, q008-q034, q036-q042 (45 rows, 37 answerable) [VERIFIED: counted this session]. Do not add a prior-turn answer longer than about 40 words, no URL, no instruction-like text, no email address (the sensitive-canary hook blocks them), and no `[S n]` markers.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| One judge score on a whole multi-turn run | Retrieval on the rewritten query as the decision metric; answers informational (Pitfall 10) | project decision | No judge variance in the ship/no-ship call |
| Threshold chosen after the numbers | Rule committed first, enforced by a guard and a `git log` check | this phase | Pre-registration |
| Unpaired proportions | Paired per-item win/tie/loss plus exact sign test | this phase | Honest at n = 30 |

**Deprecated/outdated:** the holistic correctness judge and page-overlap-only relevance (CLAUDE.md: unreliable, do not retry).

## Runtime State Inventory

Not applicable: this is not a rename, refactor or migration phase. Stored data, live service config, OS-registered state, secrets and build artifacts are untouched; the only new runtime artefacts are the gitignored `runs/conversation/<timestamp>/` folders and the committed files listed above. (`runs/` is ignored: `.gitignore:167: runs/`, confirmed with `git check-ignore`.)

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Phase 1-3 symbols exist as the plans say (`HistoryTurn`, `window`, `render_block`, `needs_rewrite`, `rewrite_question`, `RewriteResult`, `STATUSES`, `RagPipeline.answer(history_block=)`) | Standard Stack | Wave 0 contract check fails; adapt names, do not edit Phase 1-3 files |
| A2 | Ollama's default sampling for `qwen2.5:7b` is not deterministic (temperature not read; provider file off-limits) | Pitfall 3, Experiment design 11 | If deterministic, repeats cost little and show 0 instability; no harm |
| A3 | The service passes scoped document names to `rewrite_question`, so the experiment should pass `["ddia.pdf"]` | Experiment design 5 | Prompt shape differs slightly from the service; both measured cases are single-document, effect is small |
| A4 | Rewriter latency is a few seconds per call and `--answers` takes on the order of 10-20 minutes with 4 workers | Environment | Plan time estimates off; no correctness risk |
| A5 | A `REMOTE_REASONING_EFFORT=low` process-level variable is read at construction by the vLLM client (seen in a search hit this session; file not opened) and is shown in `.env.example:15` | Experiment design 12 | The comparison run uses the wrong effort; mitigated by recording the env var in the report |
| A6 | Rewriter selection with a margin larger than the band bounds winner's-curse inflation | Experiment design 12 | Slight optimism in the chosen model's number; the shipping rule is still strict |
| A7 | The first 8 draft rows from plan 03-03 will exist (`conversations_draft.jsonl`) and can seed pronoun/topic/ambiguous/standalone items | Schema reconciliation | If missing, author all items from the seeds table |
| A8 | Gate precision/recall definition ("needs a rewrite" = normalised `standalone != message`) is acceptable to the owner | Experiment design 14 | Different definition changes two printed numbers only |
| A9 | The gating rule should treat `clarify` on an answer-expected item as `on_i = 0` | Experiment design 6 | If the owner prefers "as off", (a) would be slightly easier to clear |
| A10 | Tunnel (vLLM generator) availability is unknown; only Ollama was probed | Environment Availability | Answer arms and the gpt-oss rewriter comparison may be skipped (D-14 covers it) |

## Open Questions (RESOLVED)

1. **Which `expect` vocabulary does the golden file use, given the Phase 3 drafts use four values?**
   - RESOLVED: D-01 (`answer` | `clarify`). Recommendation for conversion: all non-clarify drafts become `answer`; the category carries the finer expectation. Draft file `conversations_draft.jsonl` is left in place or removed by the authoring plan (it is read by no test).

2. **Which items count in n for the noise band?**
   - RESOLVED (recommendation, consistent with D-07's literal text): every item with `expect == "answer"` in all four non-ambiguous categories; clarify items excluded; the pronoun+constraint subset is reported as a non-gating secondary. Authoring target: at least 30 answer-expected items plus at least 4 clarify items.

3. **Is `evidence_terms` part of the schema?**
   - RESOLVED (recommendation): yes, add it; strict relevance requires it and D-01's list omits it. Also keep optional `source_id` and `notes`.

4. **How is a false clarify on an answer-expected item scored?**
   - RESOLVED (recommendation): `on_i = 0` (no answer was produced), and a `false_clarify` rate is printed. Written into the rule text.

5. **D-09 says "first turn", which makes the gate trivially skip (empty window). Is that enough?**
   - RESOLVED: D-09 is locked, implement it literally and make it gating (d). Add the non-gating "after one unrelated turn" variant as the real over-rewriting detector (Pitfall 10).

6. **Repeats and determinism (Pitfall 10 asks for 3 repeats).**
   - RESOLVED (recommendation): `--repeats 3` for the committed run, rewriter uncached, rule evaluated on repeat 1, instability reported. If the decision differs across repeats the results file says "unstable"; the default stays at whatever the repeat-1 rule says only if all three repeats agree, otherwise keep off. (This is a reporting convention, not a new gating condition; the orchestrator may drop it.)

7. **Rewriter disk cache in the experiment.**
   - RESOLVED (recommendation): `cache_dir=None` for the rewriter; generator and judge may use the default cache (public book text, reproducible reruns, README Step 6).

8. **Does (f) make the unattended outcome certain?**
   - RESOLVED by CONTEXT D-03: yes, with any `pending-human` row the default stays off and numbers are provisional. The experiment still prints (a)-(e) individually so the owner sees what would happen after review; a re-run after review is needed if any row text changes.

9. **Redundancy of (b).**
   - RESOLVED: keep (locked), annotate as implied by (a).

10. **What happens to the Phase 3 test that asserts the default is off if the rule says on?**
    - RESOLVED (recommendation): the flip commit updates it in the same commit and adds `test_the_default_matches_the_recorded_decision`.

11. **Answer-arm history blocks per arm.**
    - RESOLVED (recommendation): all arms get `render_block(win)`, except `on` after `new_topic`, which gets `render_block([])` (Phase 3 D-14); the two `on` slot variants share one retrieval trace.

12. **How are fallbacks and the denominator for (e) defined?**
    - RESOLVED (recommendation): numerator = all `fallback` statuses (guards included); denominator = items where the gate fired. `input_too_long` counts in the numerator.

13. **Two rewriters tried and one chosen: does that bias the rule?**
    - RESOLVED (recommendation): switch away from qwen only on a margin larger than the band; otherwise the lower p50; the rule is then evaluated once on the chosen model.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | everything | yes | 3.10.11 | n/a |
| Book chunks `data/processed/chunks/semantic.jsonl` | `off`/`on`/`oracle`/`concat` retrieval | yes (folder lists `semantic.jsonl`) | n/a | `--chunks-dir` override |
| Cached mpnet index `data/processed/index/semantic__sentence-transformers-all-mpnet-base-v2__plain` | retrieval without re-embedding | yes (folder listed) | n/a | `get_index(..., rebuild=False)` rebuilds if stale |
| `data/processed/ddia.pages.jsonl` | `verify()` of new gold pages/evidence | yes | n/a | tests skip with a message when absent |
| Ollama with `qwen2.5:7b` | rewriter default, judge | yes (`/api/tags` listed `qwen2.5:7b` this session) | 7B | skip `on` arm, record blocker (D-14) |
| vLLM generator `gpt-oss-20b` via PuTTY tunnel | `--answers`, gpt-oss rewriter comparison | not probed (no live model run was allowed) | n/a | skip with a printed note (D-06, D-14); check with `python -m rag.common.llm_check` |
| `git` | rule-first guard, report sha | yes | n/a | n/a |
| OpenSearch | not needed (memory store, same as the invariant) | n/a | n/a | n/a |

**Missing dependencies with no fallback:** none for the code, the golden set, the loader, the rule and the offline tests.
**Missing dependencies with fallback:** the tunnel (unverified) - D-14 path: commit everything, record blocker in STATE.md, keep default off.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest `>=8` (existing; no config file, flat `tests/`) |
| Config file | none |
| Quick run command | `python -m pytest tests/test_golden_conversations.py tests/test_conversation_experiment.py -q` |
| Full suite command | `python -m pytest tests -q` (baseline per CLAUDE.md: 591 passed, 2 skipped; Phases 1-3 add tests, so compare against the Phase 3 baseline recorded in STATE.md) |

### Phase Requirements -> Test Map

| Criterion / Req | Behavior | Test (file::name) | Automated Command | `fails_when` |
|-----------------|----------|-------------------|-------------------|--------------|
| SC1 / EVAL-01 | loader reads a valid row and builds `GoldConversation` | `tests/test_golden_conversations.py::test_a_valid_row_loads` | `python -m pytest tests/test_golden_conversations.py::test_a_valid_row_loads -q` | a field is dropped or typed wrong |
| SC1 / EVAL-01 | unknown key, missing key, unknown category, bad `expect`, bad `review`, bad page range, duplicate id, clarify with pages, answer without standalone/key_facts/evidence_terms, empty turns each raise `ValueError` (parametrized table, id = case name) | `tests/test_golden_conversations.py::test_a_bad_row_is_rejected[<case>]` | `python -m pytest tests/test_golden_conversations.py -k bad_row -q` | any case loads without error, or raises a non-`ValueError` |
| SC1 / EVAL-01 | `load_golden` is unchanged and still rejects a conversation row | `tests/test_golden_conversations.py::test_load_golden_is_untouched` + `git diff --quiet <P4_BASE> -- rag/observe/golden.py` | `python -m pytest tests/test_golden_conversations.py::test_load_golden_is_untouched -q` and `git diff --quiet "$P4_BASE" -- rag/observe/golden.py` | the golden.py diff is non-empty |
| SC1 / EVAL-01 | committed set loads; `n_answer >= 30` (or the recorded actual n), clarify items >= 4, each category >= 4, ids unique, every row has `review` | `tests/test_golden_conversations.py::test_the_committed_set_covers_every_category` | `python -m pytest tests/test_golden_conversations.py::test_the_committed_set_covers_every_category -q` | a category has fewer than 4 items, or the file is missing |
| SC1 / EVAL-01 | committed gold pages exist and evidence terms are on them (PDF pages) | `tests/test_golden_conversations.py::test_the_committed_set_matches_the_book` (skips if `data/processed/ddia.pages.jsonl` is absent) | `python -m pytest tests/test_golden_conversations.py::test_the_committed_set_matches_the_book -q` | `verify()` returns a problem (printed page used, term not on page) |
| SC2 / EVAL-02 | all four arms present; each arm retrieves on its own query string (`off`=message, `oracle`=standalone, `concat`=previous question + message, `on`=rewrite) | `tests/test_conversation_experiment.py::test_each_arm_retrieves_on_its_own_query` | `python -m pytest tests/test_conversation_experiment.py::test_each_arm_retrieves_on_its_own_query -q` | the report lacks an arm, or an arm uses another arm's string |
| SC2 / EVAL-02 | identical teacher-forced history per arm (rewriter prompt contains the item's turns; the answer prompts share the same history block; no model-generated turns) | `tests/test_conversation_experiment.py::test_every_arm_sees_the_same_teacher_forced_history` | `python -m pytest tests/test_conversation_experiment.py::test_every_arm_sees_the_same_teacher_forced_history -q` | a spy sees two different histories for one item |
| SC2 / EVAL-02 | paired win/tie/loss sums to n; per-category table present; oracle gap closed prints `n/a` when the denominator is under 3 items | `tests/test_conversation_experiment.py::test_paired_counts_and_category_table` | `python -m pytest tests/test_conversation_experiment.py::test_paired_counts_and_category_table -q` | counts do not sum to n, a category is missing |
| SC2 / EVAL-02 | status counts and a fallback counted as a failure, not as off (rewriter raising -> `fallback`, fallback rate 1.0, retrieval on the raw message) | `tests/test_conversation_experiment.py::test_a_fallback_is_a_counted_failure` | `python -m pytest tests/test_conversation_experiment.py::test_a_fallback_is_a_counted_failure -q` | the fallback is reported as `skipped`/`off` or not counted |
| SC2 / EVAL-02 | clarify items scored apart (asked, named both candidates, false-clarify rate, `allow_clarify=False` never clarifies) and excluded from n | `tests/test_conversation_experiment.py::test_clarify_items_are_scored_apart` | `python -m pytest tests/test_conversation_experiment.py::test_clarify_items_are_scored_apart -q` | a clarify item enters the hit@5 mean, or two clarifies in a row are allowed |
| SC2 / EVAL-02 | answer scoring uses `judge_facts` (judge replies `{"results": [...]}`), an abstention is wrong, the two `on` slot variants share one retrieval trace | `tests/test_conversation_experiment.py::test_answers_are_scored_with_the_fact_checklist` | `python -m pytest tests/test_conversation_experiment.py::test_answers_are_scored_with_the_fact_checklist -q` | the holistic judge is called, or the slot variants retrieve twice |
| SC2 / EVAL-02 | unreachable rewriter or generator skips that arm with a printed note instead of recording failures | `tests/test_conversation_experiment.py::test_an_unreachable_model_skips_its_arm` | `python -m pytest tests/test_conversation_experiment.py::test_an_unreachable_model_skips_its_arm -q` | the report shows 100% fallbacks instead of "not run" |
| SC2 / EVAL-02 | offline smoke over a 3-item fixture writes `report.json` to `tmp_path` with all arms and paired counts, and nothing under `data/` or `runs/` | `tests/test_conversation_experiment.py::test_the_smoke_run_writes_a_complete_report` | `python -m pytest tests/test_conversation_experiment.py::test_the_smoke_run_writes_a_complete_report -q` | a key is missing, or a file lands outside `tmp_path` |
| SC3 / EVAL-03 | `evaluate_rule` over a table: n=30 net=3 fails (a), net=4 passes; n=37 band 8.11; n=40 band 8; a standalone loss fails (c); an altered regression or any rewriter call fails (d); 2/20 fallbacks passes (e), 3/20 fails; any `pending-human` fails (f) | `tests/test_conversation_experiment.py::test_the_rule_table` (parametrized) | `python -m pytest tests/test_conversation_experiment.py -k rule_table -q` | a verdict differs from the table |
| SC3 / EVAL-03 | the rule text in `docs/chat_memory_eval.md` is the first `## ` section, named "Shipping rule (committed before the first run)", and quotes the same constants as the code | `tests/test_conversation_experiment.py::test_the_results_file_starts_with_the_rule` | `python -m pytest tests/test_conversation_experiment.py::test_the_results_file_starts_with_the_rule -q` | the heading is missing or not first, or a constant differs |
| SC3 / EVAL-03 | the `on` arm refuses to run unless the rule file is committed and clean | `tests/test_conversation_experiment.py::test_the_on_arm_needs_a_committed_rule` (monkeypatches `rule_is_committed`) | `python -m pytest tests/test_conversation_experiment.py::test_the_on_arm_needs_a_committed_rule -q` | the arm runs with an uncommitted rule |
| SC3 / EVAL-03 | commit order: the first commit of the file holds the rule and no results; a later commit adds results | shell, no test | `first=$(git log --reverse --format=%H -- docs/chat_memory_eval.md \| head -1); test -n "$first" && test "$(git show "$first":docs/chat_memory_eval.md \| grep -c '^## Results')" = 0 && test "$(git log --format=%H -- docs/chat_memory_eval.md \| wc -l)" -ge 2 && echo rule-first` | prints nothing: the rule and the results arrived in one commit, or there is a single commit |
| SC4 / EVAL-03 | the `RAG_REWRITE` default equals the decision line in the results file (`Decision: ships off` / `ships on`), through the Phase 3 `spied_settings` helper | `tests/test_conversation_experiment.py::test_the_default_matches_the_recorded_decision` | `python -m pytest tests/test_conversation_experiment.py::test_the_default_matches_the_recorded_decision -q` | the default disagrees with the recorded decision |
| SC4 / EVAL-03 | the results file records the chosen rewriter, its p50/p95, the slot decision (or "unmeasured") and the judge/rewriter-identity flag | `tests/test_conversation_experiment.py::test_the_results_file_records_every_decision` | `python -m pytest tests/test_conversation_experiment.py::test_the_results_file_records_every_decision -q` | a required line is missing |
| SC5 / EVAL-03 | regression arm: 37 first-turn questions make zero rewriter calls and return the same context chunk ids as `off` (fixture-sized offline) | `tests/test_conversation_experiment.py::test_the_regression_arm_matches_off_with_no_rewriter_call` | `python -m pytest tests/test_conversation_experiment.py::test_the_regression_arm_matches_off_with_no_rewriter_call -q` | any rewriter call, or any chunk-id list differs |
| SC5 / EVAL-03 | the regression detector can fail (gate patched to always fire -> reported as not identical) | `tests/test_conversation_experiment.py::test_the_regression_arm_detects_a_rewriter_call` | `python -m pytest tests/test_conversation_experiment.py::test_the_regression_arm_detects_a_rewriter_call -q` | the detector passes with a forced rewriter call |
| SC5 (live) | the real regression arm and the single-turn invariant are unchanged | live commands, outside pytest | `python -m rag.experiments.conversation --regression-only` (prints `37/37 identical, rewriter calls 0`) and `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` (hit@5 0.865, mrr 0.663) | counts differ or the invariant moves |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_golden_conversations.py tests/test_conversation_experiment.py -q`
- **Per wave merge:** the two modules above plus the Phase 3 modules this phase imports (`tests/test_rewrite.py`, `tests/test_rewrite_api.py`)
- **Phase gate:** `python -m pytest tests -q` (green against the Phase 3 baseline), `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` (hit@5 0.865, mrr 0.663), `python -m rag.common.llm_check ollama:qwen2.5:7b` and, if the tunnel is up, `python -m rag.common.llm_check`; output saved under `.planning/runs/<id>/`. Never run these inside this research task.

### Wave 0 Gaps
- [ ] Contract check: a one-line `python -c` that imports every Phase 1-3 symbol listed in "Phase 1-3 symbols" and halts on a mismatch; record `P4_BASE=<40 hex>` (HEAD before any Phase 4 code commit) in the first SUMMARY so later plans can check `rag/observe/golden.py` unchanged with `git diff --quiet "$P4_BASE" -- rag/observe/golden.py`
- [ ] `tests/test_golden_conversations.py` (new) - EVAL-01
- [ ] `tests/test_conversation_experiment.py` (new) - EVAL-02, EVAL-03; module-level helpers: tiny `PAGES`/`chunkset` fixture, `make_item(...)`, `scripted_rewriter(replies)` (a `FakeLLM` keyed on the text after `Last message: `), `fake_judge(...)` copied from `tests/test_about_experiment.py:13-18`, and a spy counting rewriter calls
- [ ] No framework install and no `conftest.py` needed (project rule: add one only when two modules need the same fixture)

## Security Domain

`security_enforcement` is enabled (`.planning/config.json`: `"security_enforcement": true`, `"security_asvs_level": 1`). The phase adds an offline evaluation script and committed data, no route, no auth and no upload path, so the surface is small.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | n/a (no route, no login) |
| V3 Session Management | no | n/a |
| V4 Access Control | no | The experiment must not import `rag/api` or touch `data/uploads/`; owner scoping is not exercised |
| V5 Input Validation | yes | Loader rejects unknown keys, bad types, bad pages, duplicate ids with `ValueError`; JSON read with `json.loads`; no `eval`; CLI paths are the operator's own |
| V6 Cryptography | no | none used; do not hand-roll hashing (git sha comes from `git`) |
| V7 Error Handling/Logging | yes | Library code logs counts and reason codes, never item text or exception text into a committed file; `except Exception` only at the preflight boundary, logging the class name (CONVENTIONS) |
| V14 Configuration | yes | Rewriter built with `cache_dir=None`; no key in committed files; `.env` never read; `.env.example` gets no value |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection through a golden item's prior-turn text | Tampering | Items are authored, public-book content; the rewriter still receives them only through `render_block` (neutralized), same path as the service |
| Secrets or personal data in committed golden/results files | Information disclosure | No email address (hook blocks it), no hostname/IP of the model tunnel in `docs/chat_memory_eval.md` (record the rewriter spec string only) |
| Subprocess for `git` | Tampering | `subprocess.run([...], check=False)` with an argv list, no shell, fixed arguments |
| Report path built from a CLI `--name` | Tampering | Default is `runs/conversation/<UTC timestamp>`; reject names containing a path separator or `..` |
| Disk cache retaining text | Information disclosure | Not an upload path, but keep `cache_dir=None` for the rewriter so no derived text outlives a run |
| Draft rows mistaken for reviewed gold | Tampering | `review` field is validated and rule (f) reads it; `MULTITURN_REVIEW.md` lists every `pending-human` id |

## Project Constraints (from CLAUDE.md)

- Do not edit `SYSTEM_PROMPT` in `rag/query/prompt.py`; single-turn prompts byte-identical; the experiment constructs `RagPipeline(..., subject="book")` so the book prompt is used unchanged.
- PDF page numbers everywhere (DDIA printed + 22).
- Gaps under about 8 points are noise on the 37 answerable questions; one question is 2.7 points.
- Per-question fact checklist (`judge_facts`) and strict evidence-aware relevance only; never the holistic correctness judge or page-overlap-only relevance.
- Never use the LLM disk cache for uploaded documents (`get_llm(spec, cache_dir=None)`); this experiment does not use uploads and still builds the rewriter uncached.
- Security conventions (owner from `current_owner`, 404 not 403, `Scope.owner` in the store, `textContent`, chunk id qualification, `StreamGuard`) are not exercised by this phase; do not import `rag/api`.
- Typing: `typing` generics (`Optional`, `List`), no `|` unions, no `from __future__ import annotations`; absolute imports from `rag`; lines at most 120 characters; double quotes; module logger `logging.getLogger("rag.<area>")`; `print()` only in the experiment's CLI table output.
- Commands: tests with `python -m pytest tests -q`; retrieval invariant `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` (hit@5 0.865, mrr 0.663); model check `python -m rag.common.llm_check`.
- Never name `rag/common/llm.py` or `tests/test_vllm.py` in a command or search; never glob `tests/` or `rag/common/`; never read `.env`; commit messages via `git commit -F <file>`; run multiprocessing-using scripts from a file (none here); timing-sensitive tests wait on a condition, not a fixed sleep (this phase has none: the rewriter is a fake).
- Do not push or open a PR; the flow run owns `flow/chat-memory`; GSD owns planning and execution.
- Keep `interview/` notes honest - Phase 5 relabels them, not this phase.

## Plan outline suggested to the planner (order matters for EVAL-03)

1. **Wave 0 / Plan 04-01:** contract check + `P4_BASE`; `rag/observe/golden_conversations.py` and `tests/test_golden_conversations.py` (loader only; tiny fixtures; committed-file tests marked to pass once the file exists).
2. **Plan 04-02 (can run in parallel with 04-01, different files):** commit FIRST the rule: `docs/chat_memory_eval.md` containing only `## Shipping rule (committed before the first run)` (draft text above) and the matching module docstring in `rag/experiments/conversation.py`; THEN the pure experiment core, `evaluate_rule`, `rule_is_committed()`, `--check-set`, and `tests/test_conversation_experiment.py`.
3. **Plan 04-03:** author `data/golden/ddia_conversations.jsonl` and `data/golden/MULTITURN_REVIEW.md` (all rows `pending-human`), run `--check-set` (off and oracle only) and record the baseline-miss count; freeze by committing.
4. **Plan 04-04:** preflight Ollama and the tunnel; the scored run(s) (qwen; gpt-oss comparison retrieval-only if the tunnel is up; `--answers` if up; `--repeats 3`); write the numbers into `docs/chat_memory_eval.md` below the rule in a second commit; STATE.md blocker for any arm that could not run (D-14).
5. **Plan 04-05 (conditional):** apply the decision. If the rule says on (only possible with every row `approved`): flip the default in `build_default_service`, `.env.example`, update the Phase 3 default test and add `test_the_default_matches_the_recorded_decision`; if off: still add that test asserting off, no production code change.
6. **Gate:** full suite, retrieval invariant, regression arm live, prohibition checks (`git diff --quiet "$P4_BASE" -- rag/observe/golden.py rag/query/prompt.py rag/query/rewrite.py rag/query/history.py`).

## Sources

### Primary (HIGH confidence) - read this session
- `rag/experiments/retrieval.py`, `rag/experiments/answer.py`, `rag/experiments/about.py` - experiment shape, flags, report writing
- `rag/observe/golden.py`, `rag/observe/golden_tools/verify_golden.py` - loader pattern, `verify`
- `rag/observe/retrieval_quality/metrics.py`, `run_eval.py`, `rag/observe/generation_quality/answers.py`, `judge.py` - scoring
- `rag/query/pipeline.py`, `rag/query/configs.py`, `rag/common/trace.py`, `rag/ingestion/index.py`, `rag/ingestion/chunking/base.py`, `rag/common/llm_check.py`, `rag/api/main.py` (build_default_service)
- `tests/test_about_experiment.py`, `tests/test_retrieval.py` (fixtures), `.planning/codebase/TESTING.md`
- `data/golden/ddia_questions.jsonl` (counted and listed), `question_writer_rules.md`, `BATCHES.md`
- `docs/models.md`, `rag/README.md` Step 6, `.env.example` (line 15, `RAG_*` names)
- Python computation of the band arithmetic, sign test table and power simulation (scratchpad `stats.py`, `stats2.py`)

### Secondary (MEDIUM confidence) - planned contracts
- `.planning/phases/03-rewrite-clarify-and-topic-switch/03-01-PLAN.md`, `03-03-PLAN.md`, `03-04-PLAN.md`, `03-06-PLAN.md` (grep); `.planning/phases/01-safety-net-and-prompt-seam/01-03-PLAN.md`, `01-05-PLAN.md`
- `.planning/research/PITFALLS.md` (Pitfalls 7, 10, 11, 14, 16), `.planning/research/STACK.md`, `.planning/STATE.md`, `REQUIREMENTS.md`, `ROADMAP.md`

### Tertiary (LOW confidence)
- Runtime estimates and Ollama sampling defaults (not measured here; no live model was run)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all reuse targets read in this session; no new dependency
- Architecture: HIGH for the pure-core/offline design; MEDIUM for Phase 3 call contracts (planned)
- Statistics: HIGH - exact arithmetic and enumeration computed here; power by simulation under an independence assumption
- Pitfalls: HIGH for repo-derived ones; MEDIUM for live-model behaviour (rewriter false rejections, stability)

**Research date:** 2026-10-22
**Valid until:** 2026-11-21 for the repo facts; re-run the Wave 0 contract check after Phase 3 executes, since the Phase 1-3 symbols are plans, not code
