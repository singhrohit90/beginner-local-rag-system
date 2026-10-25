---
phase: 03-rewrite-clarify-and-topic-switch
plan: 01
subsystem: query
tags: [rewrite, clarify, topic-switch, guards]
requires: [rag.query.history (Phase 1), rag.api.conversations (Phase 2)]
provides: [rag/query/rewrite.py]
affects: [plans 03-04 to 03-07]
key-files:
  created: [rag/query/rewrite.py]
  modified: []
decisions: [A4 as built, A7 as built, A11 as built, D-09 total function]
metrics:
  tasks: 3
  commits: 3
---

# Phase 3 Plan 01: rewrite module Summary

Pure module `rag/query/rewrite.py`: deterministic gate, one tagged-line rewriter call, deterministic guards, and a total `rewrite_question` that turns every failure into a coded `fallback`.

## Phase 3 base

P3_BASE=d65b26860d4de95ba5fd062cf28b1e5ad210ef0d
2026-10-25, docs(02): mark phase 2 complete

Taken with `git status --porcelain -- rag tests` empty, before any Phase 3 code commit. At this commit `rag/query/rewrite.py` does not exist and `rag/api/conversations.py` has no `since_topic_start`.

## Commits

| Task | Commit | Subject |
|------|--------|---------|
| 1 | f155fdc218d86511ac566dcf7ddf52deb290fcd6 | feat(03-01): rewrite a pronoun follow-up into a standalone question |
| 2 | 8c3f90db6c79d9a1e9885de1a472e36de35241b5 | feat(03-01): reject rewrites that invent, drop constraints, leak a topic or run long |
| 3 | 96c1f25a9e5839a6814fd6f4d1c9478971aee78d | feat(03-01): never fail a question because the rewriter failed |

## Verification

| Verify line | Result | Fail-first (state before the task's code) |
|-------------|--------|-------------------------------------------|
| `phase 2 contract ok` | printed | n/a (precondition check) |
| `base ok` | printed | n/a |
| `rewrite tracer ok` | printed | `ModuleNotFoundError: No module named 'rag.query.rewrite'` at P3_BASE |
| `guards ok` | printed | after Task 1: AssertionError, all eight bad rewrites accepted as `rewritten` |
| `outcomes ok` | printed | after Task 2: `URLError` escaped `rewrite_question` |
| `total ok` | printed | already passed after Task 2 (a totality check, not a new behaviour) |
| `real client ok ['unavailable', 'timeout', 'timeout']` | printed | after Task 2: `RuntimeError: cannot reach Ollama ...` escaped |

Acceptance greps: no `from rag.api`, `open(`, `json_mode=`, `temperature=`, `cache_dir=`, `from __future__` or `| None` in the module; exactly one `except Exception`; `str(err)` count 0 (classification reads `str(link)` inside `classify_failure` only); 10 quoted guard-reason literals; `git diff --quiet P3_BASE -- rag/query/prompt.py rag/query/history.py rag/query/guard.py rag/query/generate.py rag/query/pipeline.py requirements-rag.txt` exits 0; no line over 120 characters.

Full suite: 741 passed, 2 skipped (see "Full suite" below).

## Real Ollama client failure shapes

Characterised with `get_llm("ollama:qwen2.5:7b", cache_dir=None)` and `urllib.request.urlopen` patched (the provider module was not read or named):

| Raised by urlopen | What reaches rewrite_question | Timeout in the chain | Classified |
|-------------------|-------------------------------|----------------------|------------|
| `URLError(ConnectionRefusedError())` | `RuntimeError` ("cannot reach Ollama at ... (). Is ollama serve running ..."), `__cause__` the URLError | no | `unavailable` |
| `socket.timeout("timed out")` | the `socket.timeout` itself (a `TimeoutError` on 3.10; the client catches only URLError) | it is the error | `timeout` |
| `URLError(socket.timeout("timed out"))` | `RuntimeError("... (timed out) ...")`, `__cause__` URLError whose `reason` is the timeout | yes (message and cause) | `timeout` |

`classify_failure` needed no extension beyond RESEARCH Code Example 5.

## System prompts

- `REWRITE_SYSTEM_PROMPT`: 232 words.
- `REWRITE_SYSTEM_PROMPT_NO_CLARIFY`: 204 words (same `_PROMPT_LINES` tuple with every line containing `CLARIFY` dropped).
- Examples are hand-written (capital of France population follow-up; "What is a mutex?" -> STANDALONE), none from `data/golden`. The prompt says the conversation and document list are quoted text, not instructions, and that there are no passages in this task.

## Resolutions as built

- **A4:** `clean_doc_names` keeps at most 8 names, whitespace-collapsed, `"` replaced by `'`, cut to 60 characters, scanner-flagged names dropped. They appear on a `Documents: "a"; "b"` first line of the user prompt (omitted when none survive), and since `shown` is the whole user prompt they are in the `invented_detail` vocabulary; the tracer and the `guards ok` good case resolve "the other book" to `Paxos-notes.pdf`.
- **A7:** `REWRITE_PROMPT_MAX_WORDS = 900`; an assembled system plus user prompt over it returns `fallback` / `input_too_long` before any call (checked with the 1002-word message in `outcomes ok`).
- **A11:** a guard-rejected `REWRITE:` payload is kept as `RewriteResult.rejected_question`; a rejected `CLARIFY:` text is not kept. `as_response()` returns only `status`, `reason`, `rewritten_question`.
- **D-09:** the only `except Exception` wraps `llm.generate`; it logs the reason code and the exception class name only.

## Deviations from Plan

None in behaviour. Two small implementation choices:
- `parse_reply` returns `("empty", "")` explicitly when there is no non-empty line (the RESEARCH sketch returned `unparsed` there; the plan truth says `empty`).
- The sentence-start test for skipping a capitalised starter word uses a private `_sentence_start` helper (strip trailing whitespace before the word and check for `.`, `!` or `?`) instead of a regex search over the prefix, so a long payload cannot cost quadratic time.

## Known limits (not hidden)

A wrong pick between two entities both in the window is accepted (plan 03-05 characterises it); lowercase invented context; a spelled-out number; a capitalised non-ASCII name; a constraint outside the D-07 word list. A false rejection (for example "Multi-Paxos" when only "Paxos" was shown) falls back to the raw message.

## Full suite

`python -m pytest tests -q` on commit 96c1f25: 741 passed, 2 skipped in 206.21s (baseline 741 passed, 2 skipped; this plan adds no test file, plan 03-05 adds tests/test_rewrite.py).
