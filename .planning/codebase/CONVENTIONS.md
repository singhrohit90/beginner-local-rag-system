---
last_mapped_commit: a53a2e9a053a09e28fd2a5cbe11629a8ded7d112
last_mapped_at: 2026-10-21
---
# Coding Conventions

**Analysis Date:** 2026-10-21

## Naming Patterns

**Files:**
- Modules are short `snake_case` nouns or verbs naming one step: `rag/query/fusion.py`, `rag/query/select_context.py`, `rag/ingestion/clean.py`, `rag/observe/retrieval_quality/metrics.py`.
- Each pipeline stage is one module; the orchestrator only chooses order and what to skip: `rag/query/pipeline.py`, `rag/ingestion/pipeline.py`.
- Package folders carry an `__init__.py` (`rag/api/__init__.py`, `rag/query/__init__.py`, and so on). Tests are `tests/test_<area>.py` (`tests/test_stream_guard.py`, `tests/test_retrieval.py`). Test helpers that run in child processes live in a plain module, not in the test file: `tests/sandbox_targets.py`.
- Experiments and tools are run with `python -m`, so each has a `__main__` guard (14 modules, for example `rag/experiments/retrieval.py`).

**Functions:**
- `snake_case`, verb-first: `dense_search`, `keyword_search`, `select_context`, `filter_output`, `load_chunkset`, `load_trace`.
- Private helpers start with a single underscore: `_close_when_idle` in `rag/api/main.py`, `_PROMPT_ECHO` in `rag/query/guard.py`, `_run_extract` in tests.
- Route handlers in `rag/api/main.py` are named for the action (`upload`, `ask`, and so on) and stay thin; the work goes through `DocumentService` in `rag/api/service.py`.

**Variables:**
- `snake_case`. Module-level constants in `UPPER_SNAKE_CASE`: `DEFAULT_MAX_UPLOAD_BYTES`, `LOCAL_OWNER`, `STATES` in `rag/api/service.py`; `HEADER_FRACTION` in `rag/common/config.py`; `USABLE_CONFIGS` and `STATIC` in `rag/api/main.py`.
- Loop and math variables are short (`i`, `r`, `k`, `hits`, `scored`) when the scope is a few lines; anything that crosses a function boundary uses a full name (`chunk_id`, `page_start`, `owner`).
- The logger is always `logger = logging.getLogger("rag.<area>")` (see `rag/api/main.py`, `rag/api/service.py`).

**Types:**
- Dataclasses for records passed between stages: `Page`, `Chunk`, `Hit` in `rag/common/types.py`; `StageRecord`, `Trace` in `rag/common/trace.py`; `ChunkSet` in `rag/ingestion/chunking/base.py`. Use `@dataclass(frozen=True)` for value objects (`Scope` in `rag/common/chunk_store.py`, `units.py` in `rag/ingestion/chunking/units.py`, fixtures in `rag/security/fixtures.py`).
- Exception classes are named for the failure in one word and inherit from `Exception`: `NotFound`, `BadUpload`, `TooLarge(BadUpload)` in `rag/api/service.py`.
- Typing uses `typing` generics, not PEP 604 unions. Write `Optional[str]`, `List[Hit]`, `Dict[str, Any]`, as in `rag/common/types.py`. `from typing import ...` appears in 22 modules; `X | None` appears in none. Do not introduce `|` unions, to match.
- Pluggable parts are `typing.Protocol` or small classes with a `name` attribute, for example `RecursiveChunker.name = "recursive"` in `rag/ingestion/chunking/recursive.py` and `Embedder.name` read in `rag/query/pipeline.py`.

## Code Style

**Formatting:**
- No formatter configuration is committed (no `pyproject.toml`, `.editorconfig`, `setup.cfg`, or `ruff`/`black` config in the repo). Follow the existing layout by hand.
- Line length is loose: the longest line in `rag/` and `tests/` is 229 characters and 77 lines exceed 120. Keep new lines at or under 120 characters. Long string tables (`tests/test_stream_guard.py`, `rag/security/fixtures.py`) are the accepted exception.
- Multi-line calls put one argument per line with a trailing comma when the call wraps (see `RagPipeline` construction in `rag/query/pipeline.py`); short calls stay on one line. Some lines pack several keyword arguments with a hanging indent, as in `ContextConfig(...)` in `rag/query/pipeline.py`.
- Double quotes for strings; f-strings for messages (`f"unknown fusion {config.fusion!r}"`). Use `!r` in error messages to show the bad value.
- Blank lines: two between top-level definitions in modules, one between methods.

