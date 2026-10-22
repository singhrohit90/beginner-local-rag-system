---
phase: "05"
slug: "chat-page-and-honest-docs"
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-22"
---

# Phase 05 — Validation Strategy

> Per-phase validation contract. The full check list (V-1 to V-10, static contract cases, the optional node harness and the manual checklist, each with command and `fails_when`) is in `05-RESEARCH.md` §"Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8 (existing page tests in `tests/test_api.py` read the served page; `node --check` syntax test); node for the optional harness |
| **Config file** | none |
| **Quick run command** | `python -m pytest tests/test_page_conversation.py -q` |
| **Full suite command** | `python -m pytest tests -q` |
| **Estimated runtime** | ~10 seconds quick; ~180-600 seconds full |

---

## Sampling Rate

- **After every task commit:** quick command plus the nine existing page tests named in RESEARCH (explicit node ids)
- **After every plan wave:** `python -m pytest tests/test_page_conversation.py tests/test_api.py tests/test_stream_api.py -q`
- **Before `/gsd-verify-work`:** full suite green; docs checks (structure greps, numbers present in `docs/chat_memory_eval.md`, cited paths exist)
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Req | Success criterion | Automated Command | File Exists | Status |
|-----|-------------------|-------------------|-------------|--------|
| PAGE-01 | SC1 id kept and reset; SC2 stale 404 recovers | `python -m pytest tests/test_page_conversation.py -q` (static contract + node harness) | ❌ W0 | ⬜ pending |
| PAGE-02 | SC3 clarify as text | `python -m pytest tests/test_page_conversation.py -q -k clarify` and `grep -c innerHTML rag/api/static/index.html` prints 1 | ❌ W0 | ⬜ pending |
| DOCS-01 | SC4 Step 11, backlog, honest interview relabel | docs checks in RESEARCH V-7..V-10 | ✅ files exist | ⬜ pending |

`fails_when` for every command: non-zero exit, or the condition listed in `05-RESEARCH.md`.

---

## Wave 0 Requirements

- [ ] Phases 2-4 executed (API contract and `docs/chat_memory_eval.md`)
- [ ] `tests/test_page_conversation.py` — static contract cases and the optional node harness
- [ ] `test_choosing_another_document_keeps_the_conversation_on_the_page` rewritten in the same commit as the page edit

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Follow-up uses earlier turns; New conversation and target change start fresh; stale id recovers with notice; clarification renders `<b>x</b>` literally | PAGE-01, PAGE-02 | Needs a real browser and models | 9-step checklist in `05-RESEARCH.md`; marked `human_needed` in VERIFICATION |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
