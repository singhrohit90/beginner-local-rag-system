# Reading documents, and the models used

> **This is a summary. For the details, see [`docs/extraction.md`](../docs/extraction.md) (how a PDF is read and what is not handled) and [`docs/models.md`](../docs/models.md) (every model, its kind, and why it was chosen).**

Status labels: **Built** (code and tests exist), **Not built**, **General** (interview knowledge with no code here).

---

## 1. How do you handle tables, images, figures and scans?

**Short answer.** Today only the text layer is read, with PyMuPDF. Text, code blocks, headings (through the PDF's bookmarks) are handled, and running headers and footers are removed. Tables come out as plain text in position order, so the grid is lost. Images, figures and graphs are skipped, so any text drawn inside them is lost. A fully scanned PDF is refused with "OCR is not supported yet". There is no page classifier and no layout analysis. **Not built:** tables, images, OCR.

**In this repo.** `rag/ingestion/extract.py` (`_read_blocks` skips image blocks), `rag/ingestion/clean.py`, `rag/ingestion/pipeline.py` (the no-text error). Plan: `docs/backlog.md`, "the `Element` contract and OCR handlers".

**Follow-ups.** How would you know a page has a table? (Layout detection; we have none.) How do captions stay linked to figures? (They do not here; a layout model plus an element type would.)

## 2. At what point do you know what a page contains, and how do you split a mixed page?

**Short answer.** We don't classify pages; we only learn afterwards whether a page produced text. On a page with text, a table and an image, the text blocks come through in reading order, the image is dropped, and nothing marks where the table was. Knowing the split needs layout analysis: a model that finds regions (text, table, figure, formula) with boxes. **Not built.**

## 3. Which library, and what are the alternatives?

**Short answer.** PyMuPDF (`import pymupdf`, older name `fitz`, built on MuPDF). It gives text with positions, font flags (used to find monospaced code), bookmarks and the page count. **General, not tried here:** pdfplumber, Camelot or Tabula for tables; Docling, MinerU, Marker, Unstructured as conversion toolkits; DocLayout-YOLO and PP-DocLayout as layout detectors; Tesseract or PaddleOCR for OCR; vision-language models that read a page image; hosted services (Azure Document Intelligence, AWS Textract, Google Document AI). None of the toolkits or layout models is used here.

## 4. Is a 500-page PDF read in one go or in a loop? Can it run in parallel?

**Short answer.** A loop, page after page, in one process (inside a child process with time and memory limits for uploads). The pages are collected and written once, then the whole document is chunked, embedded in batches of 64 and indexed. Nothing is parallel across pages and the time was not measured. **General:** pages are independent, so a process pool (CPU work), threads or asyncio with a semaphore (model calls; a server such as vLLM batches concurrent requests itself) and a task queue (Celery, RQ, Ray) for many documents are the standard way. You do not write a scheduler.

## 5. When a page has several kinds of content, how do you use different models?

**Short answer.** Detect regions with a layout model, route each by type (text to the text layer or OCR, a table to a table-structure model, a figure to a vision-language model, a formula to a formula model), then merge the results back in reading order as typed elements and chunk by element. This is the planned `Element` design. **Not built.**

## 6. Which models do you use, and why?

**Short answer.** Four jobs, all text-only:
- **Embedding model**, `all-mpnet-base-v2`: turns chunks and questions into vectors for dense search; reads at most 384 tokens. Local and free; the reason was not recorded and no other embedder was benchmarked.
- **Cross-encoder reranker**, `ms-marco-MiniLM-L-6-v2` (optional): reads the question and a passage together to reorder the top 30 candidates; more accurate than a bi-encoder, slower.
- **Reasoning model**, `gpt-oss-20b` on the on-prem server: writes the answers. It thinks before it answers, so the client adds a token budget and never shows the thinking. Chosen because it is available in-house with no quota.
- **Instruction model**, `qwen2.5:7b`: grades answers (evaluation only). Cheap and local; its weakness is measured, it marked right answers wrong.

**The difference, in a line each.** An embedding model maps text to a vector and writes nothing. An instruction model replies directly. A reasoning model spends hidden tokens thinking first, so it is slower to the first word. A cross-encoder scores one pair and is only used to rank.

**In this repo.** `rag/common/embed.py`, `rag/query/rerank.py`, `rag/common/llm.py`, `rag/observe/generation_quality/judge.py`.

**Follow-ups.** Why not a bigger embedder? (Not benchmarked; the limit that matters is the 384-token input.) Why is the judge a different model from the generator? (A model grading its own answers is lenient; measured here as 5 of 6 correct against 1 of 5 with the small judge on the same questions.)
