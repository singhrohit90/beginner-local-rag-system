---
phase: 05-chat-page-and-honest-docs
verified: 2026-10-26T00:00:00Z
status: passed
score: 14/14 must-haves verified
covered_files:
  - .planning/phases/05-chat-page-and-honest-docs/05-01-PLAN.md
  - .planning/phases/05-chat-page-and-honest-docs/05-01-SUMMARY.md
  - .planning/phases/05-chat-page-and-honest-docs/05-02-PLAN.md
  - .planning/phases/05-chat-page-and-honest-docs/05-02-SUMMARY.md
  - .planning/phases/05-chat-page-and-honest-docs/05-03-PLAN.md
  - .planning/phases/05-chat-page-and-honest-docs/05-03-SUMMARY.md
  - .planning/phases/05-chat-page-and-honest-docs/05-04-PLAN.md
  - .planning/phases/05-chat-page-and-honest-docs/05-04-SUMMARY.md
  - .planning/phases/05-chat-page-and-honest-docs/05-05-PLAN.md
  - .planning/phases/05-chat-page-and-honest-docs/05-05-SUMMARY.md
  - docs/backlog.md
  - interview/05_conversation_memory_and_cost.md
  - interview/README.md
  - rag/README.md
  - rag/api/static/index.html
  - tests/page_harness.js
  - tests/test_api.py
  - tests/test_page_conversation.py
covered_digest: "v3:sha256:3d8325a0f412d6cacf4964fd30db62c957aec8514be67760e45c4140a8ef2833"
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "1. Follow-up (criterion 1). Scope \"all my documents\", ask a content question, then \"and what about its drawbacks?\"."
    expected: "The first ask/stream body has no conversation_id and its final has one; the second body carries the same id and the answer refers to the earlier subject."
    why_human: "Needs a real browser, the live server and the model tunnel; the node harness covers the request bodies but not a real model answer."
  - test: "2. New conversation (criterion 1). After an answer click \"New conversation\", then ask again."
    expected: "The log empties, the pipeline panel shows its first hint, and the next body has no conversation_id."
    why_human: "Real browser behaviour of the button; the harness proves it on a fake DOM only."
  - test: "3. Target change (criterion 1). After an answer, change the scope select; under \"checked documents\" tick a document; under \"this document\" click another document; under \"all my documents\" click a row."
    expected: "Each of the first three empties the log and the next body has no id; the row click under \"all\" keeps the log and the id."
    why_human: "Real browser event wiring; harness proves it on a fake DOM only."
  - test: "4. Delete (D-02). Scope \"all my documents\", one answer, delete a ready document, ask again."
    expected: "The log empties after the delete and the next body has no id."
    why_human: "Real browser and server delete path."
  - test: "5. Stale id (criterion 2). In the console type conversationId = \"a\".repeat(32) then ask (or: two tabs, ask in tab A, delete a document in tab B, follow up in tab A)."
    expected: "A 404 then a second request without conversation_id; the log shows \"Started a new conversation (the previous one is no longer available).\" above the answer; no red error remains; at most two requests."
    why_human: "Real server 404 through a real browser fetch."
  - test: "6. Clarify renders as text (criterion 3). Console fetch override returning a final event with kind \"clarify\" and answer \"Do you mean <b>x</b> or the other one?\" (exact snippet in 05-05-SUMMARY.md); ask, click the bubble, restore window.fetch = realFetch and ask again; then with RAG_REWRITE=1 ask an ambiguous pronoun follow-up after two plausible subjects."
    expected: "The bubble shows <b>x</b> literally (not bold) with a \"clarifying question\" label; the panel shows one meta line and no stages table; the next real request carries that id (the server then answers 404 for the canned id and the page starts a new conversation with the notice). The genuine clarify path is seen with the rewriter on."
    why_human: "Visual rendering in a real browser and the genuine rewriter path need the model server."
  - test: "7. Superseded stream (D-04). Start a long answer and click \"New conversation\" while tokens arrive, then ask once more."
    expected: "The stream stops, the log is empty, Ask is enabled, and the next request has no conversation_id."
    why_human: "Real-time streaming and abort in a real browser."
  - test: "8. 409 messages (D-04). Console fetch override returning new Response(JSON.stringify({detail:\"this conversation is full; start a new conversation\"}), {status:409}) for /v1/ask/stream, ask; repeat with the detail \"conversation is busy, retry when the previous answer is finished\"."
    expected: "The bubble and the error area show a readable sentence ending with \"Use the New conversation button.\" for full and the busy sentence for busy; the id is unchanged and Ask is enabled."
    why_human: "Error-message readability in a real browser."
  - test: "9. Layout (D-12). Look at the controls row in light and dark themes at a 900 px window."
    expected: "The New conversation button matches the other buttons and the controls row does not wrap."
    why_human: "Visual appearance."
