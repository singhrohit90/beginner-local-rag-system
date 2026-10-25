---
phase: 05-chat-page-and-honest-docs
plan: 02
status: complete
requirements: [PAGE-01, PAGE-02]
---

# 05-02 Summary: page harness and conversation contract tests

## Commits

| Task | Commit | Subject |
|------|--------|---------|
| 1 | f8a07a4 | test(05-02): drive the page script in node and prove a follow-up keeps its id |
| 2 | 422c363 | test(05-02): prove New conversation, target changes and the stale-id recovery in the page |
| 3 | 4b39587 | test(05-02): pin conflicts, clarify, the superseded stream and the page contract |

Each commit was made with the two test files as an explicit pathspec and holds only those two files.

## What was built

- `tests/page_harness.js`: plain node (only `node:vm`), fake DOM that throws on `innerHTML`, `outerHTML` and
  `insertAdjacentHTML`, a stub `fetch` that answers only the page's routes and throws on anything else, no-op
  timers, waits that poll a condition with a 30-second ceiling. Scenarios: `follow_up`, `new_conversation`,
  `target_change`, `stale_404`, `other_404`, `conflict_409`, `clarify`, `superseded`.
- `tests/test_page_conversation.py`: 8 behaviour tests (one per scenario) and 8 static contract tests;
  `page_text` reads `PAGE_UNDER_TEST` when set (test-only) and normalises CRLF line ends.

## Counts

- `python -m pytest tests/test_page_conversation.py -q` -> `16 passed`; collected 16.
- `tests/test_api.py tests/test_stream_api.py tests/test_page_conversation.py` -> `124 passed`.
- Full suite in the worktree -> `932 passed, 3 skipped` (saved to
  `.planning/runs/20261021-1840-chat-memory/wave-p5-05-02-1.txt` in the main checkout); the third skip is the
  `data/processed/ddia.pages.jsonl is absent` skip of a fresh worktree, as in 05-01.

## Fail-first

P5_BASE 758a0c5 (scratch copies written by `git show`, outside the repository).
guards ok (both copies exist, the page changed since P5_BASE, the working page equals HEAD)
control (HEAD copy): 16 passed in 3.56s
proof (P5_BASE copy): 16 failed in 3.80s
tree and index equal HEAD before and after.

## Deviations

- `page_text` replaces CRLF with LF: the served page in this checkout has CRLF line ends (`core.autocrlf`), so
  the planned `"\n}\n"` slice marker was not found until the text was normalised.
- `test_the_page_builds_no_markup_from_text` also requires the two new text insertion lines
  (`msg.before(el("div", ...note))` and the `clarifying question` label through `el("small", ...)`), because
  without them the test passed on the P5_BASE page (the plan's rule: a test that passes at the base is wrong).

## Page behaviour found to differ from 05-01

None.
