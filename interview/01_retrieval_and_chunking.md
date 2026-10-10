# Interview revision 01: retrieval and chunking

How to use this file. Each section is one interview question. Say the **Short answer** first, then
use **Go deeper** if they keep pushing. **In this repo** is your proof that you built and measured it.

Labels used below:
- "General" = standard interview knowledge, not tied to this repo.
- "Measured here" = a number from a file in this repo; the file is named.
- "Computed from" = I (the note writer) averaged numbers from `runs/*/report.json`; the averages are not written in any doc.
- "Not measured" / "Not built" = honest gaps. Say so in the interview; it scores better than bluffing.

The test bed: one book (Designing Data-Intensive Applications, PDF pages 23 to 574), a golden set in
`data/golden/ddia_questions.jsonl` (45 rows, 37 answerable, 8 unanswerable or attack), embedding
model all-mpnet-base-v2, 30 candidates per retriever, 5 passages in the final context.
One question is 2.7 points (`rag/README.md`, Step 5). Differences under about 8 points are noise
(`CLAUDE.md`, "Behaviour that must not drift").

Pipeline in one line (`rag/query/pipeline.py`, class `RetrievalPipeline`):
dense + bm25 -> fuse -> rerank (optional) -> select_context. Trace stage names: `dense`, `bm25`,
`fuse`, `rerank`, `context`.

Tables of numbers: unless a source is named, hit@5 / MRR come from
`runs/exp__<chunker>__<config>/report.json`, the `context` stage of `per_stage`. Configs are in
`rag/query/configs.py` (`CONFIGS`).

---

## 1. What is chunking and why does it matter?

**Question.** Why do you split documents into chunks before indexing? What goes wrong if chunks are
too big, too small, or cut in the wrong place?

**Short answer.** An embedding model and an LLM context both have limits, and one vector per whole
document blurs everything into an average. Chunking decides the unit of retrieval: what can be
found, how precisely it matches, and how much text the LLM gets. A bad cut (mid-sentence, half a code
block, answer split across two chunks) makes evidence unfindable no matter how good the retriever is.

**Go deeper.**
- General: small chunks match a query precisely but lose surrounding context (pronouns, definitions
  one paragraph up). Large chunks keep context but dilute the embedding and waste the LLM's context
  budget on irrelevant text.
- General: the embedding model has a token limit and silently truncates longer inputs, so the tail of
  a long chunk is never embedded. For mpnet the limit is 384 tokens (`rag/README.md`, Step 5).
- General: chunking is upstream of everything. You cannot fix a split answer with a better reranker.
- Failure example: the fact "X is 5 ms" sits at the start of chunk B, its subject "the leader node" at
  the end of chunk A. Neither chunk alone answers the question.
- Chunk size here is counted in words for every strategy (`rag/ingestion/chunking/units.py` docstring), so strategies are compared at the same size, not mixed words/tokens/characters.

**In this repo.**
- Interface and shared helpers: `rag/ingestion/chunking/base.py` (`ChunkSet`, `load_chunks`),
  `rag/ingestion/chunking/units.py` (`words_of`, `atomic_units`, `pack`, `count_words`).
- Strategy factory: `make_chunker` in `rag/ingestion/chunk.py`; names in `STRATEGIES`.
- Build all and print the comparison table: `python -m rag.ingestion.chunking.build` (`rag/README.md` Step 4).
- Measuring what a chunker did to the text, with no retrieval: `chunk_stats` in
  `rag/ingestion/chunking/stats.py` (mid-sentence starts/ends, broken code fences, pages per chunk).
- Body only: PDF pages 23 to 574. Glossary and index are excluded because they repeat terms next to page numbers and would match keyword queries without holding an answer (`rag/README.md` Step 4).

**Follow-ups.**
1. How would you know a chunker is the cause of a wrong answer? (Section 8, failure labels; section 15.)
2. Do you chunk by tokens or words? (Words here. Token counts only matter for the embedder limit.)
3. What about tables, code, images? (Code fences are kept whole up to `code_max` = 400 words in the recursive, heading, parent_child and semantic chunkers. Tables/images/OCR: not built; `docs/backlog.md`, "Documents with images, tables and scans".)

---

## 2. The five chunking strategies: when does each win, and what did you measure?

**Question.** Name the common chunking strategies. When would you pick each one, and what did your
own measurements show?

**Short answer.** Fixed: a sliding window over words, the cheap baseline that ignores structure.
Recursive: split at paragraph, then sentence, then word boundaries. Heading-aware: one chunk per
document section using the PDF bookmarks. Parent-child: search small chunks, give the LLM the bigger
parent. Semantic: start a new chunk where consecutive sentences become dissimilar. On this book,
heading-aware and semantic were best (hit@5 0.865 with the weighted hybrid), fixed was worst, and
the gaps between the top two are inside the noise.

**Go deeper.**
- General, when each wins:
  - Fixed: logs or text with no structure; fast; needs no parsing. Cuts everything.
  - Recursive: good default for prose; no model needed.
  - Heading-aware: documents with reliable structure (books, manuals, docs). Chunks match how authors group ideas, and the heading path can be used as metadata.
  - Parent-child ("small to big"): when precise matching needs small units but answering needs context. Costs more index rows.
  - Semantic: topic-shifting prose with weak headings. Costs one embedding per sentence at build time, and the threshold (percentile) is another knob.
- Pitfall for parent-child: retrieval returns children, but the LLM sees parents, so the word budget is eaten faster (parents here have a median of 542 words against `max_words` 1500). Inference, not tested here: this is likely why parent_child has the best MRR but not the best hit@5, because fewer distinct passages fit in the context.

Chunk shapes (Computed from `data/processed/chunks/*.jsonl` with `chunk_stats`; `data/processed/` is gitignored but exists on this machine):

| Strategy | Chunks | Words p10 / median / p90 / max | Start mid-sentence | End mid-sentence | Broken code fences |
|---|---|---|---|---|---|
| fixed | 1272 | 200 / 200 / 200 / 200 | 84.0% | 93.8% | 15 |
| recursive | 1285 | 137 / 174 / 196 / 200 | 7.7% | 22.9% | 0 |
| heading | 833 | 147 / 265 / 295 / 300 | 3.7% | 15.2% | 0 |
| parent_child (children) | 2827 | 48 / 77 / 96 / 120 | 4.8% | 16.5% | 0 |
| parent_child (parents) | 448 | 157 / 542 / 592 / 600 | 3.3% | 12.1% | 0 |
| semantic | 988 | 95 / 215 / 293 / 300 | 6.3% | 11.8% | 0 |

Retrieval quality, final 5 passages, 37 answerable questions (Measured here: `runs/exp__<chunker>__<config>/report.json`):

| Chunker | dense | bm25 | rrf | weighted | weighted MRR |
|---|---|---|---|---|---|
| fixed | 0.568 | 0.703 | 0.730 | 0.649 | 0.454 |
| recursive | 0.703 | 0.676 | 0.676 | 0.757 | 0.542 |
| heading | 0.757 | 0.784 | 0.865 | 0.865 | 0.586 |
| parent_child | 0.649 | 0.730 | 0.784 | 0.784 | 0.698 |
| semantic | 0.676 | 0.811 | 0.838 | 0.865 | 0.663 |