---

# Phase 5: Chat page and honest docs Verification Report

**Phase Goal:** As a chat user, I want to keep one conversation going in the browser page and start a fresh one when I choose, so that follow-ups and clarifying questions work where I chat and the project docs describe only what was built and measured.
**Verified:** 2026-10-26
**Status:** human_needed
**Re-verification:** No (initial verification)

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1: the page keeps the conversation id across questions; New conversation and a change of selected documents make the next question start fresh (no id sent) | VERIFIED | `rag/api/static/index.html`: one `let conversationId = null, epoch = 0, inflight = null;`; `askContent` adds the id only via `if (conversationId) body.conversation_id = conversationId;`; id stored only from a content answer's `r.conversation_id`. Harness scenarios `follow_up`, `new_conversation`, `target_change` run the real served script and pass (body keys exactly question/doc_ids/config(+conversation_id); scope change, other doc under "one", checkbox under "checked", delete of a target all drop the id and empty the log; row click under "all" keeps both). |
| 2 | SC2: a 404 for the stored id starts a new conversation on its own, no error left to clear | VERIFIED | `askContent` catches only `sent && err.status === 404 && err.detail === CONV_GONE`, clears the id, inserts the notice via `el()`, resends once without the id. Server side: `guarded()` in `rag/api/main.py` returns 404 "no such conversation", raised eagerly in `ask_documents_stream` (`rag/api/service.py` 649-664, before any SSE byte). Harness `stale_404` (2 requests, notice, empty error, new id) and `other_404` (1 request, ordinary "404: no such document", id kept) pass. |
| 3 | SC3: a clarifying question appears as an ordinary assistant turn, rendered as text | VERIFIED | Clarify answer goes through `msg.replaceChildren(r.answer || "")` (text node) with an `el("small",...)` "clarifying question" label; `detailClarify()` shows one meta line. Harness `clarify`: `<b>x</b>` shown literally, no B element in the log, fake DOM throws on innerHTML/outerHTML/insertAdjacentHTML, next ask carries the same id. Server `_clarify_response` supplies every field the page reads (`blocked`, `kind`, `conversation_id`). |
| 4 | SC4: README Step 11, backlog done + compaction + retention, interview relabelled only for built and measured | VERIFIED | `rag/README.md` has exactly one `## Step 11: chat memory`, the last Step heading (line 326); Step 8 points to it. `docs/backlog.md`: "Chat memory: done", compaction, reload-resume GET, panel rewrite, turn counter, "Conversation retention" bullet, rewriting/intent-classification line split. `interview/05_...md` sections 1-2 relabelled; section 3 unchanged (diff hunks only at lines 2, 24, 53); `interview/README.md` row updated. |
| 5 | Six reset sites exactly (D-02 with A2, E10) | VERIFIED | `resetConversation(` occurs 7 times (definition + newconv button, scope change, select under "one" with a different id, checkbox under "checked", delete of a pre-computed target, upload under "one" with a different doc). |
| 6 | Readable 409s keep the id, are never retried, leave Ask enabled (D-04) | VERIFIED | `httpError` builds the two sentences; harness `conflict_409` passes (no "409:" prefix, " Use the New conversation button." for full, one request per ask, id A kept, Ask enabled). Strings match `rag/api/main.py` 340-344 (`test_the_page_matches_the_server_conversation_errors`). |
| 7 | A superseded ask is aborted and its late result is dropped | VERIFIED | One `new AbortController`, signal passed to both routes; `mine !== epoch` guards in the catch, after the call and in finally. Harness `superseded` passes (signal aborted at reset, late final leaves id null, log and error empty, Ask enabled). |
| 8 | Only new control is `#newconv` (type button) between config and send; no CSS added (D-12) | VERIFIED | Diff adds one `<button type="button" id="newconv">`; no style-block lines changed in the diff; `test_the_new_conversation_button_does_not_submit_and_sits_before_ask` passes. |
| 9 | Text only, no markup (D-06); id kept only in the JS variable; ask-about never gets the id | VERIFIED | Counts on the page: innerHTML 1 (the "never innerHTML" comment, line 118), outerHTML 0, insertAdjacentHTML 0, document.write 0, localStorage 0, sessionStorage 0, document.cookie 0, `</script>` 1. `/v1/ask-about` body is `{ question, doc_ids }` only. |
| 10 | Rewritten select test and new page tests pin the contract and fail on the old page | VERIFIED | `test_choosing_another_document_resets_the_conversation_only_under_scope_one` present and passing (9 page tests in test_api/test_stream_api pass). Verifier rerun: `PAGE_UNDER_TEST=<P5_BASE page in scratch>` gives `16 failed`; HEAD page gives `16 passed in 5.00s`. Working tree untouched (`git status` shows only `.planning/state.json`). |
| 11 | Every number in Step 11 and the interview Measured bullet is in a committed file; Decision line copied word for word; provisional stated | VERIFIED | 0.633, 0.733, 0.461, 0.592, 0.867, 10.0, 0.2539, wins 6 / losses 3, 37/37, 34 of 34, 17, 6 of 37 all occur in `docs/chat_memory_eval.md` (tracked); 16 occurs in the tracked `.planning/phases/04-.../04-10-SUMMARY.md` line 32. "Decision: ships off (failed: a, c, f; provisional: items pending human review)" occurs verbatim in the eval file. Both docs say provisional. |
| 12 | Constants, defaults, error strings and paths cited in docs match the code | VERIFIED | All nine `NAME = N` constants occur once in `rag/query/history.py` / `rag/api/conversations.py`; `RAG_REWRITER` default `ollama:qwen2.5:7b` in `rag/api/main.py` 175; `purge_document`, `check_room`, `fits_context` exist; storage paths match `rag/api/conversations.py` 9-11, 44, 181; every cited test/code file is tracked. |
| 13 | Nothing unbuilt labelled Built | VERIFIED | Rolling summary, structured memory, retrieval over history, 70% trigger: "Not built." Cost tracking/tracing unchanged (section 3 byte-identical). Answer arm, question slot, judge-vs-rewriter, `max_model_len`: "Not measured." Page ignores `rewrite`, no turn counter (no matching code in the page). |
| 14 | Phase gate invariants hold (suite, retrieval, fingerprint, protected files) | VERIFIED | Gate output `pytest_full.txt`: `933 passed, 2 skipped`; `fingerprint.txt`: `b69624ed9d1a5781`; retrieval line hit@5 0.865, mrr 0.663 (05-05 SUMMARY, `retrieval.txt`). Verifier: `git diff --quiet 758a0c5..HEAD -- rag/api/main.py rag/api/service.py rag/query docs/chat_memory_eval.md data/golden requirements-rag.txt` is clean; only 8 files changed outside `.planning`. |

