---
phase: "02"
slug: "conversation-store-and-memory-in-the-answer-prompt"
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-22"
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. The full test map (T1-T26, each with file, test name, command and `fails_when`) is in `02-RESEARCH.md` §"Validation Architecture"; this file is the sampling contract.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8, `fastapi.testclient.TestClient`; no config file, no `conftest.py` |
| **Config file** | none |
| **Quick run command** | `python -m pytest tests/test_conversations.py -q` |
| **Full suite command** | `python -m pytest tests -q` |
| **Estimated runtime** | ~15 seconds quick; ~180-600 seconds full |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_conversations.py -q`
- **After every plan wave:** Run `python -m pytest tests/test_conversations.py tests/test_api.py tests/test_stream_api.py tests/test_history.py tests/test_prompt_snapshot.py tests/test_stream_guard.py -q`
- **Before `/gsd-verify-work`:** `python -m pytest tests -q` green; `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` prints hit@5 0.865 / mrr 0.663
- **Max feedback latency:** 20 seconds (quick command)

---

## Per-Task Verification Map

| Req | Success criterion | Tests (RESEARCH ids) | Automated Command | File Exists | Status |
|-----|-------------------|----------------------|-------------------|-------------|--------|
| CONV-01 | SC1 id round trip on four routes | T1, T20-T24 | `python -m pytest tests/test_stream_api.py tests/test_conversations.py -q -k "conversation_id or busy_conversation or frees_the_conversation or failed_turn or unstarted_stream or read_after_the_lease"` | ❌ W0 | ⬜ pending |
| CONV-02 | SC2 identical 404 before any model call | T4, T6 | `python -m pytest tests/test_api.py tests/test_stream_api.py -q -k "same_404 or before_any_model_call"` | ✅ files exist | ⬜ pending |
| CONV-03 | SC2 stored turn fields | T5 | `python -m pytest tests/test_conversations.py -q -k stores_the_message` | ❌ W0 | ⬜ pending |
| CONV-04 | SC3 delete cascade, race, no cache | T7-T12, T25 | `python -m pytest tests/test_api.py tests/test_conversations.py -q -k "also_deletes_its_conversations or purges_cross_document or delete_during_a_turn or serialised or no_disk_cache or omits_cache_dir or traces_are_off"` | ❌ W0 | ⬜ pending |
| PRMT-01 | SC1 history block in prompt, first turn unchanged | T2, T3, T3b | `python -m pytest tests/test_api.py tests/test_conversations.py -q -k "history_block or first_turn or both_styles"` | ❌ W0 | ⬜ pending |
| PRMT-03 | SC4 defanged history, StreamGuard only | T13-T15 | `python -m pytest tests/test_conversations.py tests/test_stream_api.py tests/test_stream_guard.py -q` | ❌ W0 | ⬜ pending |
| PRMT-04 | SC5 hard cap and budget | T16-T19 | `python -m pytest tests/test_conversations.py -q -k "is_refused_before_any_model_call or stored_word_cap or oversized_follow_up or worst_case"` | ❌ W0 | ⬜ pending |
| regression | existing trace counts and stream equality | T26 | `python -m pytest tests/test_api.py tests/test_stream_api.py -q` | ✅ | ⬜ pending |

`fails_when` for every command above: non-zero exit, or any of the per-test conditions listed in `02-RESEARCH.md` (T1-T26).

---

## Wave 0 Requirements

- [ ] Phase 1 executed (seam, `rag/query/history.py`, `tests/test_prompt_snapshot.py`) — prerequisite
- [ ] `tests/test_conversations.py` — new; `GatedLLM`, `seed_turns` helper
- [ ] `rag/query/history.py` additions — `CONVERSATION_MAX_STORED_WORDS`, `estimate_prompt_tokens`, `fits_context`
- Framework install: none.

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
