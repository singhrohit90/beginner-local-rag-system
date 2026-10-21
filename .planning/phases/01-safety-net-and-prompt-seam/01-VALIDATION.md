---
phase: "01"
slug: "safety-net-and-prompt-seam"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-21"
---

# Phase 01 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3, plain `assert`, no config file, no `conftest.py` |
| **Config file** | none (defaults) |
| **Quick run command** | `python -m pytest tests/test_prompt_snapshot.py tests/test_history.py -q` |
| **Full suite command** | `python -m pytest tests -q` (about 3 min quiet, about 10 when shared) |
| **Estimated runtime** | ~10 seconds quick; ~180-600 seconds full |

Collected baseline: 593 tests (`python -m pytest tests --collect-only -q`). Affected-file run before any edit: `python -m pytest tests/test_generation.py tests/test_security.py tests/test_stream_api.py -q` -> 64 passed in 10.68 s.

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_prompt_snapshot.py tests/test_history.py -q`
- **After every plan wave:** Run `python -m pytest tests/test_prompt_snapshot.py tests/test_history.py tests/test_generation.py tests/test_security.py tests/test_stream_api.py -q`
- **Before `/gsd-verify-work`:** Full suite must be green, plus `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` printing hit@5 0.865 / mrr 0.663; both outputs pasted into SUMMARY.md and VERIFICATION.md
- **Max feedback latency:** 15 seconds (quick command)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-xx | 01 | 1 | PRMT-02 (SC1) | — | N/A | snapshot | `python -m pytest tests/test_prompt_snapshot.py -q` | ❌ W0 | ⬜ pending |
| 01-01-xx | 01 | 1 | PRMT-02 (SC3) | — | N/A | command | `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` | ✅ | ⬜ pending |
| 01-02-xx | 02 | 1 | SC4 | — | N/A | doc check | `grep -n "Context window" docs/models.md` | ✅ | ⬜ pending |
| 01-03-xx | 03 | 2 | PRMT-02 (SC2) | — | empty block returns the old expression untouched | unit | `python -m pytest tests/test_prompt_snapshot.py -q -k "empty_history or history_block_position or pipeline"` | ❌ W0 | ⬜ pending |
| 01-04-xx | 04 | 2 | groundwork (PRMT-01/03/04) | T-01-xx | `neutralize` strips `[S n]`, newlines and flagged spans; withholds canary echo | unit | `python -m pytest tests/test_history.py -q` | ❌ W0 | ⬜ pending |
| 01-05-xx | 05 | 3 | PRMT-02 (SC3) | — | N/A | full | `python -m pytest tests -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

Task IDs above are placeholders until the planner assigns plan and task numbers; the planner must keep one automated command per task and the `fails_when` conditions below.

### Per-command failure conditions (`fails_when`)

| Command | `fails_when` |
|---------|--------------|
| `python -m pytest tests/test_prompt_snapshot.py -q` (before seam) | non-zero exit; any prompt byte differs from a committed file; a snapshot file or the digest manifest is missing; spotlight cases differ run to run (`_NONCE_KEY` not patched); a case contains `\r` |
| same, `-k empty_history` (after seam) | non-zero exit; builders called with `history_block=""` differ from the no-argument call or the snapshot |
| same, `-k history_block_position` | non-zero exit; the block is placed before the passages, after `Question:`, or dropped by a style |
| same, `-k pipeline` | non-zero exit; `answer`/`stream` do not forward the keyword; `stream` and `answer` disagree |
| `python -m pytest tests/test_history.py -q` | non-zero exit; `neutralize` output keeps a `[S n]`, a newline, a flagged span, or exceeds `max_words` plus marker; `render_block([])` returns anything but `""`; the block exceeds 400 words; the budget total exceeds `MODEL_CONTEXT_TOKENS` |
| `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` | the `semantic      weighted` row does not show 0.865 under hit@5 and 0.663 under mrr; `FileNotFoundError` for `data/processed/chunks`; an import error from `rag.query.pipeline` |
| `python -m pytest tests -q` | non-zero exit; any of the 593 baseline tests fails; the passed/skipped split differs from 591/2 for a reason other than OpenSearch being up |
| `grep -n "Context window" docs/models.md` | no matching line, or the paragraph has neither a number nor the dated "not read" sentence |

Proving each new test is real (project recipe): for the identity, position and pipeline tests run `git stash push -q -m phase1-seam-proof -- rag`, run the single test id (it must fail with a `TypeError` on the unknown keyword), then `git stash pop -q`. For the snapshot test, mutate one character of one snapshot file locally, confirm the test fails, restore it.

---

## Wave 0 Requirements

- [ ] `tests/test_prompt_snapshot.py` and `tests/snapshots/prompts/*` (24 case files + digest manifest) — covers SC1, extended for SC2
- [ ] `tests/test_history.py` — covers the groundwork and the worst-case budget test
- [ ] `rag/query/history.py` — does not exist yet
- Framework install: none.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `max_model_len` read from the live server | SC4 | Needs the PuTTY tunnel to `127.22.10.1:30007`; refused at research time | Run the one-off command in RESEARCH.md "Code Examples"; if refused, record "not read on <date>: tunnel down" in `docs/models.md` and a blocker in STATE.md |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
