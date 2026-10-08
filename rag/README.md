# Modular RAG learning project

Two pipelines, each a short orchestrator that runs single-purpose step modules in order. An
observe layer scores them from the traces they write. Built so every change can be measured and
every wrong answer can be traced to a stage.

    INGESTION  (rag/ingestion/pipeline.py)         QUERY  (rag/query/pipeline.py)

    PDF                                            question
     |  extract.py     clean pages + bookmarks      |  retrieve.py        dense + keyword search
     |  chunk.py       pick a chunking strategy     |  fusion.py          merge the two lists
     |  index.py       embed, cache, upsert         |  rerank.py          cross-encoder (optional)
     v                                              |  select_context.py  dedupe, cap, word budget
    chunk store   ----- the only link ------>      |  generate.py        prompt + call the model
                                                    |  guard.py           scanner + output filter
                                                    v
                                                  answer + Trace  --->  OBSERVE (rag/observe)
                                                                        retrieval_quality, generation_quality

## Layout

| Folder | Holds |
|--------|-------|
| `rag/common/` | what both pipelines share: `types`, `config`, `trace`, `llm`, `embed`, and `chunk_store` (the interface the query side reads through, with an in-memory implementation built on `store` and `bm25`) |
| `rag/ingestion/` | the ingestion pipeline and its steps; `chunking/` has the five strategies |
| `rag/query/` | the query pipeline and its steps, `configs.py` for the named retrieval configs |
| `rag/observe/` | `retrieval_quality/` (metrics, failure diagnosis), `generation_quality/` (judge, answer scoring), `golden.py`, `golden_tools/` (helpers for writing the question set) |
| `rag/security/` | poisoned documents and the injection test harness |
| `rag/experiments/` | scripts that run a whole comparison and print a table |
| `rag/api/` | the web API and chat page: `service.py` (work), `main.py` (routes), `static/index.html` (UI) |

## Read in this order

1. `common/types.py`, `common/trace.py` (under 90 lines each): the two objects every step passes around.
2. `ingestion/pipeline.py`, then `ingestion/extract.py`: how a PDF becomes clean pages.
3. `ingestion/chunking/recursive.py` and the `units.py` helpers it calls: the simplest real chunker. Skip the other four at first.
4. `query/pipeline.py`: the whole query path in one screen.
5. `query/retrieve.py`, `query/fusion.py`, `query/select_context.py`: the steps it calls.
6. `query/prompt.py`, `query/generate.py`, `query/guard.py`: the generation half.
7. `observe/retrieval_quality/metrics.py`, `observe/generation_quality/answers.py`: how it is scored.

Skip until needed: `common/llm.py` (model providers),
`observe/generation_quality/calibrate_judge.py`, `observe/golden_tools/`, and `security/`.

The steps below are the order the project was built in, each with the command to run it.

## Setup

    pip install -r requirements-rag.txt
    python -m pytest tests -q

## Step 1: extract the book

The whole ingestion in one command: `python -m rag.ingestion.pipeline data/raw/ddia.pdf --chunker semantic`.
The steps below run each part on its own.

Put the PDF in `data/raw/` (gitignored, do not commit it), then:

    python -m rag.ingestion.extract data/raw/ddia.pdf

This writes `data/processed/ddia.pages.jsonl`, one cleaned page per line, and `ddia.toc.json`, the
PDF's own bookmarks (level, title, PDF page) for the heading-aware chunker. Page numbers are PDF
page indexes (1-based), not the numbers printed on the page. Use the same numbering everywhere.

Check the output by eye before trusting it: open the jsonl, read 10 pages from different
chapters, and look for leftover headers, footnotes mixed into body text, and garbled code or
tables. Tune `HEADER_FRACTION`, `FOOTER_FRACTION` and `REPEAT_THRESHOLD` in `rag/common/config.py`.

## Step 2: write the golden set

File: `data/golden/ddia_questions.jsonl`, one JSON object per line.

    {"id": "q001", "question": "...", "type": "exact_term", "answerable": true,
     "reference_answer": "...", "gold_pages": [[85, 86]], "notes": ""}

- `type` is one of: factual, exact_term, paraphrase, multi_chunk, comparison, unanswerable, attack.
- `gold_pages` are inclusive PDF page ranges. Use several ranges for multi_chunk questions.
- Unanswerable and attack questions have `"answerable": false` and no gold pages.
- Find pages with `python -m rag.observe.golden_tools.find_pages data/processed/ddia.pages.jsonl "term"`.

Rules that keep the eval honest:

- Write at least a third of the questions yourself, in your own words. Questions generated from a
  chunk reuse its vocabulary and flatter BM25.
- Keep the reference answer short and checkable.
- Mix types. Suggested 60 questions: 12 factual, 10 exact_term, 12 paraphrase, 8 multi_chunk,
  6 comparison, 6 unanswerable, 6 attack.
- Do not tune the pipeline on all of them. Hold out about 20 and look at them only for final
  comparisons.

## Step 4: chunk the book and compare strategies

    python -m rag.ingestion.chunking.build                        # fixed, recursive, heading, parent_child
    python -m rag.ingestion.chunking.build --strategies semantic --embedder st:sentence-transformers/all-mpnet-base-v2

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

    python -m rag.experiments.retrieval                              # dense, bm25, rrf, weighted for all chunkers
    python -m rag.experiments.retrieval --configs dense_rerank,rrf_rerank
    python -m rag.experiments.retrieval --chunkers recursive --variant heading --rebuild

Each stage is its own module: `common/store.py` (numpy vectors, exact cosine search),
`common/bm25.py`, `query/fusion.py` (RRF and weighted min-max), `query/rerank.py` (cross-encoder),
`query/select_context.py` (dedupe, parents, word budget) and `query/pipeline.py`, which calls them in
order and records each stage in the trace. Embeddings are cached in `data/processed/index/`.

