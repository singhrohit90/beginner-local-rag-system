---
last_mapped_commit: a53a2e9a053a09e28fd2a5cbe11629a8ded7d112
last_mapped_at: 2026-10-21
---
# Testing Patterns

**Analysis Date:** 2026-10-21

## Test Framework

**Runner:**
- pytest (`pytest>=8` in `requirements-rag.txt`)
- No pytest configuration file exists: no `pytest.ini`, `pyproject.toml`, `setup.cfg`, `tox.ini`, and no `conftest.py` at any level. Defaults apply.
- Collection: 593 tests (`python -m pytest tests --collect-only -q`, last line `593 tests collected`).

**Assertion Library:**
- Plain `assert` statements; `pytest.approx` for floats (`tests/test_retrieval.py`); `pytest.raises` for errors.

**Run Commands (from the project `CLAUDE.md`):**

```bash
python -m pytest tests -q                                  # Run all tests (about 3 min quiet, about 10 min when shared)
python -m pytest tests --collect-only -q                   # List without running
python -m pytest tests --collect-only -q | tail -1         # Count only (593 collected)
python -m pytest tests/test_stream_guard.py -q             # One module (no wrapper; tests are plain files)
python -m rag.experiments.retrieval --chunkers semantic --configs weighted   # Retrieval regression check (not pytest)
python -m rag.common.llm_check                             # Model server reachability (not pytest)
```

- Watch mode and coverage are not configured. No `pytest-cov`, `pytest-watch`, or coverage config is in the repo or `requirements-rag.txt`.
- Do not run the full suite as a routine check when a single module answers the question; the full run is minutes long and the OpenSearch tests need the database.

**Regression baseline (from `CLAUDE.md`):**
- `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` must show **hit@5 0.865, mrr 0.663** after a refactor. Update these numbers only if the golden set or the chunkers change.

## Test File Organization

**Location:**
- All tests live in one flat folder, `tests/`, separate from the code. Nothing is co-located with `rag/`.
- `tests/__init__.py` exists, so tests import the package as `tests.<module>` when needed.

**Naming:**
- `test_<area>.py` for a module or feature: `test_chunk_store.py`, `test_api.py`, `test_stream_api.py`, `test_stream_guard.py`, `test_sandbox.py`, `test_secrets.py`, `test_golden_verify.py`.
- Test functions are `test_<behaviour in words>`: `test_upload_index_and_ask_returns_answer_passages_and_stages`, `test_rrf_uses_ranks_only`, `test_bm25_ranks_rare_term_and_length_normalises`. The name states the behaviour, not the method.
- Helpers used by child processes sit in a plain module: `tests/sandbox_targets.py` (no heavy imports, because the sandbox child imports it before running a worker).

**Structure:**

```
tests/
  __init__.py
  sandbox_targets.py      # worker functions for test_sandbox.py
  test_<area>.py          # one file per area, flat
```

Test modules cover, by area: chunking (`test_chunking.py`, `test_extract.py`, `test_clean_paste.py`, `test_export_text.py`), retrieval (`test_retrieval.py`, `test_bm25_stem.py`, `test_chunk_store.py`), generation (`test_generation.py`, `test_llm_stream.py`, `test_stream_api.py`), security (`test_security.py`, `test_stream_guard.py`, `test_secrets.py`, `test_sandbox.py`), evaluation (`test_eval.py`, `test_golden_verify.py`, `test_about.py`, `test_about_experiment.py`) and the HTTP API (`test_api.py`, `test_stream_api.py`).

## Test Structure

**Suite Organization:** flat functions, no classes. Module-level helper builders and constants sit at the top, then the tests.

```python

# tests/test_retrieval.py (pattern)

def make_chunk(i, text, page=1, span=None):
    start = span[0] if span else i * 1000
    end = span[1] if span else start + len(text)
    return Chunk(f"c{i}", text, page, page, "test", meta={"span": [start, end]})

def test_rrf_uses_ranks_only():
    a = [(1, 99.0), (2, 50.0), (3, 1.0)]
    b = [(3, 0.9), (1, 0.8)]
    fused = dict(fusion.rrf([a, b], k=60))
    assert fused[1] == pytest.approx(1 / 61 + 1 / 62)
```

**API tests build the app from a service factory:**

```python

# tests/test_api.py (pattern)

def make_client(tmp_path, llm=None):
    service = DocumentService(
        root=tmp_path / "uploads", embedder=HashingEmbedder(), embedder_spec="hash",
        llm=llm or FakeLLM(lambda system, user: "Copies live on several nodes [S1]."),
    )
    return TestClient(create_app(service, allowed_hosts=("testserver",))), service
```

