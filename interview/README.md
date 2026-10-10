# Interview notes for this project

Revision notes for RAG and applied-ML interviews, built from what was actually built and measured in this repo. Each topic is a question with a short answer to say out loud, the deeper reasoning, and a pointer to the file in this repo that implements it.

## How to use these notes

1. Read **The 60-second pitch** below until you can say it without looking.
2. Skim **Flashcards** the night before. Each has a one-line answer and a pointer.
3. For depth, open the numbered file for the topic. Every section has: **Question**, **Short answer** (30 seconds), **Go deeper**, **In this repo** (exact files and functions, and the measured numbers with where they are recorded), **Follow-ups**.
4. Be exact about status. Throughout, **Built** means code and tests exist, **Designed** means written down but not built, **General** means interview knowledge with no code here, and "not measured" means we did not measure it. Saying so plainly is stronger than bluffing.

## The files

| File | Topics |
|------|--------|
| [`01_retrieval_and_chunking.md`](01_retrieval_and_chunking.md) | Chunking strategies, embeddings, dense vs BM25 vs hybrid, fusion (RRF and weighted), reranking, hit@k, recall, MRR, nDCG, diagnosing retrieval failures, vector store design, exact vs approximate search, stemming |
| [`02_generation_and_evaluation.md`](02_generation_and_evaluation.md) | Evaluating a RAG system end to end, the golden set, faithfulness, correctness, relevance, LLM-as-judge and its biases, the noise band, prompts, citations, abstention, reasoning models, caching and privacy |
| [`03_security.md`](03_security.md) | Prompt injection (direct and indirect), the layered defence and its measured results, markdown exfiltration, output filtering and its limits, tenant isolation, upload safety, MCP risks, how security was tested |
| [`04_system_design_and_streaming.md`](04_system_design_and_streaming.md) | Architecture, why plain Python, API design, deployment and scaling, cold start, health checks, **streaming and validating a streamed answer (including what cannot be undone)**, a story about finding a limit by using the product, decisions and what was rejected, what is not done |
| [`05_conversation_memory_and_cost.md`](05_conversation_memory_and_cost.md) | Follow-up questions ("What is its population?") and query rewriting, compacting a long conversation, tracking token cost and latency, Langfuse and LangSmith; **all three are not built here, the file is the design plus what exists** |
| [`06_documents_and_models.md`](06_documents_and_models.md) | **A summary** of how PDFs are read (tables, images and scans are not handled), the libraries and alternatives (Docling, MinerU, layout models), 500-page and parallel processing, and the models used and why; details are in `docs/extraction.md` and `docs/models.md` |

## The 60-second pitch

I built a RAG system over a technical book and over PDFs that users upload, to learn how production RAG works, with evaluation and security as the priority. There are two pipelines, ingestion and query, each a thin orchestrator over small step modules, plus an evaluation layer that scores the traces they write. Retrieval is hybrid, dense vectors plus BM25, fused and optionally reranked, on OpenSearch with one index per user. I compared chunking strategies and retrieval configurations on a 45-question golden set, and learned to treat gaps under about 8 points as noise. I tested prompt injection with poisoned documents and built layered defences, and review showed that a pattern-based output filter alone gets bypassed, so the real rule is to show answers as plain text. A small web page lets you upload and chat across documents and see passages, scores and stage timings, and answers stream in through a guard that holds back risky text until it is judged. Still to do: real authentication and deployment.

## Facts to know cold

| Fact | Value | Where it is recorded |
|------|-------|----------------------|
| Corpus | Designing Data-Intensive Applications, PDF pages = printed page + 22; plus uploaded PDFs | `CLAUDE.md` |
| Golden set | 45 questions: 37 answerable, 6 unanswerable, 2 attack | `data/golden/ddia_questions.jsonl` |
| Noise band | about 8 points on 37 answerable questions (one question = 2.7 points) | `CLAUDE.md` |
| Reference retrieval run | semantic chunker + weighted fusion: hit@5 0.865, MRR 0.663 | `CLAUDE.md`, "Commands" |
| Retrieval defaults | RRF k 60, weights (0.7 dense, 0.3 BM25), 30 candidates from each retriever, 5 passages in context, at most 2 passages per source document | `rag/query/configs.py` |
| OpenSearch vs in-memory BM25 | +8.1 points hit@5 on average; stemming in memory closes about two thirds (+5.4) | `rag/README.md`, Step 9 |
| Generation, in memory vs OpenSearch | correct 0.750 vs 0.722, faithful 0.838 vs 0.865 (same within noise) | `rag/README.md`, Step 9 |
| Models | generator gpt-oss-20b on a remote server through an SSH tunnel; embedder all-mpnet-base-v2; judge qwen2.5:7b | `CLAUDE.md`, `.env.example` |
| Tests | 262 passed, 2 skipped when this was written | `python -m pytest tests -q` |