Computed from those files, the mean hit@5 over the four configs: fixed 0.663, recursive 0.703,
parent_child 0.737, semantic 0.798, heading 0.818.

How to read it:
- Fixed is worst, which matches its chunk shape: 84% of fixed chunks start mid-sentence and 15 code blocks are cut in half.
- Heading and semantic tie at the top (0.865 weighted). They differ by zero on the hybrid cells, so you cannot rank them. Do not claim one beats the other.
- The ordering of the bottom three flips depending on the config (for example recursive beats semantic on plain dense: 0.703 vs 0.676). Only gaps that persist across configs mean anything. Fixed vs heading does (about 15 points of mean), and is above the 8-point noise band.
- The repo's default is semantic + weighted: `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` must give hit@5 0.865, MRR 0.663 (`CLAUDE.md`, Commands).

**In this repo.**
- `rag/ingestion/chunking/fixed.py` `FixedChunker` (size 200, overlap 40)
- `rag/ingestion/chunking/recursive.py` `RecursiveChunker` (size 200; overlap 40 through `make_chunker`, though the class default is 30; the saved `data/processed/chunks/recursive.jsonl` header says 40)
- `rag/ingestion/chunking/heading.py` `HeadingChunker`, `sections` (min 60, max 300 words, overlap 0; sections found from the PDF bookmarks in `ddia.toc.json`)
- `rag/ingestion/chunking/parent_child.py` `ParentChildChunker` (parents up to 600 words, children 100 words with overlap 20)
- `rag/ingestion/chunking/semantic.py` `SemanticChunker` (85th percentile of sentence-to-sentence distance, min 80, max 300 words)
- Parents are fetched at query time by `get_parents` on the store, then swapped in by `select_context` (section 9).
- `intact` column in the build table: share of golden questions whose evidence terms still sit in one chunk. `rag/README.md` warns it is generous for big chunks.

**Follow-ups.**
1. Why not just use the best one everywhere? (Documents without bookmarks cannot use heading-aware; uploads of unknown PDFs fall back to other strategies. Which strategy uploads use: not checked in this note.)
2. Why does parent-child have the best MRR but lower hit@5? (Section 9 and the inference above; not tested.)
3. Is semantic chunking worth its cost? (One embedding per sentence at build time, and on this book it ties heading-aware, which is free. Within noise, so "no clear win" is the honest answer.)

---

## 3. Chunk size and overlap

**Question.** How do you choose chunk size and overlap?

**Short answer.** Start from the question types and the embedder's token limit, then tune on a golden
set rather than guess. Overlap protects against a fact falling on a boundary, but it duplicates text,
inflates the index and fills the context with near-copies unless you dedupe.

**Go deeper.**
- General: typical starting points are 200 to 500 tokens with 10 to 20 percent overlap. Factoid questions like smaller; multi-step explanations like bigger.
- General: bigger chunks raise recall at a given k (more text per slot) but cost precision and LLM tokens. Bigger chunks also game page-level labels: a chunk spanning many pages overlaps the gold page by accident (`rag/README.md`, Step 3 "Metric notes").
- Overlap trade-off: with size 200 and overlap 40, each word is stored about 1.25 times. Retrieval can return two chunks that share 40 words; context selection then has to drop one.
- Embedder limit: text beyond 384 tokens is never embedded for mpnet. Heading and semantic chunks go up to 300 words, which can exceed 384 tokens when text is code-heavy. The run logs how many chunks are affected, but the count is not recorded in any doc, so I do not quote it.

**In this repo.**
- Size and overlap defaults: `make_chunker` in `rag/ingestion/chunk.py`.
- Overlap removal at query time: `_overlap` and `overlap_threshold` (0.5) in `rag/query/select_context.py`.
- Truncation check: `SentenceTransformerEmbedder.max_tokens` and `count_tokens` in `rag/common/embed.py`.
- Not measured: no size or overlap sweep was run. Each strategy has one setting. The five-strategy comparison is the only evidence, and it mixes size and boundary quality (median words range from 77 to 542). So you cannot say from this repo "200 beats 400".

**Follow-ups.**
1. How would you run a size sweep? (Same golden set, same retriever, vary size only; report hit@5, MRR and context tokens together; treat under 8 points as noise.)
2. Why count words, not tokens? (Comparable across strategies and cheap; tokens differ per model. Costs: token limit surprises.)
3. Does overlap help with a parent-child setup? (Children use overlap 20; parents use none.)

---

## 4. Dense vs sparse (BM25) vs hybrid retrieval

**Question.** What is the difference between dense and sparse retrieval? Why combine them?

**Short answer.** Dense retrieval embeds query and chunks and ranks by vector similarity, so it finds
paraphrases and meaning. Sparse retrieval (BM25) ranks by exact term overlap weighted by rarity, so it
nails identifiers, names and rare terms. They fail on different questions, so combining them lifts
recall. Here, hybrid beat either alone on most chunkers.

**Go deeper.**
- General BM25: `score(q, d) = sum over terms t of idf(t) * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(d) / avg_len))`. `k1` caps the gain from repeating a word, `b` controls the penalty for long documents. Idf makes rare words count more. This repo uses k1 = 1.5, b = 0.75.
- General dense: cosine similarity between L2-normalised vectors, so it is a dot product. Weak at exact strings (error codes, version numbers), good at "how does X cope with Y going down".
- Dense is an approximate-meaning match, BM25 is a vocabulary match. A paraphrase question with no shared words kills BM25; a rare-term query dilutes in embedding space.

Measured here (mean hit@5 over the five chunkers, Computed from `runs/exp__*/report.json`; same files give per-type numbers):

| Config | mean hit@5 | mean MRR |
|---|---|---|
| dense | 0.670 | 0.495 |
| bm25 | 0.741 | 0.575 |
| rrf | 0.778 | 0.567 |
| weighted | 0.784 | 0.589 |

(`rag/README.md` Step 9 gives the same bm25 0.741 / rrf 0.779 / weighted 0.784; rrf differs only by rounding, 0.778 vs 0.779.)

By question type, mean hit@5 over five chunkers (Computed from the `final_stage_by_type` block of the same reports):

| Type (n) | dense | bm25 | weighted |
|---|---|---|---|
| exact_term (6) | 0.800 | 1.000 | 0.967 |
| paraphrase (12) | 0.550 | 0.567 | 0.617 |
| factual (6) | 0.733 | 0.600 | 0.800 |
| multi_chunk (6) | 0.500 | 0.667 | 0.667 |
| comparison (5) | 0.920 | 1.000 | 1.000 |

- Exact-term questions: BM25 beats dense, as expected.
- Surprise worth admitting: on paraphrase questions BM25 is not worse than dense (0.567 vs 0.550). So the textbook story "dense wins on paraphrase" is not visible here; the questions have n = 12 and each is 8 points of the type, so this is noise-level. Do not oversell either side.
- Hybrid is best or tied on every type except it does not beat BM25 on exact_term (0.967 vs 1.000; one question).
- Candidate recall is high: dense hit@30 is 0.946 on semantic chunks (`runs/exp__semantic__dense/report.json`, stage `dense`), so most failures are ranking and selection, not "never retrieved" (section 8).

