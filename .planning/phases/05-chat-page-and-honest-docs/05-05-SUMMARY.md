---
phase: 05-chat-page-and-honest-docs
plan: 05
status: complete
requirements: [PAGE-01, PAGE-02, DOCS-01]
---

# 05-05 Summary: Phase 5 gate

Run on 2026-10-26 at b8cdd9a (flow/chat-memory after the wave 2 merges), OpenSearch up (HTTP 200 on the
local port). Gate outputs saved under `.planning/runs/20261021-1840-chat-memory/phase-05-gate/`
(`pytest_full.txt`, `collect_p5_base.txt`, `collect_head.txt`, `collect_compare.txt`, `retrieval.txt`,
`fingerprint.txt`, `phase_checks.txt`, `docs_agree.txt`, `llm_check.txt`).

## Invariant record

Suite (main checkout, which holds the gitignored `data/processed/`):

- `python -m pytest tests -q` -> `933 passed, 2 skipped in 236.84s (0:03:56)`
- In the 05-05 worktree (no `data/processed/`): `932 passed, 3 skipped in 241.20s (0:04:01)` (saved as
  `wave-p5-05-05-1.txt`); the extra skip is `tests/test_golden_conversations.py:106: data/processed/ddia.pages.jsonl
  is absent`.

Collected count (git archive export of P5_BASE, node ids compared):

```
collected 935 = 919 at P5_BASE + 16
```

The 16 new node ids are in `tests/test_page_conversation.py`; the one removed id is the renamed select test in
`tests/test_api.py` (replaced by `test_choosing_another_document_resets_the_conversation_only_under_scope_one`).

## Phase checks

Retrieval (`python -m rag.experiments.retrieval --chunkers semantic --configs weighted`):

```
semantic      weighted        0.568  0.865  0.797  0.663   0.677    0.919     52  lost_at_context:3, lost_at_fuse:1, retrieval_miss:1, unanswerable:8
```

Prompt fingerprint: `b69624ed9d1a5781`.

Phase checks (files changed since P5_BASE under rag, tests, docs, interview, data, requirements):

```
docs/backlog.md
interview/05_conversation_memory_and_cost.md
interview/README.md
rag/README.md
rag/api/static/index.html
tests/page_harness.js
tests/test_api.py
tests/test_page_conversation.py
test_api numstat: 3	2	tests/test_api.py
phase checks ok
```

(The style-block comparison strips `\r` on both sides: the working copy has CRLF line ends, `git show` prints LF.)

Docs check: `docs agree`.

Model check (`python -m rag.common.llm_check`):

```
FAIL  cannot reach the model server ... ([WinError 10061] No connection could be made because the target machine actively refused it). This is usually the SSH tunnel (PuTTY) not being connected.
```

Tunnel down; recorded, not a failure.

## Decision coverage

| Decision | Built in | Pinned by | Verified |
|----------|----------|-----------|----------|
| D-01 one id variable, sent only when set | 05-01 Task 1 | `test_the_page_declares_one_conversation_id_and_sends_it_only_when_set`, `test_a_follow_up_sends_the_id_the_first_answer_returned` | suite green |
| D-02 reset sites (A2 scope-one select, E10 upload) | 05-01 Tasks 1-2 | `test_every_target_change_resets_the_conversation`, `test_each_target_change_drops_the_id_and_a_highlight_does_not`, `test_new_conversation_clears_the_log_and_the_next_question_has_no_id`, `test_choosing_another_document_resets_the_conversation_only_under_scope_one` | suite green |
| D-03 stale id: notice and one resend | 05-01 Task 3 | `test_a_stale_id_starts_a_new_conversation_with_one_resend`, `test_another_404_is_an_ordinary_error_without_a_retry`, `test_a_stale_id_is_retried_once_and_other_errors_are_not` | suite green |
| D-04 409 sentences; abort and epoch (refined) | 05-01 Tasks 1 and 3 | `test_conversation_conflicts_read_as_sentences_and_keep_the_id`, `test_a_superseded_ask_is_aborted_and_cannot_bring_its_id_back`, `test_a_running_ask_can_be_cancelled` | suite green |
| D-05 clarify as an ordinary turn | 05-01 Task 3 | `test_a_clarifying_question_shows_markup_as_text`, `test_a_clarifying_question_is_labelled_and_has_no_passages_panel` | suite green |
| D-06 text only, no markup | 05-01 all tasks | `test_the_page_builds_no_markup_from_text`, `test_the_page_is_served`, `test_the_page_reads_the_stream_and_shows_text_only` | suite green; innerHTML count 1 |
| D-07 verification (rewritten test, static and node tests, human_needed pass) | 05-01 Task 2, 05-02, 05-05 | the rewritten select test; `tests/test_page_conversation.py` (16 failed on P5_BASE, 16 passed on HEAD); the human checks below | fail-first in 05-01 and 05-02 summaries; human items open |
| D-08 README Step 11 | 05-03 Task 1 | `numbers ok`, `sources ok`; `docs agree` | yes |
| D-09 backlog | 05-03 Task 2 | `backlog ok`, `order ok` | yes |
| D-10 interview relabel | 05-04 | `section 1 ok`, `paths ok`, `section 2 ok`, `index ok` | yes |
| D-11 provisional wording | 05-03, 05-04 | provisional branches of the docs gates; `docs agree` | yes |
| D-12 existing styles only | 05-01 Task 1 | style-block comparison in `phase checks ok` | yes |

