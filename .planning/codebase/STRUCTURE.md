---
last_mapped_commit: a53a2e9a053a09e28fd2a5cbe11629a8ded7d112
last_mapped_at: 2026-10-21
---
# Codebase Structure

**Analysis Date:** 2026-10-21

## Directory Layout

```
beginner-local-rag-system/
├── rag/                    # All Python source (the package)
│   ├── common/             # Shared types, config, store, LLM/embedder adapters
│   ├── ingestion/          # PDF -> pages -> chunks -> vectors
│   │   └── chunking/       # Five chunking strategies
│   ├── query/              # Retrieval, fusion, context selection, generation, guards
│   ├── observe/            # Evaluation: metrics, judges, golden set
│   │   ├── retrieval_quality/
│   │   ├── generation_quality/
│   │   └── golden_tools/
│   ├── security/           # Poisoned fixtures and injection test harness
│   ├── experiments/        # Scripts that print comparison tables
│   └── api/                # FastAPI app, service layer, chat page
│       └── static/         # index.html (the UI)
├── tests/                  # pytest suite (flat, one file per area)
├── docs/                   # Design notes (auth, MCP risks, about-the-documents, models, backlog, extraction)
├── interview/              # Numbered interview notes (01 to 06) and README
├── data/                   # Mostly gitignored data; data/golden/ is committed
│   ├── raw/                # Source PDFs (gitignored)
│   ├── processed/          # Extraction, chunks, index, llm_cache (gitignored)
│   ├── golden/             # Evaluation questions (committed)
│   └── uploads/            # Per-upload workspaces (gitignored)
├── runs/                   # Per-query traces and eval reports (gitignored)
├── .planning/codebase/     # Generated codebase maps (this document)
├── .github/ or CI files    # Not detected in the tracked file list
├── docker-compose.yml      # OpenSearch service (security plugin off, port on 127.0.0.1 only)
├── requirements-rag.txt    # Python dependencies
├── .env.example            # Committed template; the real .env is gitignored
├── .gitignore
├── CLAUDE.md               # Project instructions for Claude
├── README.md               # Project overview
├── LICENSE
└── rag/GOLDEN_QUESTIONS_GUIDE.md   # How to write the golden set
```

## Directory Purposes

**`rag/common/`:**
- Purpose: Everything both pipelines share.
- Contains: `types.py`, `trace.py`, `config.py`, `chunk_store.py`, `opensearch_store.py`, `store.py`, `bm25.py`, `stem.py`, `embed.py`, `llm.py`, `llm_check.py`, `secrets.py`, `log.py`.
- Key files: `rag/common/types.py` (data objects), `rag/common/chunk_store.py` (storage interface), `rag/common/config.py` (paths and thresholds).

**`rag/ingestion/`:**
- Purpose: Ingestion pipeline and its steps.
- Contains: `pipeline.py` (orchestrator), `extract.py`, `clean.py`, `chunk.py`, `index.py`, `profile.py`, `sandbox.py`, `export_text.py`.
- Key files: `rag/ingestion/pipeline.py`, `rag/ingestion/extract.py`.

**`rag/ingestion/chunking/`:**
- Purpose: Chunking strategies and their helpers.
- Contains: `base.py` (`ChunkSet`, `load_chunkset`), `document.py` (`Document`), `units.py` (word and sentence helpers), `recursive.py`, `fixed.py`, `heading.py`, `parent_child.py`, `semantic.py`, `stats.py`, `build.py`.
- Key files: `recursive.py` (the simplest real chunker, first to read), `build.py` (builds all strategies and writes `data/processed/chunks/`).

**`rag/query/`:**
- Purpose: Query pipeline and its steps.
- Contains: `pipeline.py`, `retrieve.py`, `fusion.py`, `rerank.py`, `select_context.py`, `generate.py`, `prompt.py`, `guard.py`, `configs.py`, `about.py`.
- Key files: `rag/query/pipeline.py` (whole query path on one screen), `rag/query/prompt.py` (`SYSTEM_PROMPT` must stay word for word), `rag/query/guard.py`.

