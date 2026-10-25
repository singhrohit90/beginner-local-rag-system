---
phase: 04-multi-turn-evaluation-and-the-default-decision
verified: 2026-10-25T19:01:00Z
status: human_needed
score: 13/15 must-haves verified
covered_files:
  - .planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-01-PLAN.md
  - .planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-01-SUMMARY.md
  - .planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-02-PLAN.md
  - .planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-02-SUMMARY.md
  - .planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-03-PLAN.md
  - .planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-03-SUMMARY.md
  - .planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-04-PLAN.md
  - .planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-04-SUMMARY.md
  - .planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-05-PLAN.md
  - .planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-05-SUMMARY.md
  - .planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-06-PLAN.md
  - .planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-06-SUMMARY.md
  - .planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-07-PLAN.md
  - .planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-07-SUMMARY.md
  - .planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-08-PLAN.md
  - .planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-08-SUMMARY.md
  - .planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-09-PLAN.md
  - .planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-09-SUMMARY.md
  - .planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-10-PLAN.md
  - .planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-10-SUMMARY.md
  - data/golden/MULTITURN_REVIEW.md
  - data/golden/ddia_conversations.jsonl
  - docs/chat_memory_eval.md
  - rag/experiments/conversation.py
  - rag/observe/golden_conversations.py
  - tests/test_conversation_experiment.py
  - tests/test_golden_conversations.py
covered_digest: "v3:sha256:cf6b4df71683ed950058560af2ffe78aeba117e4564b5f131b22a6edcb56f79a"
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Owner review of the multi-turn golden set: read every row of data/golden/ddia_conversations.jsonl (34 rows, listed in data/golden/MULTITURN_REVIEW.md), correct or replace any standalone question, turn or must_contain/must_not_contain term that is not what a human would write, then change review to approved."
    expected: "Every row is review approved; python -m rag.observe.golden_conversations data/golden/ddia_conversations.jsonl --pages data/processed/ddia.pages.jsonl still prints problems 0; if any row text changed, rerun --check-set, the scored run and --results and append the new Results."
    why_human: "ROADMAP SC1 requires a human-written standalone question per item. All 34 rows are executor drafts marked pending-human (D-03). Only the owner can supply human authorship; code cannot. Rule condition (f) keeps the default off until this is done."
  - test: "With the PuTTY tunnel and Ollama up, rerun python -m rag.experiments.conversation --repeats 3 --answers --name <new> and the retrieval-only comparison REMOTE_REASONING_EFFORT=low python -m rag.experiments.conversation --rewriter vllm:/models/gpt-oss-20b --arms off,on --name <new-gptoss>, then python -m rag.experiments.conversation --results runs/conversation/<new> --compare runs/conversation/<new-gptoss>."
    expected: "The Results record a measured Question slot (rewritten question or original message, not unmeasured), a Rewriter chosen line from a measured comparison (not 'qwen by default, not compared'), the fact-checklist answer table, and the judge/rewriter same-model flag; tests/test_conversation_experiment.py stays green."
    why_human: "ROADMAP SC4 says the rewriter model and the question slot are decided from recorded latency and quality numbers. The scored run on 2026-10-25 had the vLLM tunnel down, so the answers arm and the gpt-oss comparison did not run; both decisions fell back to the pre-registered defaults (D-10, D-11, D-14). Running them needs the external model server, which the verifier must not call."
  - test: "Review the seven judgment-tier prohibitions (04-01 no item text in errors; 04-03 and 04-04 no arm over the golden set in those plans; 04-05 no on arm or rewording after a rewriter result; 04-06 no glob of tests/; 04-08 and 04-10 no fixed sleep during live runs) and confirm or reject the verifier's non-authoritative verdict."
    expected: "Each prohibition held (verifier evidence in the Prohibitions table below)."
    why_human: "Judgment-tier prohibitions are never silently passed; the verifier's verdict on them is non-authoritative."
---

# Phase 4: Multi-turn evaluation and the default decision Verification Report

**Phase Goal:** As a system owner, I want to measure rewriting on and off against a multi-turn golden set, so that rewriting becomes the default only when it shows a gain outside the noise band and the numbers are recorded either way.
**Mode:** mvp (user-story format valid)
**Verified:** 2026-10-25T19:01:00Z
**Status:** human_needed
**Re-verification:** No (initial verification)

## User Flow Coverage

