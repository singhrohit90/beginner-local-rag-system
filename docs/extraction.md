# How a PDF is read, and what is not handled

Written 2026-10-10 from the code (`rag/ingestion/extract.py`, `clean.py`, `pipeline.py`). Where a statement is general knowledge about other tools and not something this repo does, it says so.

## Short version

The system reads the **text layer** of each PDF page with PyMuPDF and nothing else. Text, headings, code blocks and bookmarks are handled. **Tables, images, figures, graphs and scanned pages are not handled.** There is no page classifier, no layout analysis and no OCR.

## What each kind of content becomes

| In the PDF | What happens now | Where |
|------------|------------------|-------|
| Ordinary text | Kept, in reading order (blocks sorted by position) | `extract.py`, `_read_blocks` |
| Headings | They are just text. The heading-aware chunker uses the PDF's **bookmarks** (the table of contents the PDF carries), not the page layout | `extract_toc`, `rag/ingestion/chunking/heading.py` |
| Code | Detected when 60% or more of a block's characters use a monospaced font; kept with its line breaks and indentation, fenced as a code block | `_block_text`, `build_pages` |
| Superscripts (footnote marks, exponents) | Written with a `^` in front, so "fan-out" plus a superscript does not fuse into one word | `_line_text` |
| Running headers, footers, page numbers | Removed: text in the top or bottom margin that repeats on enough pages, or looks like a footer, or is noise | `build_pages`, `clean.py` |
| **Tables** | **No table detection.** Whatever text the table has comes out as ordinary text blocks in position order, so cells can be joined in the wrong order and the grid is lost. (The golden set has one `table` question out of 45; it is not scored separately.) | nothing |
| **Images, figures, graphs, diagrams** | **Ignored.** Image blocks are skipped (`block["type"] != 0`). The pixels are dropped; text drawn inside an image is lost | `_read_blocks` |
| **Captions under figures** | Kept, if they are real text, as an ordinary paragraph. Nothing links a caption to its figure | nothing |
| **Scanned pages** (no text layer) | A page with no text becomes an empty page. If the whole PDF has no text, the upload fails with "no text could be extracted from this PDF (it may be scanned images; OCR is not supported yet)" | `pipeline.py` |
| Blank pages | An empty page is kept (so page numbers stay right) and counted in a log line: "Extracted N pages, M empty [list]" | `extract_pages` |
| Table of contents **page** | Plain text like any page. (The about-the-documents profile skips it when looking for a preface) | `rag/ingestion/profile.py` |
| Index pages (end of a book) | Plain text like any page | nothing |

## At what point do we know what a page contains?

We don't classify pages. We learn only the outcome after extraction: whether a page produced text or not. There is no point where the system knows "this page has a table and an image". A page with a table, an image and text yields its text blocks and drops the image, and nothing says where one kind of content ended and another began. Knowing the split needs layout analysis (see below), which is not built.

## Library used

**PyMuPDF** (`import pymupdf`; it was called `fitz` in older code, and it is built on the MuPDF C library). `requirements-rag.txt` lists `pymupdf>=1.24`. It gives, per page: text blocks with their position, the font flags of every span (used to detect monospaced code and superscripts), the page size (used to find the margins), and the PDF's bookmarks. It also gives the page count the upload limit uses. The original fork used PyPDF2 for text and pytesseract for OCR (`docs/original_repo_patterns.md`, section 3); neither is used now.

Other libraries in the pipeline are not about PDFs: `sentence-transformers` (embeddings and the reranker), `numpy`, `opensearch-py`, `fastapi` and `uvicorn`.

## Is a 500-page PDF read in a loop or in one go?

In a loop, one page after another, in a single process: `for page in doc` in `_read_blocks`. All pages are collected in a list, cleaned together (the repeated-margin check needs every page), and written to `pages.jsonl` once at the end. Then the whole document is chunked, then embedded in batches of 64 chunks (`sentence-transformers` `encode`, batch size 64), then indexed. For uploads the extraction runs inside a child process with a time and memory limit (`rag/ingestion/sandbox.py`), and only one document is ingested at a time (a lock, because the embedder shares the GPU). **Nothing is parallel across pages**, and the time for 500 pages was not measured.

## Options if tables, figures and scans must be handled

All of this is **general knowledge, from memory, not tried here**; check each tool's current documentation before choosing.

- **Layout detection models** find regions on a page image (text, title, table, figure, formula, caption) with boxes: **DocLayout-YOLO**, **PP-DocLayout** (from the PaddleOCR family), and the layout models inside **Docling** and **MinerU**. They only locate regions; something else must read each one.
- **Document-conversion toolkits** bundle layout, OCR, table structure and reading order and give structured output (Markdown, JSON): **Docling** (IBM), **MinerU** (OpenDataLab), **Marker**, **Unstructured**; hosted ones: Azure Document Intelligence, AWS Textract, Google Document AI.
- **Table-specific tools:** `pdfplumber`, Camelot and Tabula (rule-based, work on text-layer PDFs with ruled lines); table-structure models (TableFormer in Docling, PP-StructureV3's table module) for harder cases.
- **OCR engines** for scans: Tesseract, PaddleOCR, EasyOCR, or an OCR-capable VLM.
- **Vision-language models** (a hosted one, or Qwen2.5-VL, olmOCR) read a page image directly and can describe a figure or turn a chart into a table.
- **Page-image retrieval** (ColPali-style) skips text extraction and embeds the page image itself.

## How different models would be used for different parts of a page

The usual design, and the one the plan in `docs/backlog.md` ("the `Element` contract and OCR handlers") points at:

1. Render or read the page and run a **layout model** to get regions with a type and a box.
2. **Route each region by type:** text goes to the text layer (or OCR if the page is a scan); a table to a table-structure model, producing Markdown or HTML; a figure to a vision-language model for a caption or a chart-to-table; a formula to a formula-recognition model.
3. Put the results back in **reading order** as typed elements (kind, page, box, text), and chunk by element (a table stays one unit with its caption), so retrieval and citations still point at a page and a region.

## Can pages be processed in parallel? Who manages it?

Pages are independent, so yes. It is a standard pattern and you do not write a scheduler:

- **Across pages, CPU work** (rendering, layout detection): a process pool (`concurrent.futures.ProcessPoolExecutor` or `multiprocessing`), results sorted by page number afterwards.
- **Model calls** (a vision model per figure, OCR per page): a thread pool or `asyncio` with a **semaphore** to cap how many are in flight. A server such as vLLM batches concurrent requests itself (continuous batching), so sending several at once is faster than one by one.
- **Many documents, retries, persistence:** a task queue (Celery, RQ, Arq, or a workflow tool such as Ray or Dask).
- **Toolkits** such as Docling and MinerU have their own batching or multi-worker options (general knowledge; check the documentation).
- The limits are GPU memory (on this machine 8 GB, which holds one embedder), the model server's rate, and keeping the page order.

**In this repo:** none of this is built. Extraction is a single loop, model calls are one at a time, and one document is ingested at a time.

## If this is built next

1. Add an `Element` type (kind, page, box, text) next to `Page` in `rag/common/types.py`, with text as the only kind produced today, so nothing else changes.
2. Detect scanned pages (a page with no text but with images) and OCR only those, recording a confidence per page.
3. Try a toolkit (Docling or MinerU) on the two HBase books against the plain-text path, and compare on questions that need a table. Keep `data/golden/` as the yardstick: a change counts only if it beats the noise band (about 8 points on the 37 answerable questions).
