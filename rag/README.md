# Modular RAG learning project

Each stage is a separate module so you can see exactly when it is called. Built so every change
can be measured and every wrong answer can be traced to a stage.

## Status

| Step | Module | State |
|------|--------|-------|
| 1 | `rag/ingest` PDF extraction and cleaning | done |
| 2 | `rag/eval/golden.py` golden question format | done, questions still to be written |
| 3 | `rag/trace.py`, `rag/eval/{metrics,diagnose,run_eval}.py` | done |
| 4 | `rag/chunking` fixed, recursive, semantic, heading-aware, parent-child | done; semantic still to be built with a real embedder |
| 5 | `rag/retrieval` dense, BM25, fusion, rerank, context selection; `rag/experiment.py` | done, no LLM yet |
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

## Step 4: chunk the book and compare strategies

    python -m rag.chunking.build                        # fixed, recursive, heading, parent_child
    python -m rag.chunking.build --strategies semantic --embedder st:sentence-transformers/all-mpnet-base-v2

The body is PDF pages 23 to 574. The glossary and index are left out because they repeat technical
terms beside page numbers and would match keyword queries without holding an answer. Chunk sizes
are counted in words for every strategy. Output goes to `data/processed/chunks/`.

The comparison table needs no retrieval. `%midS` and `%midE` are chunks that start or end
mid-sentence, `badcode` counts code fences cut in half, and `intact` is the share of golden
questions whose evidence terms still sit together in one chunk. `intact` is generous: a large
chunk passes easily, so read it with the size columns. The real comparison is retrieval and answer
quality from the eval harness.

Semantic chunking needs the extras: `pip install sentence-transformers` (pulls in torch).

## Step 5: retrieval experiments

    python -m rag.experiment                              # dense, bm25, rrf, weighted for all chunkers
    python -m rag.experiment --configs dense_rerank,rrf_rerank
    python -m rag.experiment --chunkers recursive --variant heading --rebuild

Each stage is its own module in `rag/retrieval/`: `store.py` (numpy vectors, exact cosine search),
`bm25.py`, `fusion.py` (RRF and weighted min-max), `rerank.py` (cross-encoder), `select.py` (dedupe,
parents, word budget) and `pipeline.py`, which calls them in order and records each stage in the
trace. Embeddings are cached in `data/processed/index/`.

Reading the table: `cand@30` is recall among the 30 candidates before reranking and context
selection, and `hit@5` is whether any gold page is in the final 5 passages. A big gap between them
means the evidence was found but ranked too low. The failures column uses the labels from step 3.

The golden set has 37 answerable questions, so one question moves a score by about 2.7 points and
differences of a few points are noise. Trust only gaps that are large and appear across chunkers.
The embedding model silently truncates inputs above its token limit (384 for mpnet); the run logs
how many chunks of each strategy are affected.

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