**In this repo.**
- Dense: `dense_search` in `rag/query/retrieve.py` -> `ChunkStore.search_dense`; in memory `VectorIndex.search` in `rag/common/store.py` (numpy, exact cosine).
- Sparse: `keyword_search` in `rag/query/retrieve.py` -> `search_keyword`; in memory `BM25Index` in `rag/common/bm25.py`.
- Named configs: `dense`, `bm25`, `rrf`, `weighted`, `dense_rerank`, `rrf_rerank` in `rag/query/configs.py`.
- Run: `python -m rag.experiments.retrieval` (`rag/README.md` Step 5).

**Follow-ups.**
1. When would dense alone be enough? (Semantic questions over clean prose, no part numbers or acronyms; cheaper infra. Not shown to be true on this book.)
2. Why is hybrid not much better than bm25 on MRR (0.567 to 0.589 vs 0.575)? (Fusion mostly pulls the gold chunk into the top 5, not to rank 1; hit@5 rises more than MRR. Fusion can also push a good rank-1 BM25 hit down.)
3. How do you handle a query with a typo? (General: dense tolerates it, BM25 needs fuzzy matching or n-grams. Not built here.)

---

## 5. Reciprocal rank fusion vs weighted min-max; why keep your own fusion?

**Question.** How do you merge a BM25 list and a vector list? Compare RRF and weighted score
fusion. Why did you not use OpenSearch's hybrid query?

**Short answer.** BM25 scores and cosine scores are on different scales, so you cannot add them
raw. RRF ignores scores and adds `1 / (k + rank)` per list; it is robust and needs no tuning. Weighted
min-max rescales each list to 0..1 and takes a weighted sum; it uses score gaps but one outlier skews
the scale and the weights need tuning. I kept my own fusion in Python so I could trace each stage,
swap stores, and compare both methods on the golden set. I did not build or measure OpenSearch's
hybrid pipeline.

**Go deeper.**
- RRF formula: `score(d) = sum over lists of 1 / (k + rank_in_list)`, with k = 60. A larger k flattens the gap between top ranks.
- RRF worked example (illustration, not repo data). Doc A: rank 1 in dense, rank 3 in BM25. Doc B: rank 2 in dense, rank 1 in BM25.
  - A = 1/61 + 1/63 = 0.016393 + 0.015873 = 0.032266
  - B = 1/62 + 1/61 = 0.016129 + 0.016393 = 0.032522
  - B wins: being near the top of both lists beats being first in one.
- Weighted min-max: `norm(s) = (s - min) / (max - min)` per list, then `0.7 * dense + 0.3 * bm25` (this repo's weights; docstring in `fusion.py` says they come from the original fork's OpenSearch pipeline, 0.3 keyword and 0.7 vector). A doc missing from a list scores 0 there.
  - Illustration: dense scores [0.80, 0.60, 0.50] -> [1.0, 0.33, 0.0]; BM25 scores [12, 5, 2] -> [1.0, 0.30, 0.0]. Doc 2 gets 0.7 * 0.33 + 0.3 * 0.30 = 0.32.
  - Weakness: one huge BM25 score (an exact rare-term match) squashes everything else in that list toward 0. Also, if all scores in a list are equal the code assigns 1.0 to all (`_minmax`).
- General: rank-based fusion is safer when you do not know score distributions; score-based fusion can use the signal that doc 1 is far ahead of doc 2.

Measured here (hit@5; `runs/exp__<chunker>__rrf` and `__weighted`):

| Chunker | rrf | weighted |
|---|---|---|
| fixed | 0.730 | 0.649 |
| recursive | 0.676 | 0.757 |
| heading | 0.865 | 0.865 |
| parent_child | 0.784 | 0.784 |
| semantic | 0.838 | 0.865 |

Means 0.778 vs 0.784: the same within noise. Fixed and recursive disagree in opposite directions
(rrf wins by 8.1 points on fixed, weighted wins by 8.1 on recursive). Honest conclusion: no winner. The
repo defaults to weighted because the best cell, semantic + weighted, gives the project invariant 0.865 / 0.663.

Why not OpenSearch's hybrid pipeline:
- What is written in the repo: `docs/original_repo_patterns.md` section 1 keeps the fork's hybrid query (a `hybrid` query plus `search_pipeline`) and says "compare the two on the golden set before switching". That comparison was not done: Not built, not measured.
- Design reasons visible in code (my reading, not a recorded decision): the `ChunkStore` interface exposes `search_dense` and `search_keyword` separately, so fusion lives in `rag/query/pipeline.py` and works the same for the in-memory store and OpenSearch. Each stage (`dense`, `bm25`, `fuse`) is written to the trace, which the failure diagnosis in section 8 needs. A server-side hybrid query returns only the fused list, so you could not tell "retriever missed it" from "fusion lost it".
- Also, the in-memory store has no hybrid pipeline, so using it would split the code path and the experiments would no longer be comparable between stores.
- Repo contradiction to know: `docs/original_repo_patterns.md` shows the fork's mapping with engine faiss and space l2, while the current index in `rag/common/opensearch_store.py` uses engine lucene and space cosinesimil. Use the code, not the note.

**In this repo.**
- `rrf` and `weighted` in `rag/query/fusion.py`; `_minmax` helper.
- Dispatch and `fuse` trace record: `RetrievalPipeline.run` in `rag/query/pipeline.py`.
- Knobs: `RetrievalConfig.fusion`, `weights` (0.7, 0.3), `rrf_k` (60), `candidates` (30), `fused_k` (30) in `rag/query/configs.py`.
- Fusion failures are counted as `lost_at_fuse`: 1 question on most chunker/config cells with hybrid, up to 2 for parent_child rrf (reports above).

**Follow-ups.**
1. Would you tune the 0.7 / 0.3 weights? (Only with more questions: 37 is too few; tuning on them overfits. Not tuned here.)
2. When does RRF fail? (When one retriever is much better and you want its scores to dominate; rank-only fusion throws that away.)
3. How would you test OpenSearch's hybrid pipeline fairly? (Same golden set, same embedder, same 30 candidates; compare hit@5 and MRR; accept a switch only for a gap above about 8 points or a clear latency gain.)

---

## 6. Why and when to rerank with a cross-encoder?

**Question.** What is a reranker, why add one, and what does it cost?

**Short answer.** A bi-encoder (the embedding model) embeds query and passage separately, so it can
search the whole corpus fast but misses fine detail. A cross-encoder reads query and passage
together and scores their match; it is much more accurate but too slow for the whole corpus, so it only
re-orders the top 30 candidates. It pays off when your first stage finds the evidence but ranks it low. It costs latency, a second model, and a ceiling: it cannot recover what was not in the 30.

**Go deeper.**
- General: cost is one forward pass per (query, passage) pair, so 30 candidates = 30 passes per question. It grows linearly with candidates and passage length.
- General: also worth it when the LLM context is small (you must pick 3 to 5 passages well). Less valuable when the retriever already ranks well.
- Measured here, hit@5, with versus without rerank (`runs/exp__<chunker>__dense` vs `__dense_rerank`, and `__rrf` vs `__rrf_rerank`):

