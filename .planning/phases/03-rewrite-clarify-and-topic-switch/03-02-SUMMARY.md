---
phase: 03-rewrite-clarify-and-topic-switch
plan: 02
requirements: [RWR-03, RWR-04]
files_modified:
  - rag/api/conversations.py
status: complete
---

# 03-02 Summary: turn kind, topic start and the topic cut

START=d65b26860d4de95ba5fd062cf28b1e5ad210ef0d

## What was built

- `rag/api/conversations.py`:
  - `TURN_KINDS = ("answer", "clarify")`. A clarification is stored as a turn, so the next turn knows not to ask for clarification again (D-13).
  - `new_turn(question, answer, doc_ids, query_id, rewritten=None, kind="answer", topic_start=False)`.
    - `"kind"` is added only when the value is `"clarify"`, and `"topic_start": True` is added only when the value is true.
    - A default turn keeps exactly the seven Phase 2 keys.
    - An unknown kind raises `ValueError(f"unknown turn kind {kind!r}")`.
  - `since_topic_start(turns)` is a pure function. It returns a new list that starts at the most recent `topic_start` turn (inclusive), or all turns when no turn has the flag.
  - The module docstring now describes the two optional keys.
  - `FORMAT_VERSION`, `ConversationStore`, `to_history_turns`, `owner_key` and `scope_of` are unchanged.

## Commits

- `d5eb10dab4b3aab8a2030171a166a188a47fa54f` feat(03-02): store a clarification and a topic start on the turn
- `f243498b0034b5618b42435bab5f47d3c6cdf5be` feat(03-02): cut the history at the latest topic start

## Verification

The plan's verify one-liners were run as scripts in the scratchpad, with the same assertions.

- Task 1 fail-first: on old code (rag stashed under a unique message, run, then popped) the check gave `ImportError: cannot import name 'TURN_KINDS'`.
  - On new code it printed `turn kinds ok`.
- Task 1 Phase 2 suites: `python -m pytest tests/test_conversations.py tests/test_api.py tests/test_stream_api.py -q` gave `134 passed`.
- Task 2 fail-first: run after Task 1 and before the edit, the check gave `ImportError: cannot import name 'since_topic_start'`.
  - On new code it printed `topic cut ok`.
- Task 2 Phase 2 suite: `python -m pytest tests/test_conversations.py -q` gave `26 passed`.
- Acceptance checks:
  - `git diff --quiet $START -- rag/query/history.py tests/test_conversations.py tests/test_api.py tests/test_stream_api.py rag/query/prompt.py` exits 0.
  - No diff line in `rag/api/conversations.py` touches `FORMAT_VERSION`.
- Full suite: recorded in the final report of the run, not in this file. It was still running when this summary was committed.

## Decisions

- Only non-default keys are stored. The Phase 2 exact-key tests stay true with no edits.
- Assumption-delta: the noun "turn" now has two kinds. Decision: add the new key alongside the Phase 2 shape, accepted as debt. A turn without the key reads as `turn.get("kind", "answer")` and `turn.get("topic_start", False)`.
  - What forces a promote, so that every turn always carries `kind`: the page or a reload view needs to render a stored clarification differently (Phase 5 PAGE-02, or v2 reload-resume).
  - That promote would update the Phase 2 key-set tests in the same commit.
- `since_topic_start` lives in `conversations.py`, not `rag/query/history.py`. It reads stored dicts, and `window()` must keep accepting plain items.

## Deviations

- None in code.
- The run paused once because the shell's safety classifier was unavailable. It was resumed with no change to the work.
