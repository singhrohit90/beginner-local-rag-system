# Modular RAG learning project

Each stage is a separate module so you can see exactly when it is called. Built so every change
can be measured and every wrong answer can be traced to a stage.

## Status

| Step | Module | State |
|------|--------|-------|
| 1 | `rag/ingest` PDF extraction and cleaning | done |
| 2 | `rag/eval/golden.py` golden question format | done, questions still to be written |
| 3 | `rag/trace.py`, `rag/eval/{metrics,diagnose,run_eval}.py` | done |
| 4 | chunkers (fixed, recursive, semantic, heading-aware, parent-child) | next |
| 5 | dense, BM25, fusion, rerank, context selection | |
| 6 | generation and answer judge | |
| 7 | security tests (injection, poisoning, access control) | |

## Setup

    pip install -r requirements-rag.txt
    python -m pytest tests -q

## Step 1: extract the book

Put the PDF in `data/raw/` (gitignored, do not commit it), then:

    python -m rag.ingest.extract data/raw/ddia.pdf

This writes `data/processed/ddia.pages.jsonl`, one cleaned page per line, and `ddia.toc.json`, the
PDF's own bookmarks (level, title, PDF page) for the heading-aware chunker. Page numbers are PDF
page indexes (1-based), not the numbers printed on the page. Use the same numbering everywhere.

Check the output by eye before trusting it: open the jsonl, read 10 pages from different
chapters, and look for leftover headers, footnotes mixed into body text, and garbled code or
tables. Tune `HEADER_FRACTION`, `FOOTER_FRACTION` and `REPEAT_THRESHOLD` in `rag/config.py`.

## Step 2: write the golden set

File: `data/golden/ddia_questions.jsonl`, one JSON object per line.

    {"id": "q001", "question": "...", "type": "exact_term", "answerable": true,
     "reference_answer": "...", "gold_pages": [[85, 86]], "notes": ""}

- `type` is one of: factual, exact_term, paraphrase, multi_chunk, comparison, unanswerable, attack.
- `gold_pages` are inclusive PDF page ranges. Use several ranges for multi_chunk questions.
- Unanswerable and attack questions have `"answerable": false` and no gold pages.
- Find pages with `python -m rag.eval.find_pages data/processed/ddia.pages.jsonl "term"`.

Rules that keep the eval honest:

- Write at least a third of the questions yourself, in your own words. Questions generated from a
  chunk reuse its vocabulary and flatter BM25.
- Keep the reference answer short and checkable.
- Mix types. Suggested 60 questions: 12 factual, 10 exact_term, 12 paraphrase, 8 multi_chunk,
  6 comparison, 6 unanswerable, 6 attack.
- Do not tune the pipeline on all of them. Hold out about 20 and look at them only for final
  comparisons.

## Step 3: evaluate any pipeline

A pipeline is `GoldQuestion -> Trace`. Inside, call `trace.record(name, kind, hits)` after every
stage, with `kind="retrieve"` for dense and BM25 and `kind="transform"` for fuse, rerank and
context selection.

    from rag.eval.golden import load_golden
    from rag.eval.run_eval import run_eval, print_report

    report = run_eval(load_golden(path), my_pipeline, run_name="fixed_dense_only")
    print_report(report)

Output in `runs/<run_name>/`: one trace per question, `per_question.jsonl`, and `report.json`.

`failure_counts` in the report is the first thing to read. Labels:

- `retrieval_miss`: no retriever surfaced the gold pages. Look at extraction, chunking, k, query.
- `lost_at_<stage>`: an earlier stage had it and this stage dropped it. Fix that stage.
- `retrieval_ok`: gold survived to the end, so a wrong answer is a prompt or generation problem,
  or the gold label is wrong. Check the label before blaming the pipeline.

Metric notes:

- A chunk is relevant if its page range overlaps a gold range. Each gold range is credited once, so
  duplicate chunks from one page do not inflate recall or nDCG.
- Small chunks are not penalised for being small and large chunks are not rewarded for being large,
  except through page-range overlap. A very large chunk spanning many pages will overlap gold by
  accident. Watch chunk page spans when comparing chunkers.
- Page-level labels cannot tell whether the exact sentence was in the chunk. Add a text-containment
  check later if you need that precision.