**Linting:**
- No linter is configured or enforced in the repository. Keep imports used and the code free of unused variables; the existing code has no `# noqa` suppressions.
- Do not add `from __future__ import annotations` (0 modules use it).

## Import Organization

**Order (as observed):**
1. Standard library (`dataclasses`, `typing`, `json`, `pathlib`, `logging`).
2. Third-party (`numpy`, `pymupdf`, `fastapi`, `pydantic`, `pytest`).
3. Project imports from `rag.*`, absolute, never relative.

Some modules mix these groups, for example `rag/api/main.py` puts `starlette` imports between stdlib imports. Prefer the three-group order for new code.

**Path Aliases:**
- None. Imports are always fully qualified from the package root `rag` (for example `from rag.query.configs import RetrievalConfig`). Relative imports are not used in `rag/` or `tests/`.

**Package re-exports:**
- `rag/ingestion/chunking/__init__.py` re-exports the strategies (`RecursiveChunker`, `ParentChildChunker`), and `tests/test_retrieval.py` imports from there. Import from the package `__init__` for chunkers; import from the defining module for everything else.

## Error Handling

**Raise and catch by type, never by message:**
- Configuration or input that is wrong at the call site raises `ValueError` with the bad value in the message: `raise ValueError(f"unknown fusion {config.fusion!r}")` in `rag/query/pipeline.py`. This is the most common raise in the code (28 sites).
- Missing runtime prerequisite raises `RuntimeError` (14 sites), for example a config that asks for a reranker that was not given.
- The API maps domain exceptions to HTTP status in the route, not in the service. `rag/api/main.py` converts `BadUpload` to 400, `TooLarge` to 413, `NotFound` to 404, and unknown chunker to 422 with `HTTPException(status, detail)`. The service layer in `rag/api/service.py` raises `NotFound`, `BadUpload`, `TooLarge` and never `HTTPException`.
- Return 404 for another owner's document, not 403 (CLAUDE.md security rule); the store filters by `Scope.owner`, so a missing and a foreign document take the same path.

**Catching:**
- Catch the narrowest type that the call can raise: `except json.JSONDecodeError`, `except urllib.error.URLError as err`, `except (OSError, ValueError)`.
- `except Exception as err` appears 10 times. Use it only at a boundary that must not crash the caller (a background ingestion job, a judge call in an experiment) and log or record the error with the text of `err`, never silently.
- Do not swallow errors into `None` returns. Failure is either an exception or an explicit state (`STATES = ("queued", "processing", "ready", "failed")` in `rag/api/service.py`).

**Trace errors:**
- Pipeline failures are recorded on the `Trace.error` field (`rag/common/trace.py`) so the observe layer can attribute them. Do not hide an error from the trace.

## Logging

**Framework:** standard `logging`, configured once by `setup_logging()` in `rag/common/log.py` (INFO level, message-only format, third-party HTTP and model libraries held at WARNING).

**Patterns:**
- Use the module logger `logging.getLogger("rag.<area>")`; never call `logging.basicConfig` in a module.
- Use `print()` only in command-line entry points that write a table or report to stdout: `rag/experiments/retrieval.py`, `rag/observe/golden_tools/find_pages.py`, `rag/ingestion/chunking/build.py` (about 16 modules). Library and service code uses the logger.
- Log counts and decisions, not document text or answer text. Uploaded content and the canary string must not reach logs.

## Comments

**When to Comment:**
- Module docstrings describe what the module does and how it fits the flow, in plain sentences; they are long and explanatory (`rag/query/pipeline.py`, `rag/api/main.py`).
- Comments explain *why* a choice was made, often with a pointer to the decision doc: see `# With one document in scope there is nothing to flood...` in `rag/query/pipeline.py`, and the `docs/auth_plan.md` reference in the `rag/api/main.py` docstring.
- Trailing comments give units and meaning on constants: `page_no: int  # 1-based PDF page index (NOT the printed page number)` in `rag/common/types.py`.
- Do not write comments that restate the code.