**`rag/observe/`:**
- Purpose: Scoring. Reads traces and answers; not on the request path.
- Contains: `golden.py`, `retrieval_quality/` (`metrics.py`, `run_eval.py`, `diagnose.py`), `generation_quality/` (`judge.py`, `answers.py`, `calibrate_judge.py`), `golden_tools/` (`find_pages.py`, `verify_golden.py`, `export_review.py`, `clean_paste.py`).
- Key files: `rag/observe/retrieval_quality/metrics.py`, `rag/observe/generation_quality/answers.py`.

**`rag/security/`:**
- Purpose: Injection test harness.
- Contains: `fixtures.py` (ten poisoned documents), `defenses.py` (baseline and switchable defences), `indirect.py` (runner).

**`rag/experiments/`:**
- Purpose: Full-comparison scripts that print tables: `retrieval.py`, `answer.py`, `about.py`.

**`rag/api/`:**
- Purpose: HTTP surface and chat UI.
- Contains: `main.py` (routes and app factory), `service.py` (`DocumentService`), `static/index.html`.
- Key files: `rag/api/main.py` (`current_owner`, `create_app`, `build_default_service`), `rag/api/service.py` (upload workflow, status, asks, deletion).

**`tests/`:**
- Purpose: pytest suite. Flat layout, `test_<area>.py` per area, plus `sandbox_targets.py` (helper module for sandbox tests).
- Examples: `tests/test_api.py`, `tests/test_chunk_store.py`, `tests/test_chunking.py`, `tests/test_stream_guard.py`, `tests/test_retrieval.py`, `tests/test_security.py`.
- Note: `tests/test_vllm.py` and `tests/test_ollama.py` exist; provider tests.

**`docs/`:**
- Purpose: Design decisions and risks. Read `docs/auth_plan.md` and `docs/mcp_risks.md` before exposing the API.

**`interview/`:**
- Purpose: Learning notes, numbered `01_` to `06_`. Each point is labelled built, designed, general, or not measured (`CLAUDE.md`).

## Key File Locations

**Entry Points:**
- `rag/api/main.py`: web app (`rag.api.main:app`).
- `rag/ingestion/pipeline.py`: ingestion CLI.
- `rag/query/pipeline.py`: query path (called, no CLI).
- `rag/experiments/retrieval.py`, `rag/experiments/answer.py`: comparison runs.

**Configuration:**
- `rag/common/config.py`: paths, extraction thresholds.
- `rag/query/configs.py`: named retrieval configs.
- `.env.example`: environment variable names (`RAG_STORE`, `RAG_LLM`, `RAG_EMBEDDER`, `GEMINI_API_KEY`). The `.env` file itself is not read by this map.
- `docker-compose.yml`: OpenSearch.
- `requirements-rag.txt`: Python dependencies.

**Core Logic:**
- `rag/query/pipeline.py`, `rag/query/fusion.py`, `rag/query/select_context.py`, `rag/query/generate.py`: query path.
- `rag/ingestion/chunking/recursive.py`, `rag/ingestion/extract.py`: ingestion path.
- `rag/common/chunk_store.py`, `rag/common/opensearch_store.py`: storage.

**Testing:**
- `tests/`: all tests. Run with `python -m pytest tests -q`; list with `--collect-only -q`.
- `data/golden/ddia_questions.jsonl`: golden set (committed).

## Naming Conventions

**Files:**
- Modules are lowercase with underscores: `select_context.py`, `opensearch_store.py`, `calibrate_judge.py`.
- Tests are `tests/test_<area>.py`: `test_chunk_store.py`, `test_stream_guard.py`.
- Step modules are named for the verb or noun they perform: `extract.py`, `chunk.py`, `index.py`, `retrieve.py`, `fusion.py`, `rerank.py`, `generate.py`, `guard.py`.

**Directories:**
- Lowercase, single word or underscore-free: `common`, `ingestion`, `query`, `observe`, `security`, `experiments`, `api`. Sub-packages named for the strategy or quality area: `chunking`, `retrieval_quality`, `generation_quality`, `golden_tools`.