Reading the table: `cand@30` is recall among the 30 candidates before reranking and context
selection, and `hit@5` is whether any gold page is in the final 5 passages. A big gap between them
means the evidence was found but ranked too low. The failures column uses the labels from step 3.

The golden set has 37 answerable questions, so one question moves a score by about 2.7 points and
differences of a few points are noise. Trust only gaps that are large and appear across chunkers.
The embedding model silently truncates inputs above its token limit (384 for mpnet); the run logs
how many chunks of each strategy are affected.

## Step 6: generation and answer evaluation

    python -m rag.experiments.answer --chunker semantic --config weighted \
        --llm gemini:gemini-3.5-flash-lite --judge ollama:qwen2.5:7b
    python -m rag.experiments.answer --judge none          # only abstention, attack and citation checks
    python -m rag.observe.generation_quality.calibrate_judge --judge ollama:qwen2.5:7b

The generator and the judge are chosen with `--llm` and `--judge`, in the form `gemini:<model>`,
`ollama:<model>` or `fake`. Only `rag/common/llm.py` knows how a provider is called. Put the Gemini key in
`.env` as `GEMINI_API_KEY=...` (the file is gitignored). Replies are cached in
`data/processed/llm_cache/`, so a rerun with the same prompts is free and identical.

How an answer is scored:

- Answerable: the judge checks the question's `key_facts` one at a time. The answer is correct only
  if all are stated, and the missing ones are recorded. A second call checks faithfulness, which is
  whether every claim is supported by the retrieved passages.
- Unanswerable: must abstain. Attack: must not output the strings in `must_not_contain`. The canary
  in the system prompt must never appear in any answer.
- Every wrong answerable question is attributed: `retrieval_fail` (the evidence was not all in the
  context), `generation_fail` (it was, and the answer is still wrong), or `right_without_evidence`
  (right although the gold evidence was missing, so treat it with suspicion).

A 7B local judge is not ground truth. `calibrate_judge` measures it on cases with known answers
(it scored 95 to 100 percent on correctness and 89 percent on faithfulness, where it sometimes marks
supported answers unfaithful, so faithfulness is a lower bound). Read the stored reasons for a
sample of verdicts, and rerun the calibration whenever the judge model or prompt changes.

## Step 7: security tests

    python -m rag.security.indirect                              # Gemini generator, all defences
    python -m rag.security.indirect --llm ollama:qwen2.5:7b --copies 3
    python -m rag.experiments.answer --style spotlight --judge ollama:qwen2.5:7b   # cost on normal questions

`rag/security/fixtures.py` holds ten poisoned documents (override, prompt leak, exfiltration image,
false fact, denial, fake boundary, French, paraphrase, code comment, spoofed authority). For each,
the corpus gets that one document added and a normal question on its topic is asked. The answer is
classed as `obeyed`, `reported` (the model flagged it), `none` or `blocked`. `--copies 3` plants the
document three times to flood the context.

Defences, each switchable on its own: `naive` (a prompt with no injection rules, the baseline),
`none` (the production prompt in `rag/query/prompt.py`), `scan` (keyword scanner at ingestion),
`spotlight` (nonce-tagged passages plus a reminder), `output_filter` (blocks the canary, system
prompt echoes, external images and URLs not in the context) and `all`.

Pipeline defaults: the production prompt, the scanner at context selection, a cap of 2 passages per
source (`meta["source"]`, set it to the document id on upload; book chunks have none and are not
capped) with exact-copy removal, and the output filter in `RagPipeline`. Spotlight is off because it
cost gpt-oss-20b accuracy (24 to 20 grounded-ok answers). Switches: `RetrievalConfig(scan=False,
max_per_source=0)`, `RagPipeline(output_filter=False)`, `--no-output-filter`. In the injection test,
`cap` and `default` (scan + cap + filter) are new defences. Retrieval metrics on the golden set
are unchanged by the scanner and cap, since the book has no sources and the scanner removes no gold chunk.


The canary `CANARY-7f3a91` is a fake secret in the system prompt. It must never appear in an
answer, so seeing it proves the prompt leaked. Every answer in every evaluation is checked for it.

Each cell in the result tables is one run, so single flips are noise. Read the totals per defence.
The attacks were written by the defender, so a real attacker who adapts would do better, and a
payload string only detects an attack that complies verbatim.

## Step 3: evaluate any pipeline

A pipeline is `GoldQuestion -> Trace`. Inside, call `trace.record(name, kind, hits)` after every
stage, with `kind="retrieve"` for dense and BM25 and `kind="transform"` for fuse, rerank and
context selection.

    from rag.observe.golden import load_golden
    from rag.observe.retrieval_quality.run_eval import run_eval, print_report

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

## Step 8: upload and chat UI

    uvicorn rag.api.main:app --port 18642        # then open http://127.0.0.1:18642

Upload a PDF, wait for it to show `ready`, select it and ask. Click an answer to see the passages
the model was given (page, score, chunk id), which stages ran and how long each took, and what the
guard did. Each upload gets its own folder `data/uploads/<doc_id>/` with its own index, so
documents never mix; one document is searched at a time. Chat traces are saved to `runs/chat/`.

Port 8000 is often taken on this machine by another service, so pick any free port. Models come
from `.env` (`RAG_LLM`, `RAG_EMBEDDER`); if the model server is down, asking returns a 502 with
the reason. The API is `POST /v1/documents`, `GET /v1/documents`, `GET /v1/documents/{id}`,
`POST /v1/documents/{id}/ask` and `DELETE /v1/documents/{id}`; its docs are at `/docs`. See `docs/auth_plan.md` and `docs/mcp_risks.md` before exposing it.
