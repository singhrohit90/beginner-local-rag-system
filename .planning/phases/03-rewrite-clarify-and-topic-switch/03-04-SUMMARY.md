---
phase: 03-rewrite-clarify-and-topic-switch
plan: 04
requirements: [RWR-01, RWR-02, RWR-03, RWR-04]
files_modified:
  - rag/api/service.py
  - rag/api/main.py
  - .env.example
status: complete
---

# 03-04 Summary: the rewrite step, clarify and topic switch wired behind RAG_REWRITE

START=55c3cb1 (branch work/03-04, cut from flow/chat-memory); P3_BASE=d65b26860d4de95ba5fd062cf28b1e5ad210ef0d

## What was built

- `rag/api/service.py`:
  - `DocumentService(..., rewrite: bool = False, rewrite_llm: Optional[LLM] = None)`, after `conversations`. `rewrite=True` with no rewriter raises `ValueError("rewrite needs a rewrite_llm")` at construction (orchestrator resolution: never a silent default to the answer model).
  - `_rewrite(question, turns, names) -> Tuple[RewriteResult, List[HistoryTurn]]`. Switch off: `RewriteResult("off", question)` and Phase 2's window exactly (stored `kind` and `topic_start` ignored). Switch on: window cut by `since_topic_start`, `needs_rewrite` gate (`skipped` with no model call), `allow_clarify` False when the last stored turn is a clarification (D-13), one `rewrite_question(self.rewrite_llm, ...)` call; `new_topic` shows no earlier turn (D-14).
  - `_retrieve` builds `info` once, before retrieval (`info = {...}`), adds `rewrite`, then on `clarify` returns `(None, None, info)` with `query_id` `clarify-<ms>`, `clarify` and `history_block` "". Otherwise `retrieval.run(query_id, result.question, CONFIGS[config])`, the block rendered after the decision, the prompt-budget check on `trace.question`, and `return rag, trace, info` (the same dict).
  - With the switch on, `trace.config["conversation"]` gains `original_question`, `rewritten_question`, `rewrite`, `fallback_reason`, `rewrite_ms`, `rejected_question` (A11: trace only, never the response). With it off, the four Phase 2 keys only.
  - `_describe` adds `"kind": "answer"` and `"rewrite": info["rewrite"].as_response()`.
  - `_clarify_response(info)`: the normal shape built from info only, `filter_output(info["clarify"], "")`, `kind` "clarify", `llm` = `self.rewrite_llm.name`, empty passages/citations/stages, no context-stage read.
  - `_remember` stores `rewritten` (accepted rewrite only), `kind` from the result and `topic_start` on `new_topic`; with the switch off a stored turn keeps the seven Phase 2 keys.
  - `ask_documents` returns the clarify response after storing it (lease released by the existing `finally`). `ask_documents_stream` stores it and releases the lease in a `finally`, then returns a one-event generator `clarified()` (final, `replace: False`, no token event).
- `rag/api/main.py` `build_default_service`: `rewrite = setting("RAG_REWRITE", "") == "1"`; `rewrite_llm = get_llm(setting("RAG_REWRITER", "ollama:qwen2.5:7b"), cache_dir=None) if rewrite else None`; passes `rewrite=rewrite, rewrite_llm=rewrite_llm`. No route, request model or `guarded()` change.
- `.env.example`: commented `# RAG_REWRITE=` and `# RAG_REWRITER=` with no values, the default `ollama:qwen2.5:7b` and the `OLLAMA_KEEP_ALIVE` cold-load note.

## Decisions as built

- **D-09 (fail-open with a visible flag):** a rewriter error, timeout, empty or unparsable reply or a failed guard never fails the request; retrieval runs on the raw message and the response and final event carry `"rewrite": {"status": "fallback", "reason": <code>, "rewritten_question": null}`. RWR-02's literal text favours an HTTP status; ROADMAP Phase 3 criterion 3 allows "an HTTP status before any SSE byte, or a flagged fall-back to the raw message". The decision is made inside `_retrieve`, before any SSE byte.
- **A11:** `rejected_question` lives in `trace.config["conversation"]` only (traces are saved only for single-document questions, inside the document folder).
- **ValueError:** `rewrite=True` without `rewrite_llm` raises at construction.
- **Clarify on the stream:** a generator (`def clarified()`), not `iter([...])`, because the route's `frames()` calls `events.close()` (correction of RESEARCH Code Example 8).

## Deviations

- `build_default_service` now builds the answer model into a local `llm` before the rewriter (it used to be built inline in the `DocumentService(...)` call). Reason: the plan's settings check asserts the last `get_llm` call is the rewriter's; the arguments are unchanged and still pass `cache_dir=None`.
- The `_rewrite` signature line is 133 characters, over the 120 guideline, because the acceptance criterion greps for the signature on one line.
- The plan's verify one-liners were run as scripts in the scratchpad under `if __name__ == "__main__":`, with the same assertions; ingestion's extraction sandbox spawns child processes, which fail without the guard.

## Commits

- `5e13486` feat(03-04): retrieve on the rewritten follow-up behind RAG_REWRITE
- `566f641` feat(03-04): ask one clarifying question and start a clean history on a new topic
- `62040f2` feat(03-04): document RAG_REWRITE and RAG_REWRITER and pin the switch-off contract

## Verification

- Before any edit (at 55c3cb1) all four check scripts failed: `TypeError: DocumentService.__init__() got an unexpected keyword argument 'rewrite'` (tracer, clarify), `'rewrite_llm'` (switch off and fallback), `AttributeError: 'DocumentService' object has no attribute 'rewrite'` (settings).
- Task 1 fail-first (rag stashed as `p0304-task1-a7f3`, run, popped): tracer `TypeError ... 'rewrite'`; settings `AttributeError ... 'rewrite'`. On new code: `service tracer ok`, `needs a rewriter ok`, `settings ok`; `pytest tests/test_api.py tests/test_stream_api.py tests/test_conversations.py tests/test_prompt_snapshot.py -q` gave `212 passed`.
- Task 1 acceptance: every `get_llm(` line under rag/api carries `cache_dir=None`; first match in `_retrieve` is `info = {`; `return rag, trace, info$` count 1; all literal strings present in both files.
- Task 2 fail-first (Task 2 edits stashed as `p0304-task2-c91e`, run, popped): `AssertionError` with `kind` "answer" and a retrieval on the clarify path. On new code: `clarify ok`, `topic and stream clarify ok`; `pytest tests/test_api.py tests/test_stream_api.py tests/test_conversations.py tests/test_stream_guard.py -q` gave `404 passed`.
- Extra check: a clarification through `POST /v1/documents/{id}/ask/stream` gives one `final` frame with kind "clarify", and the next request is 200 (lease released) with `rewrite.reason` "unparsed" (`http stream clarify ok`).
- Task 2 acceptance: `stage("context")` count 0 in `_clarify_response`..`ask_documents`; no `iter([` in `ask_documents_stream`.
- Task 3: `settings ok`, `env example ok`, `switch off ok`, `fallback ok`. AskRequest grep for history/turns/kind/rewrite/topic gave 0; no 403 or request-owner pattern in main.py; `git diff --quiet P3_BASE -- rag/query/prompt.py rag/query/generate.py rag/query/pipeline.py rag/query/guard.py rag/query/history.py rag/api/static/index.html requirements-rag.txt` exits 0; `rag/query/rewrite.py` and `tests/` unchanged since 55c3cb1.
- Full suite: `python -m pytest tests -q` gave `741 passed, 2 skipped` (baseline at the branch point 741 passed, 2 skipped).