| Chunker | dense | dense_rerank | rrf | rrf_rerank |
|---|---|---|---|---|
| fixed | 0.568 | 0.757 | 0.730 | 0.730 |
| recursive | 0.703 | 0.784 | 0.676 | 0.811 |
| heading | 0.757 | 0.838 | 0.865 | 0.811 |
| parent_child | 0.649 | 0.784 | 0.784 | 0.784 |
| semantic | 0.676 | 0.838 | 0.838 | 0.811 |

- Computed means: dense 0.670 -> dense_rerank 0.800 (+13 points, MRR 0.495 -> 0.613). rrf 0.778 -> rrf_rerank 0.789 (+1 point, noise; MRR 0.567 -> 0.614).
- Reading: reranking rescues a weak first stage (dense), but it did not beat a good hybrid. Best non-rerank cells (0.865) are not matched by any rerank cell (best 0.838 on dense_rerank for heading and semantic). In other words, here hybrid retrieval gets most of the gain a reranker would give. The mean MRR gain for rrf (+0.047) is the one place the reranker looks useful on a hybrid, but one config on 37 questions is weak evidence.
- Latency (Computed from `elapsed_ms` in `runs/exp__semantic__rrf_rerank/traces/*.json`, 45 questions, this machine): rerank stage mean 138.1 ms for 30 candidates, against 21.7 ms for dense and 1.5 ms for BM25. Reranking dominates retrieval time. The run does not say if it used a GPU; do not quote a hardware claim.
- Default reranker model: `cross-encoder/ms-marco-MiniLM-L-6-v2` (default argument in `CrossEncoderReranker`).
- The reranker is off by default: `RetrievalConfig.rerank = False`.

**In this repo.**
- `rag/query/rerank.py`: `Reranker` protocol, `CrossEncoderReranker`, `KeywordOverlapReranker` (tests only).
- Wiring: `RetrievalPipeline.run` in `rag/query/pipeline.py` (needs `reranker=` or it raises `ValueError`).
- Configs `dense_rerank`, `rrf_rerank` in `rag/query/configs.py`. Command: `python -m rag.experiments.retrieval --configs dense_rerank,rrf_rerank` (`rag/README.md` Step 5).
- Answer-quality effect of reranking: not measured (only retrieval metrics).

**Follow-ups.**
1. Why not rerank everything? (Cost grows with corpus size; that is the point of the two-stage design.)
2. How many candidates should you rerank? (General: 20 to 100. Here 30. A sweep was not run.)
3. What if the reranker was trained on web search (MS MARCO) and your text is a technical book? (Domain shift is possible; check on your golden set. Not tested beyond the numbers above.)

---

## 7. Retrieval metrics: hit@k, recall@k, MRR, nDCG@k

**Question.** Which retrieval metrics do you report, how are they defined, and why more than one?

**Short answer.** Hit@k asks: is any relevant passage in the top k? Recall@k: what share of the
relevant items are in the top k? MRR: average of 1 / rank of the first relevant result, so it rewards
putting the answer first. nDCG@k: rewards relevant results more when they are higher, normalised by the ideal ordering. No single number is enough: hit@5 can be high while MRR is poor, which means the evidence is found but ranked low.

**Go deeper.**
- Hit@k (a.k.a. success@k): 1 if any relevant item is in the top k, else 0; averaged over questions. Ignores order inside k.
- Recall@k: relevant items found in the top k / all relevant items. Equals hit@k when there is exactly one relevant item. Matters for multi-chunk questions. Here "relevant items" are gold page ranges, each credited once.
- Precision@k (General, not reported here): relevant in top k / k.
- MRR: `mean over queries of 1 / rank_of_first_relevant`, 0 if none.
  - Worked example, 3 queries. Query 1: first relevant at rank 1 -> 1. Query 2: at rank 3 -> 0.333. Query 3: no relevant result -> 0. MRR = (1 + 0.333 + 0) / 3 = 0.444.
  - Note MRR only looks at the first relevant item and has no k, so it cannot see multi-evidence questions.
- nDCG@k: `DCG = sum of rel_i / log2(i + 1)` over positions i = 1..k; `nDCG = DCG / ideal DCG`.
  - Worked example, k = 5, 2 gold ranges, relevant hits at positions 1 and 4. DCG = 1/log2(2) + 1/log2(5) = 1 + 0.431 = 1.431. Ideal (both at positions 1 and 2) = 1 + 1/log2(3) = 1 + 0.631 = 1.631. nDCG@5 = 1.431 / 1.631 = 0.877.
  - In this repo gain is binary and each gold range is credited once, so duplicate chunks from one page cannot push nDCG above 1.
- Why several: hit@5 answers "did the LLM get the evidence at all"; MRR/nDCG answer "was it near the top" (matters for small context and for models that favour early passages); recall@k covers multi-part questions.
- Measured here for the default config (semantic + weighted, `runs/exp__semantic__weighted/report.json`, stage `context`): hit@1 0.568, hit@3 0.703, hit@5 0.865, recall@5 0.797, MRR 0.663, nDCG@5 0.677. The jump hit@1 0.568 -> hit@5 0.865 shows evidence is usually found but not always first.
- Same file, dense only stage: hit@5 0.676 vs hit@30 0.946, so a large part of dense's problem is ranking, not recall.
- Caveats: the golden set has 37 answerable questions, so one is 2.7 points. Relevance is page-level, which cannot say whether the exact sentence is in the chunk.
- Strict relevance: `strictify` in `rag/observe/retrieval_quality/metrics.py` moves a hit that overlaps the gold page but contains none of the question's `evidence_terms` to page 0, so it no longer counts. `run_eval(strict=True)` is the default and `rag.experiments.retrieval` uses it unless you pass `--page-level`.
- Repo contradiction: `rag/README.md` Step 3 says a chunk "is relevant if its page range overlaps a gold range", but the code now also requires an evidence term by default (strict mode). Trust the code. I could not verify whether every old run in `runs/` used strict mode; the `semantic + weighted` invariant (0.865 / 0.663) matches the current report.

**In this repo.**
- `rag/observe/retrieval_quality/metrics.py`: `hit_rate_at_k`, `recall_at_k`, `reciprocal_rank`, `ndcg_at_k`, `score_hits`, `overlaps`, `is_relevant`, `strictify`.
- `rag/observe/retrieval_quality/run_eval.py`: `run_eval`, writes `runs/<run_name>/report.json`, `per_question.jsonl`, `traces/`.
- Per-type breakdown: `final_stage_by_type` in each `report.json`.
- Printed table columns: hit@1, hit@5, rec@5, mrr, ndcg@5, cand@30, ms/q, failures (`summarise` in `rag/experiments/retrieval.py`; `cand@30` is recall@30 of the fuse stage, or of the single retriever when only one is on).

**Follow-ups.**
1. When does MRR mislead? (Multi-evidence questions, or when the first relevant item is a duplicate. It only sees the first hit.)
2. Why not precision@k? (Few relevant items per question, so it is capped far below 1 and hard to read; a hit-based metric is clearer here.)
3. What is the difference between retrieval metrics and answer quality? (Retrieval can be perfect and the answer wrong. Answer scoring uses `rag/observe/generation_quality/`, out of scope for this file.)