## Flashcards

Format: question, one-line answer, then where to look.

**Retrieval**
- *Why chunk at all?* Embeddings and prompts have size limits, and a smaller unit retrieves more precisely. Cost: context split across chunks. → `01`, chunking sections; code in `rag/ingestion/chunking/`.
- *Dense vs BM25?* Dense matches meaning, BM25 matches exact words, names and numbers; hybrid covers both. → `01`; `rag/query/retrieve.py`.
- *RRF formula?* Each document scores the sum over lists of 1 / (k + rank), with k = 60 here, so it uses ranks only and needs no score scaling. → `rag/query/fusion.py`, `rag/query/configs.py`.
- *Weighted fusion?* Min-max scale each list, then take a weighted sum (0.7 dense, 0.3 BM25 here); sensitive to score distributions. → `rag/query/fusion.py`.
- *Why rerank?* A cross-encoder reads the question and passage together, so it is more accurate than the bi-encoder used for first-stage search, but slower, so it only reorders a short list. → `rag/query/rerank.py`.
- *Hit@k?* Share of questions where a relevant item is in the top k. *Recall@k?* Share of all relevant items found in the top k. → `rag/observe/retrieval_quality/metrics.py`.
- *MRR?* Mean over questions of 1 / (rank of the first relevant result), 0 if none. Ranks 1, 3 and none give (1 + 1/3 + 0) / 3 = 0.444. It rewards putting the answer first.
- *nDCG@k?* Gain of each relevant result discounted by log of its position, divided by the best possible ordering; handles graded relevance.
- *Why one index per owner?* Lucene computes BM25 statistics over the whole index, so a shared index lets one user's documents change another's ranking. → `01`; `rag/common/opensearch_store.py`.
- *Exact vs approximate kNN?* Exact scans everything and is the baseline; HNSW is faster with a recall loss. Recall of the approximate mode was not measured here.

**Evaluation**
- *Faithfulness vs correctness vs relevance?* Faithful: the claims are supported by the retrieved passages. Correct: it matches the truth (key facts). Relevant: it answers the question that was asked. → `02`.
- *Why a per-question fact checklist?* A holistic "is this correct?" judge was unreliable here; checking each expected fact is stricter and explainable. → `02`; `CLAUDE.md`, "Behaviour that must not drift".
- *Danger of LLM-as-judge?* Self-preference when the generator grades itself, small judges misreading right answers, verbosity and position bias. Measured here: 1 of 5 with a small judge, 5 of 6 with the generator grading itself, on the same questions. → `02`; `docs/about_the_documents.md`.
- *When is system A better than B?* Only when the gap is larger than the noise band; here about 8 points on 37 questions.

**Security**
- *Indirect prompt injection?* Instructions hidden in retrieved data, not typed by the user; RAG is the classic case. → `03`; `rag/security/`.
- *Layers here?* Scanner on passages, production system prompt, optional spotlighting, exact-copy drop and per-source cap, output filter. Result with the defaults: 0 of 10 fixtures obeyed, but be precise: the scanner removed 7 of the 10 poisoned documents, so only 3 reached the model, and none of those 3 was obeyed (the production prompt alone: 3 of 10 obeyed at 1 copy, 2 at 3 copies; a naive prompt: 5). → `03`; `runs/security__indirect__vllm-models-gpt-oss-20b__copies1/report.json`.
- *Markdown exfiltration?* A poisoned document makes the model write an image whose address carries private data; the client's render makes the request. The fix is on the display side: no images from untrusted domains, an image proxy and an allow-list. → `03`, `04` section 8; `docs/mcp_risks.md`.
- *Why 404 and not 403 for another user's document?* A 403 confirms it exists. → `03`; `rag/api/main.py`.

**Conversation and cost** (design, not built here)
- *How does the model know what "it" means in a follow-up?* It does not; it is stateless. Send the history, and rewrite the follow-up into a standalone question before searching; ask when two readings are equally likely. → `05`, section 1.
- *How do you compact a long conversation?* Recent turns verbatim, older turns as a running summary, key facts kept separately, re-fetchable text dropped, raw log kept. → `05`, section 2.
- *How do you track token cost?* Per request: model, prompt, completion and hidden reasoning tokens, latency, user; cost = tokens x price (GPU time if self-hosted); aggregate and alert; use Langfuse or LangSmith. What exists here: token counts and stage timings per question in the trace. → `05`, section 3.

**System**
- *Streaming and a failed final check?* You cannot unsend. Hold back risky pieces until judged, render safely, then replace the text with the checked answer. → `04`, section 8.
- *Why not LangChain?* A fixed pipeline does not need it; revisit for routing, loops, state or human approval. → `rag/README.md`, "Design decisions".