- Use `fastapi.testclient.TestClient` on `create_app(...)`. Build a real `DocumentService` with `tmp_path` as its root; do not mock the service.
- Auth is faked by overriding `current_owner` in `rag/api/main.py` (the docstring says tests override it to act as two users).

**Setup and teardown:**
- Use pytest's `tmp_path` for every file the code writes (uploads, traces, caches). No test writes into `data/` or `runs/`.
- Real PDFs are built in memory with `pymupdf` (`make_pdf(*page_texts)` in `tests/test_api.py`), so a test controls exactly the text on each page.
- OpenSearch fixtures generate a unique prefix per test and drop their indexes afterward (`unique_prefix()`, `drop_indexes()` in `tests/test_chunk_store.py`).

**Assertion style:**
- Assert the whole structure when the shape matters (`assert [row for row, _ in ranked][:2] == [1, 2]`), and the ordering or relative score when behaviour does (`ranked[0][1] > ranked[1][1] > 0`).
- Floating point uses `pytest.approx`.
- Compare the streamed and ordinary responses for equality, not just presence (`test_the_streamed_response_equals_the_ordinary_one` in `tests/test_stream_api.py`).

## Parametrization

Hostile and benign inputs are tables, one test per row:

```python

# tests/test_stream_guard.py (pattern)

@pytest.mark.parametrize("name", list(HOSTILE))
def test_...(name): ...
```

- `HOSTILE` and `BENIGN` dicts map a short name to an input; the name appears in the test id, so a failure names the case. `SIZES` controls chunk sizes for streaming.
- Add new attack or edge cases as dict rows, not as copies of the test function.

## Mocking

**Framework:** no mocking library. Tests use `pytest`'s `monkeypatch` fixture and in-repo fakes.

**Fakes provided by the code (preferred):**
- `FakeLLM` (from `rag/common/llm.py`) takes a function `lambda system, user: "..."`. Use it instead of any network model.
- `HashingEmbedder` (from `rag/common/embed.py`) is the offline embedder; tests and the API use it, not the sentence-transformers model.
- `KeywordOverlapReranker` (from `rag/query/rerank.py`) is the offline reranker.

**Patterns:**

```python

# monkeypatch a module attribute (tests/test_llm_stream.py)

monkeypatch.setattr("rag.common.llm.time.sleep", lambda seconds: None)

# monkeypatch an environment-driven value, then reload the code that reads it (tests/test_secrets.py)

got = load(tmp_path, monkeypatch, ...)
```

- Patch the name where it is used, by dotted string path (`"rag.common.llm.time.sleep"`), as in the existing tests.
- Remove waits: patching `time.sleep` to a no-op is the standard way to test retry backoff.

**Network failures:**
- A closed local port times out on the development machine instead of refusing. Test "connection refused" by patching `urllib.request.urlopen` to raise `urllib.error.URLError(ConnectionRefusedError())` (CLAUDE.md). Do not rely on a real closed port.

**What to Mock:**
- The model providers (use `FakeLLM`), the network call inside a provider, `time.sleep` in retry loops.
- The environment and secret lookup (monkeypatch `os.environ` or the loader) in `tests/test_secrets.py`.

**What NOT to Mock:**
- The chunkers, the BM25 index, fusion, `select_context`, the guard, the trace. These are pure code and are tested directly or through the real pipeline.
- The PDF extractor: build a real PDF with `pymupdf` instead (`make_pdf`).
- The chunk store. `MemoryChunkStore` is the real in-memory implementation; the OpenSearch store runs the same tests when the database is up (parametrized fixture, below).

## Fixtures and Factories

**Test Data:**
- Inline text constants at module top: `REPLICATION`, `COMPACTION`, `POISONED` in `tests/test_api.py`. Each is a sentence repeated to a fixed length so chunkers produce predictable chunks.
- Factories are small functions: `make_chunk`, `make_pdf`, `make_client`, `upload`, `make_service`.
- `rag/security/fixtures.py` holds the ten poisoned documents for the injection harness (`rag/security/indirect.py`). These are data, not test code, and are shared with the experiments.

**Pytest fixtures:**
- `tmp_path`, `monkeypatch` (built in).
- Project fixtures are local to a module: a parametrized `params=["memory", "opensearch"]` store fixture in `tests/test_chunk_store.py` runs each store test on both backends (skips the OpenSearch leg when the database is down).

**Location:**
- No shared fixtures file. Put a fixture in the test module that uses it; move it to `tests/conftest.py` only when two modules need the same one (no `conftest.py` exists yet).

## Skipping External Services

- OpenSearch-dependent tests skip, not fail, when the database is not reachable. Pattern from `tests/test_chunk_store.py`:

```python
pytest.skip(f"OpenSearch is not running at {OPENSEARCH_URL} (docker compose up -d opensearch)")
```

