---
phase: "03"
slug: "rewrite-clarify-and-topic-switch"
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-22"
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. The full per-criterion test map (test names, commands and `fails_when`) is in `03-RESEARCH.md` §"Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8, `fastapi.testclient.TestClient`, `FakeLLM`; no config file |
| **Config file** | none |
| **Quick run command** | `python -m pytest tests/test_rewrite.py -q` |
| **Full suite command** | `python -m pytest tests -q` |
| **Estimated runtime** | ~10 seconds quick; ~180-600 seconds full |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_rewrite.py tests/test_rewrite_api.py -q`
- **After every plan wave:** Run `python -m pytest tests/test_rewrite.py tests/test_rewrite_api.py tests/test_conversations.py tests/test_api.py tests/test_stream_api.py -q`
- **Before `/gsd-verify-work`:** `python -m pytest tests -q` green; retrieval invariant hit@5 0.865 / mrr 0.663 unchanged
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Req | Success criterion | Automated Command | File Exists | Status |
|-----|-------------------|-------------------|-------------|--------|
| RWR-01 | SC1 gate, no call on turn 1, standalone unchanged, ships off | `python -m pytest tests/test_rewrite.py tests/test_rewrite_api.py -q -k "gate or first_turn or marker_free or exactly_one or switch_off or ships_the_switch_off or only_when_on"` | ❌ W0 | ⬜ pending |
| RWR-02 | SC2 retrieval on the rewrite, both texts recorded; SC3 visible fallback before any SSE byte | `python -m pytest tests/test_rewrite.py tests/test_rewrite_api.py -q -k "runs_on_the_rewrite or record_both_texts or same_rewrite or visible_fallback or real_ollama or request_for_a_rewrite or oversized or 250"` | ❌ W0 | ⬜ pending |
| RWR-03 | SC4 one clarification, normal shape, never two in a row | `python -m pytest tests/test_rewrite.py tests/test_rewrite_api.py -q -k "clarifying_question_uses or stored_with_its_kind or not_clarified or with_a_link or only_known"` | ❌ W0 | ⬜ pending |
| RWR-04 | SC5 topic switch and the four bad rewrites | `python -m pytest tests/test_rewrite.py tests/test_rewrite_api.py -q -k "clean_history or new_topic_uses or bad_rewrite or four_named or known_limit"` | ❌ W0 | ⬜ pending |

`fails_when` for every command: non-zero exit, or the per-test condition listed in `03-RESEARCH.md`.

---

## Wave 0 Requirements

- [ ] Phases 1 and 2 executed (history helpers, conversation store, `_retrieve` wiring) — prerequisite
- [ ] `tests/test_rewrite.py` — pure gate, parser, guards
- [ ] `tests/test_rewrite_api.py` — service and route behaviour
- [ ] Seed helper for `kind: "clarify"` and `topic_start` turns
- Framework install: none.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Draft multi-turn golden items are human-written | (D-15, feeds EVAL-01) | Authorship cannot be automated | Owner reviews `data/golden/conversations_draft.jsonl` rows marked for review before Phase 4 loads them |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