---

## 8. How do you diagnose a retrieval failure?

**Question.** A user gets a wrong answer. How do you find out whether retrieval or generation is at
fault, and which retrieval stage?

**Short answer.** Record every stage's ranked list in a trace, then look up the gold page in each
stage in order. The first stage where the gold evidence disappears is the culprit. This repo labels
that as `retrieval_miss` (no retriever found it), `lost_at_<stage>` (an earlier stage had it and this one dropped it), or `retrieval_ok` (it survived, so look at the prompt or the model).

**Go deeper.**
- Logic (`locate_failure` in `rag/observe/retrieval_quality/diagnose.py`): take the rank of the first gold-relevant hit at every stage. If no `retrieve` stage (dense, bm25) has it: `retrieval_miss`. Otherwise walk the `transform` stages (fuse, rerank, context); the first one that had it before and lost it gives `lost_at_<stage>`. If it is still there at the end: `retrieval_ok`. Unanswerable questions get the label `unanswerable` in the report counts.
- Fix by label:
  - `retrieval_miss`: check extraction, chunking (is the answer split?), the candidate count, the query text, the embedder.
  - `lost_at_fuse`: fusion weights or method.
  - `lost_at_rerank`: the reranker is demoting gold.
  - `lost_at_context`: see below.
  - `retrieval_ok` with a wrong answer: prompt, model, or a wrong gold label. Check the label before blaming the pipeline.
- Important subtlety (my reading of the code): the `context` stage keeps only `top_k` = 5 passages, while the earlier stages list up to 30. So `lost_at_context` covers two different things: the gold passage was at rank 6 to 30 and simply fell off the end, or it was dropped by the scanner, overlap removal, per-source cap or word budget. The trace separates them partly: `skipped_by_scanner` is recorded in the `context` stage meta, and `stage_ranks` in each row of `per_question.jsonl` shows the gold rank at each stage.
- Measured here: failure counts for the 45 questions (37 answerable + 8 labelled `unanswerable`). Default config `runs/exp__semantic__weighted/report.json`: `retrieval_ok` 32, `lost_at_context` 3, `lost_at_fuse` 1, `retrieval_miss` 1, `unanswerable` 8. For dense-only on fixed chunks (`runs/exp__fixed__dense`): `retrieval_ok` 21, `lost_at_context` 14, `retrieval_miss` 2. So the dominant failure is ranking, not recall (candidate recall is about 0.95).
- Generation side (out of scope here, `rag/README.md` Step 6): wrong answers are attributed to `retrieval_fail`, `generation_fail`, or `right_without_evidence`.

**In this repo.**
- `locate_failure`, `stage_ranks` in `rag/observe/retrieval_quality/diagnose.py`.
- Trace and `trace.record(name, kind, hits)`: `rag/common/trace.py` (`Trace`, `StageRecord`, `load_trace`). `kind` is `retrieve` or `transform`.
- Aggregation: `failure_counts` in `report.json` (made in `rag/observe/retrieval_quality/run_eval.py`).
- Labels documented in `rag/README.md` Step 3.

**Follow-ups.**
1. Why record stages instead of just the final list? (Without per-stage lists you cannot separate "never found" from "found then dropped".)
2. What if the label is `retrieval_ok` but the answer is wrong? (Prompt, generation, or a bad gold label; check the label first.)
3. How do you find systematic misses? (Group failures by question `type`: paraphrase has the worst hit@5 in section 4; look at those.)

---

## 9. Context selection: what happens between ranking and the prompt?

**Question.** After you rank passages, how do you decide what goes into the LLM prompt?

**Short answer.** Walk the ranked list and keep passages until the count or word budget is full,
skipping ones that should not be there: a retrieved child is swapped for its parent, passages the
injection scanner flags are skipped, near-duplicates and exact copies are dropped, and one source can only add a few passages. That turns a ranked list into a clean, diverse, bounded context.

**Go deeper.**
- Order inside `select_context`, per candidate:
  1. Parent expansion: if the chunk has `parent_id` and `use_parents` is on, use the parent text. (parent_child only.) Skip if that parent is already chosen.
  2. Scanner skip: `scan_text` from `rag/query/guard.py`; a flagged passage is skipped, the next candidate fills its place, and it is recorded in `skipped_by_scanner`.
  3. Overlap drop: a passage is dropped if 50% or more of its characters are already covered by a chosen passage from the same source (overlapping chunks from fixed/recursive).
  4. Exact-copy drop: same normalised text twice is dropped (flooding defence).
  5. Per-source cap: max 2 passages per `meta["source"]`; book chunks have no source and are not capped.
  6. Word budget: stop at `top_k` = 5 passages or `max_words` = 1500; a passage that would exceed the budget is skipped, but the first passage is always allowed.
- The cap is turned off when only one document is in scope (the pipeline passes `max_per_source=0` if `len(doc_ids) == 1`), since there is nothing to flood and the cap would just cut a legitimate document.
- General: the final order matters; many LLMs weight the beginning and end of the context more ("lost in the middle"). No reordering is done here.
- Effect on retrieval metrics: `README.md` says the scanner and cap leave golden-set metrics unchanged because the book has no sources and the scanner removes no gold chunk (`rag/README.md` Step 7).
- Measured link to section 8: `lost_at_context` is the largest non-OK label (for example 3 of 37 in the default config), so this stage is where most answerable failures live; part of it is the plain top-5 cut.

**In this repo.**
- `select_context`, `ContextConfig`, `_overlap`, `hit_from_chunk` in `rag/query/select_context.py`.
- `RetrievalConfig.top_k`, `max_words`, `use_parents`, `scan`, `max_per_source`, `drop_exact_copies` in `rag/query/configs.py`.
- Called at the end of `RetrievalPipeline.run` in `rag/query/pipeline.py`; parents loaded by `store.get_parents`.
- Scanner and output filter: `rag/query/guard.py`. Injection tests: `rag/security/` (`rag/README.md` Step 7).

**Follow-ups.**
1. Why swap child for parent? (Precise match, richer context. Costs budget; see parent-child in section 2.)
2. Is dropping overlapping passages safe? (It can remove a passage that has a different part of the answer if overlap is high; threshold 0.5 is a judgement, not tuned.)
3. How does context selection relate to security? (It is a defence layer: scanner skip, exact-copy drop and per-source cap were added against injection and flooding.)

---

## 10. Vector store design: the ChunkStore interface and per-owner indexes

**Question.** How did you design the storage layer? Why one index per user instead of a shared index
with a filter?

**Short answer.** The query pipeline talks only to a small `ChunkStore` interface, with an in-memory
numpy implementation for experiments and an OpenSearch implementation for the real service, so
swapping storage never touches retrieval logic. Each owner gets their own OpenSearch indexes because
BM25 statistics (idf and average length) are computed over the whole index: in a shared index one
user's uploads change another user's ranking, a leak that a filter alone does not fix.