| Step of the story | Expected | Evidence in codebase | Status |
|---|---|---|---|
| Owner has a multi-turn golden set | 34 rows in all five categories, own loader, page check clean | `data/golden/ddia_conversations.jsonl` (answer 30, clarify 4; pronoun 10, constraint 6, topic_switch 6, ambiguous 4, standalone 8); `python -m rag.observe.golden_conversations ... --pages data/processed/ddia.pages.jsonl` printed `problems 0` (run by verifier) | VERIFIED (structure); human authorship pending |
| Owner measures rewriting on and off | One command, arms off/on/oracle/concat on teacher-forced histories, strict evidence-aware scoring, paired and per-category tables | `rag/experiments/conversation.py` `run_arms`, `score_query` (strict_trace + score_hits), `summarise`, `render_results`; 79 tests pass (run by verifier) | VERIFIED |
| Rule decided before the numbers | Rule commit holds only the rule and precedes every scored run | `9baf0f3` adds only `docs/chat_memory_eval.md` (30 lines, no `## Results`); results commit `e114e36` is 84 insertions, 0 deletions; report meta head `eb3f61a` (2026-10-26 00:57 +0800) is after the rule commit (2026-10-25 21:38 +0800); `--check-rule` exit 0 (run by verifier) | VERIFIED |
| Numbers recorded either way | Committed Results with the Decision line | `docs/chat_memory_eval.md` `## Results`, ending `Decision: ships off (failed: a, c, f; provisional: items pending human review)`; values match `runs/conversation/p4-qwen/report.json` (arms, latency 2979.0/3342.9 over 28, rule checks a to f) | VERIFIED |
| Default follows the rule | Off, because the rule failed | `rag/api/main.py:173` `setting("RAG_REWRITE", "") == "1"`; `rag/api/` unchanged since P4_BASE; `test_the_default_matches_the_recorded_decision` passes | VERIFIED |