## Edge coverage

| Probe item | Resolution | Where |
|------------|------------|-------|
| PAGE-01 concurrency | resolved (explicit) as truths | 05-01; tests in 05-02 (`superseded`, `conflict_409`) |
| PAGE-02 unclassified | unresolved by the probe; flagged assumption | 05-01, 05-02; behaviour covered by the clarify tests |
| DOCS-01 adjacency | resolved (explicit) | 05-03 and 05-04 gates (Decision line copied, never re-derived) |
| DOCS-01 empty | resolved (explicit) | 05-03 and 05-04 preconditions; "not measured" wording for the answer arm |
| DOCS-01 ordering | resolved (explicit) | 05-03 `order ok`; 05-04 section order check |

Six probe rows: five authored as truths, one flagged; none dropped.

## Human verification (human_needed)

Not run by this unattended run (no browser, tunnel down). The verifier should mark the phase `human_needed`
for these nine items.

Setup: start WSL, OpenSearch and the tunnel per CLAUDE.md; run
`RAG_REWRITE=1 RAG_STORE=opensearch python -m uvicorn rag.api.main:app --port 18642`; two ready PDFs; devtools
open on the Network tab with "Disable cache" ticked; hard reload.

1. **Follow-up (criterion 1).** Scope "all my documents", ask a content question, then "and what about its
   drawbacks?". Expected: the first `ask/stream` body has no `conversation_id` and its `final` has one; the second
   body carries the same id and the answer refers to the earlier subject.
2. **New conversation (criterion 1).** After an answer click "New conversation", then ask again. Expected: the log
   empties, the pipeline panel shows its first hint, and the next body has no `conversation_id`.
3. **Target change (criterion 1).** After an answer, change the scope select; under "checked documents" tick a
   document; under "this document" click another document; under "all my documents" click a row. Expected: each of
   the first three empties the log and the next body has no id; the row click under "all" keeps the log and the id.
4. **Delete (D-02).** Scope "all my documents", one answer, delete a ready document, ask again. Expected: the log
   empties after the delete and the next body has no id.
5. **Stale id (criterion 2).** In the console type `conversationId = "a".repeat(32)` then ask (or: two tabs, ask in
   tab A, delete a document in tab B, follow up in tab A). Expected: a 404 then a second request without
   `conversation_id`; the log shows "Started a new conversation (the previous one is no longer available)." above
   the answer; no red error remains; at most two requests.
6. **Clarify renders as text (criterion 3).** In the console:
   ```
   const realFetch = window.fetch;
   window.fetch = async (u, o) => u.endsWith("/v1/ask/stream") ? new Response("event: final\ndata: " + JSON.stringify({kind:"clarify", answer:"Do you mean <b>x</b> or the other one?", conversation_id:"a".repeat(32), turn:2, passages:[], citations:[], stages:[], blocked:[], skipped_by_scanner:[], documents:[], abstained:false, replace:false, llm:"rewriter", seconds:0, query_id:"clarify-1", rewrite:{status:"clarify"}}) + "\n\n", {status:200}) : realFetch(u, o);
   ```
   Ask, click the bubble, restore `window.fetch = realFetch` and ask again. Expected: the bubble shows `<b>x</b>`
   literally (not bold) with a "clarifying question" label; the panel shows one meta line and no stages table; the
   next real request carries that id (the server then answers 404 for the canned id and the page starts a new
   conversation with the notice). Then with `RAG_REWRITE=1` ask an ambiguous pronoun follow-up after two plausible
   subjects to see the genuine path.
7. **Superseded stream (D-04).** Start a long answer and click "New conversation" while tokens arrive, then ask once
   more. Expected: the stream stops, the log is empty, Ask is enabled, and the next request has no
   `conversation_id`.
8. **409 messages (D-04).** Console fetch override returning
   `new Response(JSON.stringify({detail:"this conversation is full; start a new conversation"}), {status:409})` for
   `/v1/ask/stream` (same pattern as step 6), ask; repeat with the detail
   `"conversation is busy, retry when the previous answer is finished"`. Expected: the bubble and the error area show
   a readable sentence ending with "Use the New conversation button." for full and the busy sentence for busy; the
   id is unchanged and Ask is enabled.
9. **Layout (D-12).** Look at the controls row in light and dark themes at a 900 px window. Expected: the New
   conversation button matches the other buttons and the controls row does not wrap.

## STATE.md

STATE.md commit: db54bfc (`docs(05-05): record the Phase 5 baseline and the human_needed browser pass`).