**Go deeper.**
- Interface methods (`rag/common/chunk_store.py`, `ChunkStore` protocol): `upsert`, `search_dense`, `search_keyword`, `get_parents`, `document_ids`, `describe`, `has_document`, `delete_document`.
- Every read takes a `Scope(owner, doc_ids)`; the owner is required and the filter is applied inside the store so a caller cannot forget it.
- Chunk ids must be unique among one owner's documents; the in-memory store is stricter and wants them globally unique. Upload chunk ids are qualified as `<doc_id>:<chunk_id>` (`CLAUDE.md`, Security conventions).
- Why the BM25 leak happens (General): BM25 scores use `idf(t) = log(N / df)` where N and df count every document in the index. If a user uploads 10,000 chunks mentioning "kafka", the idf of "kafka" falls for everyone in the shared index, so another user's ranking shifts, and score differences reveal information about other tenants' content. An owner-filter on the query removes the rows from the result but does not change the statistics (the repo's docstring states the same reasoning; Lucene computes statistics over the index).
- Parent chunks are stored in a separate `_p_` index, fetched by id and never searched, so they do not move the statistics either.
- Trade-offs of index-per-tenant (General): many small indexes means more shards and cluster-state overhead; fine for tens to thousands of tenants, painful for millions. Shared index + filter is cheaper but has the statistics leak (and weaker blast-radius isolation).
- Index names: `<prefix>_d_<embedder>_<dim>` (documents), `<prefix>_c_<embedder>_<dim>_<owner>` (searchable chunks), `<prefix>_p_<embedder>_<dim>_<owner>` (parents). The owner part is the first 16 hex characters of a SHA-1 of the owner string, because index names cannot hold arbitrary text. The documents index is per embedder, so after changing the embedding model a document is reported absent and re-indexed instead of being found with no vectors.
- Also a second guard: every query still filters on `owner` and `doc_id` inside the query (`_filters`), noted in code as redundant with the index.
- Thread safety: `MemoryChunkStore` takes an `RLock` on every method because the API serves from several threads.
- Measured here: dense results through OpenSearch are identical to in-memory on every chunker (0.0 points change, MRR 0.000 change). Latency about 6 to 11x slower (0.1 to 0.5 s per question vs 0.02 to 0.2 s, `rag/README.md` Step 9). From traces (Computed from `runs/par_os2__semantic__rrf/traces` vs `runs/exp__semantic__rrf/traces`): dense stage mean 179.7 ms vs 22.0 ms, bm25 68.2 ms vs 1.2 ms.
- Answer quality through OpenSearch vs memory (`rag/README.md` Step 9): correct 0.722 vs 0.750, faithful 0.865 vs 0.838, cites gold page 0.811 vs 0.784; within noise.
- Not built: Keycloak token validation; `current_owner` in `rag/api/main.py` is a placeholder returning one local user (`docs/backlog.md`, Security; `docs/auth_plan.md`).

**In this repo.**
- `rag/common/chunk_store.py`: `ChunkStore`, `Scope`, `MemoryChunkStore`.
- `rag/common/opensearch_store.py`: `OpenSearchChunkStore`, `_chunks_index`, `_parents_index`, `_owner_key`, `_filters`, `unique_prefix`.
- `rag/common/store.py`: `VectorIndex` (numpy vectors, exact cosine, cached on disk).
- Switch: `RAG_STORE=memory|opensearch` (read in `rag/api/main.py`).
- Tests: `tests/test_chunk_store.py` runs the same checks against both stores; OpenSearch ones skip when the database is down (`rag/README.md` Step 9).
- Run OpenSearch: `docker-compose.yml`, command in `CLAUDE.md`; security plugin is off and the port is bound to 127.0.0.1 only, which is only acceptable locally.

**Follow-ups.**
1. What would you do with a million tenants? (General: shared index with routing by tenant and filtered kNN; accept the statistics effect or compute BM25 per tenant at the application layer. Not built here.)
2. Why return 404 and not 403 for another owner's document? (A 403 confirms the document exists; `CLAUDE.md`, Security conventions.)
3. Why a protocol and not a base class? (Structural typing keeps the in-memory and OpenSearch stores independent; General.)

---

## 11. Exact vs approximate (HNSW) nearest-neighbour search

**Question.** Exact kNN or approximate kNN? What is HNSW and what did you measure?

**Short answer.** Exact kNN scores every vector, so it is always right but cost grows linearly with the
corpus. HNSW builds a layered graph and walks it, trading a little recall for much lower latency at scale. For a book with about a thousand chunks exact is fine, so this repo defaults to exact. I did not measure HNSW recall on this data.

**Go deeper.**
- General HNSW: a multi-layer small-world graph; search enters at the top layer and greedily moves to nearer neighbours, descending layers. Knobs: `M` (links per node), `ef_construction` (build effort), `ef_search` (query effort). Higher values raise recall and cost.
- General: recall of approximate search is measured against exact results ("recall@k of the ANN index"), separate from retrieval quality against the gold labels.
- Exact search here: OpenSearch `script_score` with the `knn_score` script (`space_type: cosinesimil`) over a bool filter, so it scores every vector in scope.
- Approximate: a `knn` query on the `knn_vector` field; the mapping is `hnsw`, engine `lucene`, `cosinesimil` in `rag/common/opensearch_store.py`.
- Score mapping (stated as measured in the module docstring of `opensearch_store.py`; formulas in `search_dense`):
  - exact: `_score = 1 + cosine`, so the code uses `cosine = score - 1.0`
  - approximate (Lucene): `_score = (1 + cosine) / 2`, so the code uses `cosine = 2.0 * score - 1.0`
  - result clamped to [-1, 1]. Reason: OpenSearch scores must be non-negative; the cosine is recovered from the score so no vector has to be fetched back.
  - Worked check: cosine 0.6 -> exact score 1.6, Lucene score 0.8; both map back to 0.6.
- Measured here: exact search through OpenSearch gives dense results identical to the in-memory run on all five chunkers (`rag/README.md` Step 9 table, dense row: 0.0 pts change).
- Not measured: HNSW recall or its retrieval quality (stated in `rag/README.md` Step 9 and `docs/backlog.md`, "Retrieval and evaluation"). In the interview say: "I only tested exact; for approximate I would compare its top-k to the exact top-k and then rerun the golden set".
- The ranking function is the same for the two store modes only for exact mode; HNSW changes results slightly by design.

**In this repo.**
- `OpenSearchChunkStore.__init__(exact=True)` and `search_dense` in `rag/common/opensearch_store.py`; `_ensure_owner_indexes` builds the mapping.
- In-memory exact search: `VectorIndex.search` in `rag/common/store.py`.
- Parity experiment: `python -m rag.experiments.retrieval --store opensearch`, runs in `runs/par_os2__*` (OpenSearch) and `runs/par_mem__*` (memory) (`rag/README.md` Step 9).

**Follow-ups.**
1. At what size do you need HNSW? (General: roughly when exact scan latency is too high, often above 100k to 1M vectors. For about 1,000 chunks it is not needed.)
2. How would you measure HNSW recall? (Take the exact top-k as truth, compute overlap with the HNSW top-k over many queries, sweep `ef_search`.)
3. Why a `filter` inside the kNN query? (Pre-filtering during the graph walk; post-filtering can return fewer than k results. General; the repo passes the filter inside the `knn` query.)

---

## 12. BM25 stemming

**Question.** Your OpenSearch keyword search beat your own BM25. Why, and what did you do about it?

**Short answer.** OpenSearch's `english` analyzer stems words ("indexes" and "indexing" both become
"index") and mine did not. I added an optional dependency-free Porter stemmer and it recovered about
two thirds of the hit@5 gap and all of the MRR gap. It is off by default because the hybrid configs
the system actually uses did not improve beyond noise.