- The URL comes from `RAG_OPENSEARCH_URL` (default `http://127.0.0.1:9200`). The probe uses `timeout=2, max_retries=0`.
- Skip also for a feature that exists only in one backend: `pytest.skip("copy() is only part of the in-memory store, ...")`. State the reason in the message.
- Start the database with `cat docker-compose.yml | wsl -d Ubuntu-24.04 -- docker compose -f - up -d opensearch` and keep WSL awake (CLAUDE.md). Without it, the OpenSearch cases are silently skipped in the count.

## Timing-Sensitive Tests

- Wait for the state the test checks, not a fixed sleep: use an `Event`, or poll a condition with a 30 second ceiling (CLAUDE.md). The API ingests in the background, so tests poll `GET /v1/documents/{id}` until `state == "ready"`.
- Fixed `time.sleep` in a test is flaky under parallel load on this machine. Replace it with polling.

## Child Processes

- Sandbox tests (`tests/test_sandbox.py`) spawn children through `rag/ingestion/sandbox.py`. Worker functions go in `tests/sandbox_targets.py`.
- The sandbox children are spawned, so any script that uses `multiprocessing` must keep its entry code under `if __name__ == "__main__"` and must not run from stdin on Windows (CLAUDE.md).

## Coverage

**Requirements:** none enforced. No coverage tool is configured.

**View Coverage:** not configured. To measure locally, add `pytest-cov` ad hoc: `python -m pytest tests -q --cov=rag` (requires installing `pytest-cov`; not in `requirements-rag.txt`).

## Test Types

**Unit tests:**
- Pure functions and single steps: tokenization, BM25 scoring, RRF and weighted fusion, chunkers (`tests/test_chunking.py`), cleaning (`tests/test_clean_paste.py`), stream guard (`tests/test_stream_guard.py`), trace save and load.

**Integration tests:**
- Pipeline and HTTP tests run the real code path with offline fakes: upload through `TestClient`, background ingestion, ask, stream, delete (`tests/test_api.py`, `tests/test_stream_api.py`). These are the main regression net for the API.
- OpenSearch store tests run the same store contract against a real database (`tests/test_chunk_store.py`), skipped when it is down.

**End-to-end / evaluation:**
- Not run by pytest. The evaluation scripts are the end-to-end check: `python -m rag.experiments.retrieval` (retrieval) and `python -m rag.experiments.answer` (answers, needs a model). Their numbers are compared to the baseline above, not asserted in tests.
- Tests that need a live model server are not separated by a marker or a directory; check each module before relying on the default run.

## Common Patterns

**Async / streaming:**
- The API streams answers. Test streaming through `TestClient` by reading the streamed body and comparing it with the ordinary response (`tests/test_stream_api.py`). Test the guard by feeding text in chunks of every size in `SIZES` (`tests/test_stream_guard.py`), so a boundary bug at any split point fails.

**Error testing:**

```python

# expect a specific error type with pytest.raises (illustrative; match the message text in the code under test)

with pytest.raises(ValueError, match="unknown fusion"):
    pipeline.run(...)
```

- Test HTTP error mapping by status code: `assert response.status_code == 404` for another owner's document, not 403 (CLAUDE.md rule).
- Test retry behaviour by counting calls: a server-error response is retried, a client-error response is not (`tests/test_vllm.py`, not opened in this mapping).

**Security regression tests:**
- Each defence has a test that proves the attack fails with the defence on and succeeds with it off. The canary `CANARY-7f3a91` must never appear in any released answer; assert its absence on every output path.
- Add a test before a fix in security code, and prove it fails on the old code (see below).

## Proving a Regression Test Fails on Old Code

From the project `CLAUDE.md`:

```bash
git stash push -q -m <unique-tag> -- rag   # set aside the fix, keep the test
python -m pytest tests/<file>.py::<test> -q   # must FAIL here
git stash pop -q                            # restore the fix
```

- Always give the stash a unique message, because the stash stack is shared by every worktree.
- Run the single test id, not the full suite.

## Adding a Test: Checklist

1. Create or extend `tests/test_<area>.py`; add a helper builder at module top if the test needs one.
2. Use `tmp_path` for any file, `FakeLLM` and `HashingEmbedder` for models, and a real `pymupdf` PDF for documents.
3. For a table of inputs, use `@pytest.mark.parametrize` with dict keys as ids.
4. For a timing condition, poll with a ceiling; never add a fixed sleep.
5. For a service that may be down, `pytest.skip` with the start command in the message.
6. Run the single module (`python -m pytest tests/test_<area>.py -q`); run the full suite only when the change touches the shared path.
7. For retrieval changes, run the regression check and compare with hit@5 0.865 and mrr 0.663.

---

*Testing analysis: 2026-10-21*