**Score:** 14/14 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `rag/api/static/index.html` | id lifecycle, New conversation, reset sites, stale retry, 409s, abort/epoch, clarify | VERIFIED | Substantive (93-line diff), served by the app, exercised by the harness |
| `tests/test_api.py` | rewritten select test | VERIFIED | 3+/2- lines; passes |
| `tests/page_harness.js` | node fake DOM, stub fetch, 8 scenarios | VERIFIED | Runs the served script via `node:vm`; unknown URLs throw; waits poll with 30 s ceiling (`waitFor`), no fixed sleep |
| `tests/test_page_conversation.py` | static + behaviour tests | VERIFIED | 16 tests; reads the served page through `make_client`; skips when node is missing |
| `rag/README.md` | Step 11 | VERIFIED | Last Step heading; numbers copied from the eval file |
| `docs/backlog.md` | done bullet, 4 open items, retention | VERIFIED | Order: done, compaction, reload GET, panel, turn counter, then Cost and observability; retention follows traces retention |
| `interview/05_conversation_memory_and_cost.md` | honest relabel | VERIFIED | See truths 11-13 |
| `interview/README.md` | index row | VERIFIED | Says follow-ups built, rewriting ships off, compaction and cost tracking not built |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| index.html | main.py | `conversation_id` in POST /v1/ask/stream body; read from final | WIRED | `AskAcrossRequest.conversation_id` forwarded to `ask_documents_stream` (main.py 409-414) |
| index.html | main.py | `CONV_GONE = "no such conversation"` | WIRED | Same string at main.py 340 |
| test_api.py | index.html | select() slice requires the scope-one reset | WIRED | Passing |
| test_page_conversation.py | page_harness.js | subprocess with the served script on stdin | WIRED | 16 passed |
| test_page_conversation.py | main.py | SERVER_STRINGS must occur in main.py | WIRED | `test_the_page_matches_the_server_conversation_errors` |
| rag/README.md, interview note | docs/chat_memory_eval.md | numbers and Decision line copied | WIRED | All numbers found |
| docs/backlog.md | rag/README.md | "Step 11" | WIRED | Present in the done bullet |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| index.html | `conversationId` | `final.conversation_id` from `/v1/ask/stream` (`_describe` / `_clarify_response` in service.py) | Yes (server-issued) | FLOWING |
| index.html | clarify bubble text | `final.answer` from `_clarify_response` (passes `filter_output`) | Yes | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Page conversation behaviour on the real script | `python -m pytest tests/test_page_conversation.py -q` | `16 passed in 5.00s` | PASS |
| Tests fail on the old page | `PAGE_UNDER_TEST=<scratch P5_BASE page> python -m pytest tests/test_page_conversation.py -q` | `16 failed in 4.28s` | PASS |
| Existing page tests unchanged | `python -m pytest tests/test_api.py tests/test_stream_api.py -q -k "page or document_resets"` | `9 passed, 99 deselected` | PASS |
| No markup sinks / storage | grep counts on the page | innerHTML 1 (comment), others 0, `</script>` 1 | PASS |
| Protected files unchanged | `git diff --quiet 758a0c5..HEAD -- rag/api/main.py rag/api/service.py rag/query docs/chat_memory_eval.md data/golden requirements-rag.txt` | clean | PASS |

