---
phase: 04-multi-turn-evaluation-and-the-default-decision
plan: 09
status: complete
requirements: [EVAL-03]
---

# 04-09 Summary: the default follows the recorded decision

Recorded lines (docs/chat_memory_eval.md, Results commit e114e36):

- `Decision: ships off (failed: a, c, f; provisional: items pending human review)`
- `Rewriter chosen: ollama:qwen2.5:7b (qwen by default, not compared)`
- `Question slot: rewritten question (unmeasured: answers not run)`

## Task 1: ships off branch (tests only)

Added to `tests/test_conversation_experiment.py`: imports `build_default_service` and `spied_settings`, constant
`DOC`, helper `recorded(label)`, `test_the_default_matches_the_recorded_decision`,
`test_the_results_file_records_every_decision`. No production file changed.

Fail-first: `setting("RAG_REWRITE", "") == "1"` mutated to `setting("RAG_REWRITE", "1") == "1"` ->
`E       AssertionError: ships off (failed: a, c, f; provisional: items pending human review)` /
`E       assert True is False`; restored with `git checkout HEAD -- rag/api/main.py`, `git diff --quiet HEAD -- rag` ok.

Verify: `2 passed`; switch read matches the decision; every `get_llm(` under rag/api has `cache_dir=None`;
`tests/test_rewrite_api.py` -> `42 passed`.

Commit: aae220a test(04-09): pin the rewrite default to the recorded decision

## Task 2: rewriter default not triggered

rewriter default not triggered: Rewriter chosen is ollama:qwen2.5:7b.

Added `test_the_rewriter_default_matches_the_recorded_choice`. Fail-first: default mutated to
`vllm:/models/gpt-oss-20b` -> `E       AssertionError: assert ('vllm:/model...ss-20b', None) == ('ollama:qwen2.5:7b', None)`;
restored with `git checkout HEAD -- rag/api/main.py`.

Verify: `1 passed`; `tests/test_rewrite_api.py tests/test_conversation_experiment.py` -> `82 passed`.

Commit: c99ad41 test(04-09): pin the rewriter default to the recorded choice

## Task 3: question slot not triggered

question slot not triggered: Question slot: rewritten question (unmeasured: answers not run)

## Full suite

`917 passed, 2 skipped` (worktree, OpenSearch up): `.planning/runs/20261021-1840-chat-memory/wave-p4-04-09-1.txt`.
`git status --porcelain -- rag tests docs .env.example` empty.