**Docstrings:**
- Triple-double-quoted, one-line summary for simple functions (`"""Who is calling. There is no login yet..."""`), a short paragraph for classes that carry a design rule (`RecursiveChunker` in `rag/ingestion/chunking/recursive.py`).
- Private helpers may have no docstring.
- Type information is in the signature, not in docstrings. No `:param:` or Google-style sections are used.

## Function Design

**Size:** Pipeline functions are long because they are sequences (`RetrievalPipeline.run` in `rag/query/pipeline.py`). Extract a helper when a block is reused or independently testable; do not split a linear sequence just to shorten it.

**Parameters:**
- Keyword arguments with defaults for configuration (`RecursiveChunker(size=200, overlap=30, code_max=400)` in `rag/ingestion/chunking/recursive.py`; `RagPipeline(..., style="standard", output_filter=True, subject="book")`).
- Pass the `Scope` (owner plus document ids) explicitly into every store call; never rely on a global current owner in service code. The only owner source is `current_owner()` in `rag/api/main.py`.

**Return values:**
- Return dataclasses (`Chunk`, `Trace`, `ChunkSet`) or plain lists of `Hit` rather than dicts when the shape is stable. Use `.to_dict()` only at the serialization boundary.
- Stages return their hits so calls chain: `trace.record(...)` returns `hits` (see `rag/common/trace.py`).

**Mutation:** Prefer returning a new list over in-place edits of inputs; frozen dataclasses for values.

## Module Design

**Exports:** No `__all__` lists. A module exports what it defines; underscore names are private.

**Barrel Files:**
- Only the `chunking` package re-exports its strategies from `__init__.py`. Other packages keep `__init__.py` empty or minimal.
- Do not add a new barrel to hide internals; the orchestrator-plus-steps layout is the documented structure (`rag/README.md`, "Layout").

**Dependency rules (from `rag/README.md` and CLAUDE.md):**
- The two pipelines communicate only through the chunk store (`rag/common/chunk_store.py`). Query code reads chunks through `ChunkStore`, never reads ingestion files directly.
- Only `rag/common/llm.py` knows how a model provider is called. Other modules take an `LLM` object or a spec string.
- Only the `rag/query/guard.py` `StreamGuard` may release streamed answer text.

## Project Behaviour That Must Not Drift

These come from the project `CLAUDE.md` and are enforced by tests and eval results, not by a linter. Treat any change to them as a deliberate, measured change.

- `SYSTEM_PROMPT` in `rag/query/prompt.py` stays word for word. The golden-set results and the LLM disk cache depend on it. Uploads use `DOCUMENT_SYSTEM_PROMPT`.
- Page numbers are PDF page indexes (1-based) everywhere. For the DDIA book, printed page + 22.
- Treat gaps under about 8 points as noise on the 37 answerable golden questions (one question is 2.7 points).
- Never pass `cache_dir=None` for uploaded documents to the LLM cache; `get_llm(spec, cache_dir=None)` keeps the text after a delete.
- Upload chunk ids are `<doc_id>:<chunk_id>` and unique within an owner.
- In `rag/api/static/index.html`, insert untrusted text with `textContent`, never `innerHTML`.
- Stream answers only through `StreamGuard`, and show them as text.

## Adding New Code: Checklist

1. Put the module in the folder that matches its stage (`rag/query/`, `rag/ingestion/`, `rag/observe/`), with a module docstring that says what it does.
2. Use absolute `rag.*` imports, typing generics (`Optional`, `List`), and dataclasses for records.
3. Raise `ValueError`/`RuntimeError` with the bad value; map domain errors to HTTP only in `rag/api/main.py`.
4. Use `logging.getLogger("rag.<area>")`; `print()` only in a `__main__` entry point.
5. Add a test in `tests/test_<area>.py` (see `TESTING.md`).

---

*Convention analysis: 2026-10-21*