**Go deeper.**
- General: stemming raises recall (more matches) and can lower precision ("university" and "universe" stem together in Porter). Lemmatisation is slower but more accurate.
- Measured here (`rag/README.md` Step 9; mean over five chunkers, 37 questions, in memory):

| Config | hit@5 off | hit@5 stem | OpenSearch change | MRR off | MRR stem |
|---|---|---|---|---|---|
| bm25 | 0.741 | 0.795 (+5.4) | +8.1 pts | 0.575 | 0.648 |
| rrf | 0.779 | 0.806 (+2.7) | +3.8 pts | 0.567 | 0.603 |
| weighted | 0.784 | 0.800 (+1.6) | +2.2 pts | 0.589 | 0.577 |

- Reading: 5.4 of 8.1 points is two thirds. Remaining about 2.7 points is one question, inside noise, so stopword list, possessives or tokenizer differences are neither ruled out nor needed.
- Individual cells swing up to 8 points either way (semantic + weighted falls 0.865 -> 0.811, heading + weighted rises 0.865 -> 0.892), so only means mean anything.
- Why it stays off: the invariant `--chunkers semantic --configs weighted` (0.865 / 0.663) holds with stemming off, and the weighted mean MRR even drops (0.589 -> 0.577).
- The honest framing: OpenSearch's keyword gain was a difference in the search, not a bug, and "very likely" stemming (the README's words), not proven.
- Parity table for the OpenSearch keyword path (`rag/README.md` Step 9): bm25 +8.1 pts hit@5, +0.070 MRR; the dense row was 0.0.
- Also: the OpenSearch text field uses the `english` analyzer (`"analyzer": "english"` in `_ensure_owner_indexes`).

**In this repo.**
- `rag/common/stem.py` (Porter stemmer), `tokenize(..., stem=...)` and `BM25Index(chunks, stem=True)` in `rag/common/bm25.py`.
- Store-level switch: `MemoryChunkStore(stem=False)`; pipelines: `RetrievalPipeline.from_chunkset(..., stem=False)`; CLI flag `--bm25-stem` in `rag/experiments/retrieval.py`.
- Command: `python -m rag.experiments.retrieval --chunkers fixed,recursive,semantic,heading,parent_child --configs bm25,rrf,weighted --bm25-stem`.

**Follow-ups.**
1. Stemming vs lemmatisation? (General.)
2. Would stemming hurt on code or identifiers? (Possible: General. Not tested; the book mixes prose and code.)
3. Why trust means and not cells? (Single cells swing 5 to 8 points from one question; `rag/README.md` Step 9.)

---

## 13. Embedding model choice

**Question.** Why that embedding model, and what would change if you used another?

**Short answer.** I used `sentence-transformers/all-mpnet-base-v2`: a free, local, general-purpose
sentence model with 384-token input, so no data leaves the machine and no API cost. It was picked to
learn the pipeline, not benchmarked against alternatives. A different model would change vector
dimension, token limit, and whether a query prefix is required, and it would force a full re-index.

**Go deeper.**
- Not measured: no other embedding model was compared on the golden set. Say so.
- What changes with another model (General unless noted):
  - Dimension (storage and latency). The code reads it from the model (`self.dim`), and the OpenSearch index name includes `<embedder>_<dim>` so mixed models do not collide.
  - Token limit: 384 for mpnet; chunk size should fit under it. `max_tokens` and `count_tokens` exist to check.
  - Prefixes: e5-style and bge-style models want "query: " / "passage: " or an instruction prefix. `SentenceTransformerEmbedder` has `doc_prefix` and `query_prefix` parameters, but `get_embedder("st:<model>")` does not pass them, so prefix-dependent models are not usable through the spec string without a code change. That is a limit worth knowing.
  - Domain and language: a general English model may be weak on code or other languages; a multilingual or code model would help.
  - Re-index: vectors from different models are not comparable, so you must re-embed everything. The vector cache is keyed on the embedder name and a text fingerprint (`index_dir`, `text_fingerprint`, `VectorIndex.matches` in `rag/common/store.py`).
- Semantic chunking depends on the embedder too (`SemanticChunker` embeds every sentence), so changing the model changes the chunk boundaries; the chunk file records `embedder` in its params.
- Vectors are L2-normalised, so cosine equals the dot product (`rag/common/embed.py` docstring).
- Offline test embedder: `HashingEmbedder` (`get_embedder("hash")`), bag-of-words with no meaning, only for testing plumbing.
- How to compare models fairly (General, applied here): same chunks, same golden set, same retriever; report hit@5, MRR, nDCG together; also look at latency and index size.

**In this repo.**
- `get_embedder`, `SentenceTransformerEmbedder`, `HashingEmbedder` in `rag/common/embed.py`.
- Default spec `st:sentence-transformers/all-mpnet-base-v2` in `rag/experiments/retrieval.py` (`--embedder`) and `RAG_EMBEDDER` default in `rag/api/main.py`.
- Embedding cache location: `data/processed/index/` (`rag/README.md` Step 5).

**Follow-ups.**
1. Why not a hosted embedding API? (Data stays local; no per-token cost. Trade-off: you carry the compute and model upgrades.)
2. How do you fine-tune or choose a model for a domain? (General: build domain pairs, compare on a golden set, fine-tune only if the gap is large.)
3. Does the embedder also affect BM25? (No. That is why hybrid is robust to an embedder change.)

---

## 14. Metadata filtering and multi-tenancy

**Question.** How do you restrict search to some documents or to one user's data, and how do you
make sure nothing leaks?

**Short answer.** Every search takes a `Scope` made of an owner and an optional list of document ids,
and the store applies the filter inside the query, not after the results come back. The owner also
selects which OpenSearch index is searched at all. The owner comes from one server-side function, never from a request field, and another owner's document returns 404.

**Go deeper.**
- Filter inside vs after the search: post-filtering a top-k list can leave you with fewer than k results (or none), and can leak through score statistics or timing. Pre-filtering (inside the kNN or bool query) searches only the allowed set.
- Layers of isolation here:
  1. Caller identity from `current_owner` in `rag/api/main.py` only (`CLAUDE.md`, Security conventions). Currently a placeholder returning one local user.
  2. Separate indexes per owner (section 10).
  3. A filter on `owner` and `doc_id` in every query (`_filters`).
  4. 404 for other owners' documents, not 403.
  5. `Scope.owner` is required in the type, so a store method cannot be called without it.
