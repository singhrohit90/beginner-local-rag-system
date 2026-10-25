---
phase: 05-chat-page-and-honest-docs
plan: 01
status: complete
requirements: [PAGE-01, PAGE-02]
---

# 05-01 Summary: conversation id, resets, stale-id retry and clarify on the chat page

## Base

P5_BASE=758a0c56b29093641f3b0b6e163ef4352d261998

The three conversation detail strings in `guarded()` (`rag/api/main.py`), matching the plan exactly (no deviation):

- 404 `no such conversation`
- 409 `conversation is busy, retry when the previous answer is finished`
- 409 `this conversation is full; start a new conversation`

## Commits

| Task | Commit | Subject |
|------|--------|---------|
| 1 | b082667 | feat(05-01): keep the conversation id on the page and add New conversation |
| 2 | 9a290ec | feat(05-01): start a fresh conversation when the target documents change |
| 3 | e22cb42 | feat(05-01): recover from a stale conversation id and show clarifying questions as text |

## What was built

- `rag/api/static/index.html`: state `let conversationId = null, epoch = 0, inflight = null;`, `CONV_GONE`, `DETAIL_HINT`;
  `resetConversation()`, `httpError(status, detail)`, `askContent(...)` (async), `detailClarify()`;
  `streamAsk(path, body, onText, signal)`; a `New conversation` button (`type="button"`, `id="newconv"`).
- Six reset sites: New conversation button, scope change, `select()` under "one" with a different id, checkbox under
  "checked", delete of a document in the pre-request target set, upload under "one" when the document differs.
- One AbortController per ask plus an epoch guard; a superseded ask writes nothing and does not set the id.
- 404 "no such conversation" on an ask that sent an id: notice, id cleared, one resend with no id. 409 full gets
  " Use the New conversation button."; 409 busy is shown as is; neither is retried.
- Clarify: `small.meta` label "clarifying question" before the text; clicking shows `detailClarify()`.
- `tests/test_api.py`: `test_choosing_another_document_keeps_the_conversation_on_the_page` rewritten as
  `test_choosing_another_document_resets_the_conversation_only_under_scope_one`.

## Fail-first

With the page change stashed (`git stash push -q -m p5-0501-select-test -- rag`):

```
FAILED tests/test_api.py::test_choosing_another_document_resets_the_conversation_only_under_scope_one
1 failed in 1.28s
```

After `git stash pop -q`, `git diff --name-only -- rag` listed `rag/api/static/index.html`.

## Verification

- Task 1: `tracer ok`; pinned page tests `9 passed`; static gate ok (innerHTML 1, storage/markup 0, `</script>` 1,
  `resetConversation(` 2, no API or query file changed).
- Task 2: `9 passed`; `six reset sites ok`; static gate ok.
- Task 3: `stale, conflict and clarify ok`; `9 passed`; `tests/test_api.py tests/test_stream_api.py` -> `108 passed`;
  `resetConversation(` 7; `res.status}:` 0.
- Full suite in the worktree: `916 passed, 3 skipped` (saved to
  `.planning/runs/20261021-1840-chat-memory/wave-p5-05-01-1.txt` in the main checkout). The third skip is
  `tests/test_golden_conversations.py:106: data/processed/ddia.pages.jsonl is absent`; `data/processed/` is
  gitignored and absent in a fresh worktree, so it is an environment skip, not a change in behaviour.

## Deviations

- Acceptance criterion "`grep -c 'clarifying question'` prints 1" cannot hold together with the planned string
  `A clarifying question: no passages were retrieved for it.`, which contains the same words; the count is 2 (the
  label line and the detail line). Both strings are as the plan specifies.
- `askContent` is declared `async` so its `try { return await streamAsk(...) }` can catch the 404.