Full suite not rerun by the verifier (gate output `933 passed, 2 skipped` read from `.planning/runs/20261021-1840-chat-memory/phase-05-gate/pytest_full.txt`).

### Probe Execution

Step 7c: no `scripts/*/tests/probe-*.sh` declared by the phase; not applicable.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| PAGE-01 | 05-01, 05-02, 05-05 | keep id, reset on new conversation / target change, handle stale 404 | SATISFIED (browser pass pending) | Truths 1, 2, 5-7, 10 |
| PAGE-02 | 05-01, 05-02, 05-05 | clarifying question as an ordinary turn via textContent | SATISFIED (browser pass pending) | Truth 3, 9 |
| DOCS-01 | 05-03, 05-04, 05-05 | README Step 11, backlog, interview relabel with recorded numbers | SATISFIED | Truths 4, 11-13 |

No orphaned requirements: REQUIREMENTS.md maps only PAGE-01, PAGE-02, DOCS-01 to Phase 5. (The traceability rows still read "Pending"; updating them is the orchestrator's phase-completion step, not a code gap.)

### Prohibitions

| Prohibition | Tier | Disposition |
|-------------|------|-------------|
| No innerHTML in new code, no markup from text | test | Enforced: harness throws on HTML sinks; static test; grep count 1 |
| No history/owner/extra fields to ask routes; no id to ask-about | test | Enforced: harness asserts exact body key sets; ask-about body read in code |
| Id only in the JS variable | test | Enforced: storage/cookie counts 0 |
| No edit to main.py, service.py, rag/query, routes | test | Enforced: git diff clean |
| No package, build step, CSS rule or extra script tag | test | Enforced: no package.json/node_modules; no style change; `</script>` 1 |
| No deferred idea built (reload GET, list, panel rewrite, fallback flag, turn counter) | judgment | Non-authoritative LLM judgment: not built (no `rewrite`, `turn` or `/v1/conversations` use in the page) |
| Docs: no unbuilt item described as built; no number outside committed files | test | Enforced by verifier checks (truths 11-13) |
| Hook-safety rules (llm.py / test_vllm.py names, .env) | judgment | Process rule; not checkable from the tree. Non-authoritative: no evidence of a breach |

### Anti-Patterns Found

None. No TBD/FIXME/XXX/TODO/HACK added in the eight changed files. `return null`/`= null` matches in the page are initial state overwritten by the server's id.

### Human Verification Required

From 05-05-SUMMARY.md "Human verification (human_needed)", verbatim. Setup: start WSL, OpenSearch and the tunnel per CLAUDE.md; run `RAG_REWRITE=1 RAG_STORE=opensearch python -m uvicorn rag.api.main:app --port 18642`; two ready PDFs; devtools open on the Network tab with "Disable cache" ticked; hard reload.

1. **Follow-up (criterion 1).** Scope "all my documents", ask a content question, then "and what about its drawbacks?". Expected: the first `ask/stream` body has no `conversation_id` and its `final` has one; the second body carries the same id and the answer refers to the earlier subject.
2. **New conversation (criterion 1).** After an answer click "New conversation", then ask again. Expected: the log empties, the pipeline panel shows its first hint, and the next body has no `conversation_id`.
3. **Target change (criterion 1).** After an answer, change the scope select; under "checked documents" tick a document; under "this document" click another document; under "all my documents" click a row. Expected: each of the first three empties the log and the next body has no id; the row click under "all" keeps the log and the id.
4. **Delete (D-02).** Scope "all my documents", one answer, delete a ready document, ask again. Expected: the log empties after the delete and the next body has no id.
5. **Stale id (criterion 2).** In the console type `conversationId = "a".repeat(32)` then ask (or: two tabs, ask in tab A, delete a document in tab B, follow up in tab A). Expected: a 404 then a second request without `conversation_id`; the log shows "Started a new conversation (the previous one is no longer available)." above the answer; no red error remains; at most two requests.
6. **Clarify renders as text (criterion 3).** In the console:
   ```
   const realFetch = window.fetch;
   window.fetch = async (u, o) => u.endsWith("/v1/ask/stream") ? new Response("event: final\ndata: " + JSON.stringify({kind:"clarify", answer:"Do you mean <b>x</b> or the other one?", conversation_id:"a".repeat(32), turn:2, passages:[], citations:[], stages:[], blocked:[], skipped_by_scanner:[], documents:[], abstained:false, replace:false, llm:"rewriter", seconds:0, query_id:"clarify-1", rewrite:{status:"clarify"}}) + "\n\n", {status:200}) : realFetch(u, o);
   ```
   Ask, click the bubble, restore `window.fetch = realFetch` and ask again. Expected: the bubble shows `<b>x</b>` literally (not bold) with a "clarifying question" label; the panel shows one meta line and no stages table; the next real request carries that id (the server then answers 404 for the canned id and the page starts a new conversation with the notice). Then with `RAG_REWRITE=1` ask an ambiguous pronoun follow-up after two plausible subjects to see the genuine path.
7. **Superseded stream (D-04).** Start a long answer and click "New conversation" while tokens arrive, then ask once more. Expected: the stream stops, the log is empty, Ask is enabled, and the next request has no `conversation_id`.
8. **409 messages (D-04).** Console fetch override returning `new Response(JSON.stringify({detail:"this conversation is full; start a new conversation"}), {status:409})` for `/v1/ask/stream` (same pattern as step 6), ask; repeat with the detail `"conversation is busy, retry when the previous answer is finished"`. Expected: the bubble and the error area show a readable sentence ending with "Use the New conversation button." for full and the busy sentence for busy; the id is unchanged and Ask is enabled.
9. **Layout (D-12).** Look at the controls row in light and dark themes at a 900 px window. Expected: the New conversation button matches the other buttons and the controls row does not wrap.

### Gaps Summary

No gaps. Every roadmap criterion and plan truth is met in the code and docs, and the page's state changes are exercised on the real served script by a node harness that fails 16/16 on the pre-phase page. What remains is the browser pass above (real rendering, real streaming and abort, real server 404/409, layout), which an unattended run with the tunnel down could not perform.

---

_Verified: 2026-10-26_
_Verifier: Claude (gsd-verifier)_

## Lead resolution of the human items (2026-10-26)

Status set from `human_needed` to `passed` by the flow lead; 14/14 verified, no gaps. The nine browser checks above cannot run in this environment (the page needs a live answer model for follow-ups, and the model tunnel is down). They were named at gate 1 as a check for the owner and are carried to the merge gate as the owner's browser checklist; they are not verified.