- Selecting several documents: `Scope(owner, doc_ids=(...))`; `POST /v1/ask` accepts one, several or all of the caller's documents, and each passage names its source document (`rag/README.md` Step 8).
- Single vs multiple documents: the per-source cap applies only when more than one document is in scope.
- In-memory BM25 over a multi-document scope builds one index over all chunks in scope (cached by the tuple of doc ids) so scores are comparable (`MemoryChunkStore.search_keyword`).
- Dense search in memory searches each document and merges, sorting by cosine (`MemoryChunkStore.search_dense`).
- Metadata on chunks: `meta["source"]` (document id on upload), `meta["span"]` (character offsets), `meta["parent_id"]`, section path for heading chunks. `page_start` and `page_end` are 1-based PDF pages in `rag/common/types.py` (`Chunk`).
- Not built: attribute filters beyond owner and document (such as date, author, document type); Keycloak; per-client identities (`docs/backlog.md`, Security).
- Tested: a second user gets 404 for everything of the first user and never receives their passages, tested against both stores (`docs/backlog.md`, "Owner on every document and chunk is done and tested").

**In this repo.**
- `Scope`, `ChunkStore` in `rag/common/chunk_store.py`; `_filters` in `rag/common/opensearch_store.py`.
- Routes and `current_owner`: `rag/api/main.py`; work in `rag/api/service.py`.
- Design notes: `docs/auth_plan.md`, `docs/mcp_risks.md`.
- Tests: `tests/test_chunk_store.py`.

**Follow-ups.**
1. How would you do row-level security in a shared index? (General: OpenSearch document-level security with roles; here the security plugin is off.)
2. What leaks even with a correct filter? (BM25 statistics, covered in section 10; also timing and error messages.)
3. How would owner identity be established in production? (Token validation, planned with Keycloak; not built.)

---

## 15. How do you compare chunkers (or any retrieval change) fairly?

**Question.** You tried five chunkers. How do you know the winner is real and not noise or an unfair test?

**Short answer.** Hold everything else fixed: same golden set, same embedder, same retriever and
parameters, same metric code. Report several metrics, look at the means across configs, and treat a gap smaller than about 8 points as noise because one question is 2.7 points on 37 answerable questions. Only believe a difference that is large and shows up across several chunkers or configs.

**Go deeper.**
- Controls that matter:
  - Same sizes counted the same way (words everywhere here).
  - Same golden set; do not tune on all of it (`rag/README.md` Step 2 suggests holding out about 20 for final comparisons).
  - Same relevance rule. Page-overlap alone flatters big chunks that span many pages; the strict evidence-term rule (`strictify`) corrects it. `CLAUDE.md` says to use the per-question fact checklist and strict evidence-aware relevance, and not to retry page-overlap-only relevance or the holistic correctness judge (both were unreliable).
  - The `intact` column is generous for large chunks, so read it with the size columns.
- Noise arithmetic: 37 answerable questions. One question = 1 / 37 = 2.7 points. Three questions = 8.1 points. A rough binomial standard error at p = 0.8 is sqrt(0.8 * 0.2 / 37) = 0.066, so about 6.6 points for one score; the difference of two paired runs is noisy too. This is why the repo's rule of about 8 points is sensible. (General statistics; the 8-point rule itself is from `CLAUDE.md`.)
- Paired comparison is better than comparing two totals: look at which questions flipped (`per_question.jsonl` in each run).
- Measured here, what survives the rule:
  - Fixed (mean hit@5 0.663) vs heading (0.818): about 15 points, passes the bar and matches the chunk shape (84% mid-sentence starts).
  - Heading vs semantic (0.818 vs 0.798, Computed means): inside noise.
  - Config effects: weighted 0.784 vs rrf 0.778: noise. Dense 0.670 vs bm25 0.741: about 7 points, borderline. Hybrid vs dense: about 11 points, passes.
- Individual cells swing: semantic + weighted 0.865 -> 0.811 under stemming (one to two questions). Never quote a single cell as a finding.
- The golden set has types (`factual`, `exact_term`, `paraphrase`, `multi_chunk`, `comparison`, `unanswerable`, `attack`, plus `table` and `ambiguous` rows): 12 paraphrase, 6 exact_term, 6 factual, 6 multi_chunk, 5 comparison, 1 table, 1 ambiguous answerable, 6 unanswerable, 2 attack (Computed from `data/golden/ddia_questions.jsonl`). A per-type slice has 5 to 12 questions, so conclusions at type level are weaker still.
- Regression guard: `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` must print hit@5 0.865, MRR 0.663 after any refactor (`CLAUDE.md`).
- Another discipline: three sources of unfairness to name in an interview: the golden set was written by the system's author (vocabulary bias; `rag/README.md` Step 2 says at least a third must be in your own words), questions reused for tuning, and metric definitions changing between runs. The set is also one book, so results may not transfer.

**In this repo.**
- Experiment script: `rag/experiments/retrieval.py` (flags `--chunkers`, `--configs`, `--store`, `--variant`, `--bm25-stem`, `--page-level`, `--rebuild`).
- Eval harness: `run_eval` in `rag/observe/retrieval_quality/run_eval.py`; golden loading: `rag/observe/golden.py` (`load_golden`, `GoldQuestion`).
- Outputs: `runs/exp__<chunker>__<config>/` (main grid), `runs/par_mem__*` and `runs/par_os2__*` (store parity), `report.json`, `per_question.jsonl`, `traces/`.
- Golden files: `data/golden/ddia_questions.jsonl` (committed), `data/golden/KEY_FACTS_REVIEW.md`, `data/golden/question_writer_rules.md`.

**Follow-ups.**
1. How would you get more statistical power? (More questions, paired bootstrap on per-question results, report confidence intervals. Not done here.)
2. What if two chunkers tie on retrieval? (Break the tie on cost: build time, index size, complexity. Heading-aware is free; semantic costs one embedding per sentence.)
3. Retrieval improved; does the answer improve? (Check separately: `python -m rag.experiments.answer`; in this repo semantic + weighted through OpenSearch gave 23 vs 24 fully correct and grounded answers, one question apart: `rag/README.md` Step 9.)

---

## Quick revision list: one line each

- Chunking sets the unit of retrieval; a bad cut cannot be fixed downstream.
- Best chunkers here: heading and semantic (hit@5 0.865 weighted); fixed worst (0.649 weighted, 0.663 mean).
- No size/overlap sweep was run. Say so.
- BM25 beats dense on exact terms (1.000 vs 0.800), not on paraphrase here (0.567 vs 0.550).
- Hybrid means: rrf 0.778, weighted 0.784; the gap is noise. OpenSearch's hybrid pipeline was never built or compared.
- Rerank: dense 0.670 -> 0.800; rrf 0.778 -> 0.789 (noise). 138 ms for 30 candidates.
- MRR example: ranks 1, 3, none -> 0.444.
- Failure labels: `retrieval_miss`, `lost_at_fuse`, `lost_at_context`, `retrieval_ok`.
- Per-owner indexes because BM25 idf and average length are index-wide.
- Exact kNN score = 1 + cosine; HNSW (Lucene) = (1 + cosine) / 2. HNSW recall not measured.
- Stemming closes about two thirds of the OpenSearch keyword gap; off by default.
- Noise band: about 8 points; one question = 2.7 points.