**Identifiers:**
- Upload document ids are 12 lowercase hex characters (`DOC_ID` in `rag/api/service.py`).
- Chunk ids for uploads are qualified as `<doc_id>:<chunk_id>` and must be unique within an owner (`CLAUDE.md`, `rag/common/chunk_store.py`).
- Page numbers are 1-based PDF page indexes. For the DDIA book, printed page + 22 (`CLAUDE.md`).

**Per-owner index names (OpenSearch):** `rag_c_*` for searchable chunks, `rag_p_*` for parent chunks, one documents index per embedding model (`rag/README.md` Step 9).

## Where to Add New Code

**New query retrieval stage:**
- Implementation: a function in `rag/query/` (for example, a new `fusion` method in `rag/query/fusion.py`).
- Wire it into `RetrievalPipeline.run()` in `rag/query/pipeline.py`, recording a trace stage.
- Add a switch to `RetrievalConfig` in `rag/query/configs.py`.
- Tests: `tests/test_retrieval.py`.

**New chunking strategy:**
- Implementation: `rag/ingestion/chunking/<name>.py`, subclassing the base in `rag/ingestion/chunking/base.py`.
- Register the name in `STRATEGIES` and `make_chunker()` in `rag/ingestion/chunk.py`.
- Tests: `tests/test_chunking.py`.

**New LLM or embedder provider:**
- Implementation: add a branch in `rag/common/llm.py` or `rag/common/embed.py` (the spec-string factories).
- Tests: a file like `tests/test_ollama.py`.

**New API route:**
- Route: `rag/api/main.py` (inside `create_app`), with request model classes next to `AskRequest`.
- Behaviour: a method on `DocumentService` in `rag/api/service.py`, keeping the route thin.
- Owner: always from `current_owner()`; never from a header or body field.
- Tests: `tests/test_api.py` or `tests/test_stream_api.py`.

**New storage backend:**
- Implementation: a new class implementing `ChunkStore` in `rag/common/`, modelled on `rag/common/opensearch_store.py`.
- Tests: add the backend to the shared checks in `tests/test_chunk_store.py`.

**New evaluation metric:**
- Implementation: `rag/observe/retrieval_quality/metrics.py` or `rag/observe/generation_quality/`.
- Experiment script: `rag/experiments/`.

**New security fixture or defence:**
- Fixtures: `rag/security/fixtures.py`. Defences: `rag/security/defenses.py`. Runs: `rag/security/indirect.py`.
- Production guards go in `rag/query/guard.py`, not in `rag/security/`.

**Utilities:**
- Shared, used by both pipelines: `rag/common/`.
- Ingestion-only helper: `rag/ingestion/chunking/units.py` for chunking, `rag/ingestion/clean.py` for text cleaning.

**Frontend:**
- Single file: `rag/api/static/index.html`. Untrusted text goes into the DOM with `textContent`, never `innerHTML` (`CLAUDE.md`).

## Special Directories

**`data/`:**
- Purpose: All inputs and derived artifacts.
- Generated: Yes (`processed/`, `uploads/`, index and cache directories).
- Committed: Partly. `data/golden/` is committed; `data/raw/`, `data/processed/`, `data/uploads/` are gitignored (`CLAUDE.md`).

**`runs/`:**
- Purpose: Per-query traces (`runs/<run_name>/traces/`) and eval reports (`report.json`, `per_question.jsonl`).
- Generated: Yes. Committed: No.

**`data/uploads/<doc_id>/`:**
- Purpose: One folder per uploaded document: `source.pdf`, `status.json`, `pages.jsonl`, `toc.json`, `chunks/`, `index/`, `chat/`.
- Generated: Yes. Committed: No. Deleting the folder removes all data kept about the document.

**`.planning/codebase/`:**
- Purpose: Generated codebase maps used by GSD commands.
- Generated: Yes. Committed: Decision for the user.

**Scope note:** This map covers the full repository. No `--paths` restriction was applied.

---

*Structure analysis: 2026-10-21*
