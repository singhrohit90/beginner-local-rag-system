# The models this project uses, and why

Three kinds of model are used. None of them looks at page images: every model here reads text. There is no layout model, no OCR model and no vision model (see `docs/extraction.md`).

| Role | Model | Kind of model | Where it runs | Used for | Code |
|------|-------|---------------|---------------|----------|------|
| Embedder | `sentence-transformers/all-mpnet-base-v2` | Embedding model (a bi-encoder: text in, one vector out). Reads at most 384 tokens | Locally, GPU or CPU, no key | Turning every chunk and every question into a vector for dense search; the semantic chunker also uses it to find topic changes | `rag/common/embed.py` (`SentenceTransformerEmbedder`, `get_embedder`) |
| Reranker (optional) | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Cross-encoder (reads the question and one passage together and gives a relevance score) | Locally | Reordering the top 30 fused candidates; only in the `*_rerank` configs, not the default | `rag/query/rerank.py` (`CrossEncoderReranker`) |
| Generator | `gpt-oss-20b` on the on-prem vLLM server | Reasoning model: it writes hidden "thinking" tokens before the answer, so the client adds a token budget and never shows the thinking | A remote GPU server, reached through an SSH tunnel (PuTTY) | Writing the cited answer, and the "about the documents" answer | `rag/common/llm.py` (`OpenAICompatLLM`) |
| Judge | `qwen2.5:7b` through Ollama | Small instruction-following model (answers directly, no hidden thinking) | Locally | Grading answers against a per-question key-fact checklist (evaluation only; never in the product path) | `rag/common/llm.py` (`OllamaLLM`), `rag/observe/generation_quality/judge.py` |
| Hosted option | `gemini-3.5-flash-lite` | Hosted instruction model | Google's API (needs a key in `.env`) | Early experiments only; dropped because the free tier allows about 20 requests a day per model | `rag/common/llm.py` (`GeminiLLM`) |
| Test doubles | `HashingEmbedder`, `FakeLLM` | Not real models | In memory | Fast tests with no model server | `rag/common/embed.py`, `rag/common/llm.py` |

## Why these, and how sure we are

- **Embedder (mpnet).** Local, free, no key, no quota, and nothing leaves the machine; a strong general-purpose sentence model that fits an 8 GB GPU. The reason was not written down when it was chosen, and **no other embedder was benchmarked here**, so "best" is not claimed. Its 384-token limit shapes chunk size: text past the limit is never embedded.
- **Reranker (MiniLM cross-encoder).** The reason for having one is in `rag/query/rerank.py`: a bi-encoder is quick but misses fine detail, and a cross-encoder reads both texts at once, so it is far more accurate on a short list. The small model keeps the cost low (measured about 138 ms against 21.7 ms for dense search alone, GPU use not recorded; see `interview/01_retrieval_and_chunking.md`). It is not on by default.
- **Generator (gpt-oss-20b).** It is the model the user's environment provides on-prem, so documents and questions stay in-house, and there is no per-request quota (the hosted free tier ran out). It is a reasoning model, which affects how the client works: the token limit sent is the answer budget plus 3000 for thinking, an answer cut off during thinking is retried once with a larger budget, and the thinking is never shown to a user because it can quote the system prompt. Measured on the 37 answerable golden questions: correct 0.750 and faithful 0.838 in memory (`rag/README.md`, Step 9).
- **Judge (qwen2.5:7b).** Local and free, so a whole evaluation can be rerun at no cost. Its weakness is known and measured: on the about-the-documents questions it marked right answers wrong (1 of 5 correct, against 5 of 6 when the generator graded itself; `docs/about_the_documents.md`). Use a stronger judge that is not the generator before quoting a number.
- **Hosted Gemini.** Kept as an option; the code needs only a provider class, because `rag/common/llm.py` is the one file that knows how a provider's request looks.

## Reasoning model, instruction model, embedding model: the difference

- An **embedding model** does not write text. It maps text to a vector so that similar meanings are close; it is the only thing the vector search uses.
- An **instruction model** (qwen2.5:7b, Gemini flash-lite) is a language model tuned to follow an instruction and reply directly. Cheaper and faster, weaker on hard reasoning.
- A **reasoning model** (gpt-oss-20b) spends tokens thinking before it replies, which tends to help with multi-step or constrained questions and costs more tokens and time to the first visible word. That is why streaming shows nothing for the first few seconds (4.4 s measured on one question).
- A **cross-encoder** is neither: it scores one question-passage pair and is used only to rank.

## What is not used

No layout-detection model (DocLayout-YOLO, PP-DocLayout), no document-conversion toolkit (Docling, MinerU), no OCR engine, and no vision-language model. Pages are read with PyMuPDF's text layer only. What that means for tables, figures and scans, and what the options are, is in `docs/extraction.md`.