The `[outcome]` clause (default only on a gain outside the band, numbers recorded either way) is observably true. The two open items concern SC1's "human-written" wording and SC4's "decided from recorded numbers" for the rewriter model and question slot.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| SC1 | Multi-turn golden set under `data/golden/` with pronoun follow-up, topic switch, ambiguous follow-up and standalone-in-conversation items, fixed prior turns, a human-written standalone question and PDF gold pages; own loader rejects unknown keys; `load_golden` unchanged | ? UNCERTAIN | Structure, loader and invariants VERIFIED: `rag/observe/golden_conversations.py` (unknown/missing key rejection at lines 175/178, duplicate ids at 242); `git diff --quiet 3744d3c HEAD -- rag/observe/golden.py data/golden/ddia_questions.jsonl data/golden/about_questions.jsonl` clean; 30 answer rows reuse source gold_pages/key_facts/evidence_terms verbatim from 30 distinct source ids (verifier script, 0 mismatches). Not verified: every standalone is an executor draft, `review` is `pending-human` on 34 of 34 rows, so "human-written" is not yet true. Routed to human verification item 1. |
| SC2 | One command under `rag/experiments/` prints off, on and oracle arms, retrieval scored on the rewritten query and the answer on the last turn with the fact-checklist judge, identical teacher-forced histories, paired win/tie/loss and per-category tables | ✓ VERIFIED | `run_arms` builds one `win = window(teacher_history(item))` per item and changes only the query string (lines 251-279); `on` retrieves on `effective_query` of the shipped `rewrite_question`; `_answer_item` uses `judge_facts` (line 774) with `history_block=` (line 766); tests `test_each_arm_retrieves_on_its_own_query`, `test_every_arm_sees_the_same_teacher_forced_history`, `test_answers_are_scored_with_the_fact_checklist`, `test_paired_counts_and_category_table` pass. Live answers were not produced (tunnel down); see SC4. |
| SC3 | Shipping rule (band recomputed for the set's size) committed before the first scored run; the run's numbers recorded in a committed file | ✓ VERIFIED | Rule commit `9baf0f3` holds only the doc, `band = max(8, 300 / n)`, no Results; `rule_status` shows committed, clean, unchanged, first commit has results no; Results committed in `e114e36` with no deletions. |
| SC4 | Default follows the rule (on only if the gain clears the band, else off with numbers recorded); the rewriter model and the question slot decided from the recorded latency and quality numbers | ? UNCERTAIN | Default part VERIFIED: gain 10.0 equals band 10.0 so (a) fails, (c) and (f) fail, Decision ships off, `RAG_REWRITE` default stays off, pinned by `test_the_default_matches_the_recorded_decision` and `test_the_rewriter_default_matches_the_recorded_choice`. Not met as worded: Results say `Rewriter chosen: ollama:qwen2.5:7b (qwen by default, not compared)` and `Question slot: rewritten question (unmeasured: answers not run)`; neither decision came from measured comparison numbers. This is the pre-registered D-10/D-11/D-14 fallback for a down tunnel, recorded as a STATE.md blocker (line 89). Routed to human verification item 2. |
| SC5 | Replaying the 37 answerable questions as first turns with rewriting on gives the same retrieval as off; hit@5 0.865 / mrr 0.663 unchanged | ✓ VERIFIED | `report.json` regression: n 37, identical 37, rewriter_calls 0, off hit@5 0.865, mrr 0.663; independent gate run `phase-04-gate/regression.txt` and `retrieval.txt` (semantic weighted hit@5 0.865, mrr 0.663); `rag/query`, `rag/ingestion` unchanged since P4_BASE; offline tests `test_the_regression_arm_matches_off_with_no_rewriter_call` and `test_the_regression_arm_detects_a_rewriter_call` pass. |
| P01 | 04-01 must-haves (contract ok, P4_BASE, loader schema, edges, to_question, page-check CLI) | ✓ VERIFIED | SUMMARY has `contract ok` and `P4_BASE=3744d3c...`; loader imports GoldQuestion, verify, history caps (key links present); CLI output format confirmed by verifier run. |
| P02 | 04-02 rule committed alone first, D-10/D-11/D-12 rules in the same section, no address or URL | ✓ VERIFIED | First line is the rule heading; `git show --stat 9baf0f3` one file; grep for URL/IP/email in the doc found none. |
| P03 | 04-03 experiment core (arms, strict scoring, false clarify, fallback, clarify items, regression, rule guard, preflight, report meta) | ✓ VERIFIED | Code read (lines 137-426); report meta keys match; `test_the_on_arm_needs_a_committed_rule`, `test_rule_status_reads_git`, `test_an_unreachable_model_skips_its_arm` pass; subprocess uses argv lists. |
| P04 | 04-04 statistics, evaluate_rule, answers arm, choose_rewriter, render_results | ✓ VERIFIED | `test_the_rule_table` (n30 net3 fails a, band edges, fallback 2/20 vs 3/20), `test_the_sign_test_and_percentiles`, `test_the_rewriter_choice_table`, `test_the_results_text_holds_no_model_text` pass; no scipy; all `get_llm` calls pass `cache_dir=None`. |
| P05 | 04-05 frozen golden set and review file | ✓ VERIFIED | 30 answer / 4 clarify, >= 4 per category, all pending-human, page check problems 0, `discriminating 8/16` in MULTITURN_REVIEW.md (meets half); set last changed in `dbae052`, before the scored run. |
| P06 | 04-06 loader tests | ✓ VERIFIED | `tests/test_golden_conversations.py` passes (in the 79). |
| P07 | 04-07 experiment tests | ✓ VERIFIED | All named tests present and pass; reuse `fake_judge` and compare doc constants. |
| P08 | 04-08 live run, Results below the rule, STATE.md blocker | ✓ VERIFIED | `runs/conversation/p4-qwen/report.json` exists with decision, summary, regression, repeats; Results numbers match the report; STATE.md line 89 lists answers and gpt-oss comparison as not run with rerun commands. Results not re-rendered by the verifier (command outside the allowed list); cross-checked field by field instead. |
| P09 | 04-09 default and rewriter-choice tests; no production change on ships off | ✓ VERIFIED | Three tests present and passing; `git diff 3744d3c HEAD -- rag/api .env.example` empty. |
| P10 | 04-10 gate: full suite, invariant, rule-first, phase checks, STATE.md baseline and owner flag | ✓ VERIFIED | `phase-04-gate/pytest.txt` `917 passed, 2 skipped`, collect 919; `phase-checks.txt` rule-first, only two rag files changed, prompt fingerprint b69624ed9d1a5781; STATE.md lines 69, 88, 90. The full suite was not re-run by the verifier (saved output only). |

**Score:** 13/15 truths verified (0 present, behavior-unverified; 2 uncertain, routed to human)

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `rag/observe/golden_conversations.py` | Loader, validation, adapter, page CLI | ✓ VERIFIED | 282 lines, imported by the experiment and tests |
| `docs/chat_memory_eval.md` | Rule then Results then Decision line | ✓ VERIFIED | 114 lines, two commits in rule-first order |
| `rag/experiments/conversation.py` | Arms, stats, rule, answers, results | ✓ VERIFIED | 1187 lines, `__main__` entry, run live once |
| `data/golden/ddia_conversations.jsonl` | Frozen set, pending-human | ✓ VERIFIED (review pending) | 34 rows |
| `data/golden/MULTITURN_REVIEW.md` | Per-row review state, baseline | ✓ VERIFIED | 67 lines |
| `tests/test_golden_conversations.py`, `tests/test_conversation_experiment.py` | Offline tests | ✓ VERIFIED | 79 passed in 6.27 s |
| `.planning/STATE.md` | Baseline, decision, owner flag, blocker | ✓ VERIFIED | Lines 69, 86-90 |

### Key Link Verification

| From | To | Via | Status |
|---|---|---|---|
| conversation.py | rag/query/rewrite.py | `rewrite_question(rewriter, message, win` (line 175) | WIRED |
| conversation.py | metrics.py | `strict_trace(` (line 154) | WIRED |
| conversation.py | docs/chat_memory_eval.md | `RULE_HEADING`, `rule_status` | WIRED |
| conversation.py | golden_conversations.py | `load_conversations(` (line 1100) | WIRED |
| conversation.py | judge.py | `judge_facts(judge, ` (line 774) | WIRED |
| conversation.py | pipeline.py | `history_block=` (line 766) | WIRED |
| golden_conversations.py | golden.py, verify_golden.py, history.py | imports lines 23-25 | WIRED |
| test_conversation_experiment.py | test_rewrite_api.py, test_about_experiment.py | `spied_settings`, `fake_judge` imports | WIRED |
| STATE.md | docs/chat_memory_eval.md | `[Phase 4]` decision line | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real data | Status |
|---|---|---|---|---|
| Results in `docs/chat_memory_eval.md` | arm table, latency, rule checks | `runs/conversation/p4-qwen/report.json` from the live qwen run | Yes; values match field by field | ✓ FLOWING |
| Answers section | fact-checklist results | generator unreachable | No; "unmeasured" | ⚠️ STATIC (external service down; human item 2) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Phase 4 tests | `python -m pytest tests/test_conversation_experiment.py tests/test_golden_conversations.py -q` | 79 passed in 6.27s | ✓ PASS |
| Rule guard | `python -m rag.experiments.conversation --check-rule` | committed yes; clean yes; unchanged yes; first commit has results no; exit 0 | ✓ PASS |
| Golden page check | `python -m rag.observe.golden_conversations data/golden/ddia_conversations.jsonl --pages data/processed/ddia.pages.jsonl` | conversations 34 (answer 30, clarify 4), problems 0, exit 0 | ✓ PASS |
| Phase scope | `git diff --stat 3744d3c HEAD -- rag/ requirements-rag.txt data/golden/ docs/ .env.example` | only the 5 expected files | ✓ PASS |
| Full suite, retrieval invariant, regression-only | not run (outside the allowed commands; regression-only preflights a live rewriter) | saved gate outputs used | ? SKIP |

### Probe Execution

No probes declared; step not applicable.

### Requirements Coverage

| Requirement | Source Plan | Status | Evidence |
|---|---|---|---|
| EVAL-01 | 04-01, 04-05, 04-06, 04-10 | ? NEEDS HUMAN | Set, loader and tests in place; "human-written standalone" awaits owner review |
| EVAL-02 | 04-03, 04-04, 04-07, 04-08, 04-10 | ✓ SATISFIED | Experiment scores retrieval on the rewritten query and answers with judge_facts (offline-tested); live answers pending tunnel |
| EVAL-03 | 04-02 to 04-05, 04-07 to 04-10 | ✓ SATISFIED | Rule committed first, ships off with numbers recorded, default pinned by test |

No orphaned requirements.

### Prohibitions

Test-tier prohibitions with enforcement found: golden.py and single-turn files unchanged (git diff), rule commit single-file and no Results, no URL/IP/email in committed doc and golden files (grep), no scipy, no `rag.api` import in experiment or loader, `cache_dir=None` on every `get_llm` (experiment lines 1092, 1122, 1152, 1153; `rag/api/main.py` 170, 175), no production change on ships off, rule section unchanged. All held.

Judgment-tier prohibitions (non-authoritative verdict, human review recommended):

| Plan | Prohibition | Verifier verdict |
|---|---|---|
| 04-01 | No item text in exception messages or logs | Appears held: all `ValueError` messages name path, line, id and key only |
| 04-03, 04-04 | No arm over the golden set in these plans | Appears held: the set was first committed in `ba6900e`, after both plans' code commits |
| 04-05 | No on arm or rewording after a rewriter result | Appears held: set frozen in `dbae052` and unchanged since; first on run at head `eb3f61a` |
| 04-06 | No glob of tests/ | Cannot verify from the repo |
| 04-08, 04-10 | No fixed sleep during live runs | Cannot verify from the repo |

### Anti-Patterns Found

No TBD, FIXME, XXX, TODO, HACK or PLACEHOLDER markers in the phase files.

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| docs/chat_memory_eval.md | Results | Clarify items: 4, asked 0 | ℹ️ Info | The rewriter never asked a clarifying question on the four ambiguous items; reported, not gating |
| report.json (gitignored) | meta.golden | Absolute path into `.claude/worktrees/04-08/` | ℹ️ Info | Run was made from a worktree; no effect on the committed file |
| phase-04-gate/regression.txt | unrelated variant | rewritten 16 vs 17 in the committed Results | ℹ️ Info | Non-gating variant, qwen nondeterminism |

### Human Verification Required

### 1. Owner review of the multi-turn golden set

**Test:** Read every row of `data/golden/ddia_conversations.jsonl` (34 rows, listed in `data/golden/MULTITURN_REVIEW.md`), correct or replace any standalone question, turn or must_contain/must_not_contain term that is not what a human would write, then change `review` to `approved`.
**Expected:** Every row is `approved`; the page check still prints `problems 0`; if any row text changed, rerun `--check-set`, the scored run and `--results` and append the new Results.
**Why human:** ROADMAP SC1 requires a human-written standalone question per item. All 34 rows are executor drafts marked pending-human (D-03). Rule condition (f) keeps the default off until this is done.

### 2. Measure the question slot and the rewriter model with the tunnel up

**Test:** With the PuTTY tunnel and Ollama up, run `python -m rag.experiments.conversation --repeats 3 --answers --name <new>` and `REMOTE_REASONING_EFFORT=low python -m rag.experiments.conversation --rewriter vllm:/models/gpt-oss-20b --arms off,on --name <new-gptoss>`, then `python -m rag.experiments.conversation --results runs/conversation/<new> --compare runs/conversation/<new-gptoss>`.
**Expected:** The Results record a measured Question slot, a Rewriter chosen line from a measured comparison, the fact-checklist answer table, and the judge/rewriter same-model flag.
**Why human:** ROADMAP SC4 says both decisions come from recorded latency and quality numbers. The 2026-10-25 run had the vLLM tunnel down, so both fell back to the pre-registered defaults (D-10, D-11, D-14).

### 3. Judgment-tier prohibitions

**Test:** Review the seven judgment-tier prohibitions in the table above.
**Expected:** Each held.
**Why human:** The verifier's verdict on judgment-tier prohibitions is non-authoritative.

If the owner accepts the D-14 fallback as meeting SC4 for this milestone, an override can carry it:

```yaml
overrides:
  - must_have: "the rewriter model and the question slot in the answer prompt are decided from the recorded latency and quality numbers"
    reason: "vLLM tunnel down during the scored run; pre-registered D-10/D-11 fallback applied (qwen by default, not compared; rewritten question, unmeasured) and recorded as a STATE.md blocker with rerun commands"
    accepted_by: "{name}"
    accepted_at: "{ISO timestamp}"
```

### Gaps Summary

No code gaps. Every artifact exists, has real content and is wired, and the phase's outcome holds: the rule was committed alone before any scored run, the live qwen run's numbers are committed, the decision is ships off (a: gain 10.0 equals band 10.0; c: one standalone loss; f: 34 rows pending review), and the default stays off, pinned by a test. Two roadmap criteria are not met as worded, and code cannot meet them. SC1 needs the owner to review the golden rows. SC4 needs a rerun with the tunnel up to measure the question slot and the rewriter comparison. Phase 5 (chat page and docs) does not cover either, so neither is deferred.

---

_Verified: 2026-10-25T19:01:00Z_
_Verifier: Claude (gsd-verifier)_
