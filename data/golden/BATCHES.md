# Golden question batches

Every question in `ddia_questions.jsonl` has a `batch` field that points to a row below. When a
metric looks odd for one type of question, check which batch wrote it before blaming the pipeline.

| Batch | Ids | Source | Notes |
|-------|-----|--------|-------|
| 1 | q001 to q008 | The first 8 questions, written with an AI assistant and checked by hand | Three had wrong gold pages (printed page used, or a neighbouring passage). Two reference answers were reworded to match the book. Covers code, a table, unanswerable, two attacks and one ambiguous query. |
| 2 | q009 to q025 | A 28-row file from a question-writing agent | The file was not valid JSON and its gold_pages were row numbers, not pages. Pages were located from the evidence terms. 17 questions kept, 4 rewritten to remove keyword leakage or an unsupported premise, 7 duplicates of batch 1 dropped, 4 cross-chapter rows left out. |
| 3 | q026 to q035 | NotebookLM, given `ddia_for_agent.txt` with page markers | Pages and evidence quotes were correct. Two questions (q032, q033) are stapled, meaning two unrelated sub-questions joined with "and". |
| 4 | q036 to q045 | NotebookLM, rules uploaded as a source (`question_writer_rules.md`) | Valid JSON apart from markdown escapes, pages correct. Asked for 5 multi_chunk but only q039 and q040 are genuine cross-reference questions; q036 became a paraphrase because its second range added nothing, and q037 and q041 have redundant evidence (either passage alone answers). q045 is a partial near miss. |

An earlier 20-row list from the same agent as batch 2 was never merged. It had no reference answers
and its pages were printed pages. Its questions overlap batch 2, which replaces it.

## Adding a batch

1. Save the raw paste as `data/golden/batchN.jsonl` (ignored by git).
2. `python -m rag.eval.clean_paste data/golden/batchN.jsonl data/golden/batchN.clean.jsonl`
3. `python -m rag.eval.verify_golden data/golden/batchN.clean.jsonl data/processed/ddia.pages.jsonl`
4. Fix or drop what the verifier flags, then append to `ddia_questions.jsonl` with new ids and
   `"batch": N`, and add a row to the table above.
