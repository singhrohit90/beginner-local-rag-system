---
phase: "04"
slug: "multi-turn-evaluation-and-the-default-decision"
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-22"
---

# Phase 04 — Validation Strategy

> Per-phase validation contract. The full per-criterion test map (test names, commands and `fails_when`) is in `04-RESEARCH.md` §"Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8, `HashingEmbedder`, `FakeLLM`, tiny-corpus fixture; no config file |
| **Config file** | none |
| **Quick run command** | `python -m pytest tests/test_golden_conversations.py tests/test_conversation_experiment.py -q` |
| **Full suite command** | `python -m pytest tests -q` |
| **Estimated runtime** | ~15 seconds quick; ~180-600 seconds full |

---

## Sampling Rate

- **After every task commit:** Run the quick command
- **After every plan wave:** quick command plus `tests/test_rewrite.py tests/test_retrieval.py`
- **Before `/gsd-verify-work`:** full suite green; `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` prints hit@5 0.865 / mrr 0.663; `python -m rag.experiments.conversation --regression-only` prints `37/37 identical, rewriter calls 0`
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Req | Success criterion | Automated Command | File Exists | Status |
|-----|-------------------|-------------------|-------------|--------|
| EVAL-01 | SC1 set, loader, `load_golden` untouched | `python -m pytest tests/test_golden_conversations.py -q` | ❌ W0 | ⬜ pending |
| EVAL-02 | SC2 four arms, teacher-forced history, paired and category tables, fallback counted, clarify apart, offline smoke | `python -m pytest tests/test_conversation_experiment.py -q -k "own_query or teacher_for or paired_counts or counted_failure or scored_apart or fact_checklist or skips_its_arm or smoke_run"` | ❌ W0 | ⬜ pending |
| EVAL-03 | SC3 rule committed first and evaluated exactly; SC4 default follows the decision; SC5 regression arm | `python -m pytest tests/test_conversation_experiment.py -q -k "rule or committed_rule or recorded_decision or every_decision or regression_arm"` plus the `git log` commit-order check in RESEARCH | ❌ W0 | ⬜ pending |

`fails_when` for every command: non-zero exit, or the per-test condition in `04-RESEARCH.md`.

---

## Wave 0 Requirements

- [ ] Phases 1-3 executed; contract check imports every Phase 1-3 symbol and records `P4_BASE`
- [ ] `tests/test_golden_conversations.py` — EVAL-01
- [ ] `tests/test_conversation_experiment.py` — EVAL-02, EVAL-03
- Framework install: none.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Golden rows reviewed by the owner | EVAL-01, EVAL-03 (f) | Human authorship | Owner changes `"review": "pending-human"` to `"approved"` after reading each row; until then the rule keeps the default off |
| Live arms (qwen rewriter, gpt-oss comparison, `--answers`) | EVAL-02 | Need Ollama and the PuTTY tunnel | Run `python -m rag.experiments.conversation` with the models up; record skipped arms if not |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
