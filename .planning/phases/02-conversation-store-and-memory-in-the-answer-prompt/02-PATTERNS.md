# Phase 2: Conversation store and memory in the answer prompt - Pattern Map

**Mapped:** 2026-10-22
**Files analyzed:** 7 (2 new, 5 modified)
**Analogs found:** 7 / 7 (all tracked source; `rag/query/history.py` does not exist yet, shape from `01-05-PLAN.md`)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `rag/api/conversations.py` (new) | service / store | file-I/O, CRUD, lock-guarded | `rag/api/service.py` (`DocumentService`: `_retry`, `_read_json`, `_atomic_write`, `_dir`, `_remove_tree`, exceptions) | role-match (same layer, same file idioms) |
| `rag/api/service.py` (mod) | service | request-response + streaming | itself (`_retrieve`, `_describe`, `ask_documents*`, `delete`) | exact (edit in place) |
| `rag/api/main.py` (mod) | route | request-response + SSE | itself (`AskRequest`, `guarded`, `stream_request`, four lambdas) | exact |
| `rag/query/history.py` (Phase 1 file, mod) | utility (pure) | transform | `01-05-PLAN.md` spec; style from `rag/query/guard.py` | spec-match |
| `tests/test_conversations.py` (new) | test | unit + threaded service tests | `tests/test_api.py` lines 776-800 (`_BlockingStore`, `_race_service`) | role-match |
| `tests/test_api.py` (mod) | test | request-response | itself (`make_client`, `two_users`) | exact |
| `tests/test_stream_api.py` (mod) | test | streaming | itself (`frames`, `ask_stream`) | exact |

## Pattern Assignments

### `rag/api/conversations.py` (store, file-I/O)

**Analog:** `rag/api/service.py`. Copy idioms, do not import them (D-07: the store cannot import `service.py`, which imports the store; define exceptions as plain `Exception` subclasses).

**Module header / logger / exceptions** (service.py 11-58):
```python
logger = logging.getLogger("rag.api")   # use "rag.api" or "rag.conversations"; never basicConfig
DOC_ID = re.compile(r"^[0-9a-f]{12}$")

class NotFound(Exception):
    pass
class BadUpload(Exception):
    pass
class TooLarge(BadUpload):
    """The file is over the size limit; the API reports it as 413."""
```
New: `class NoSuchConversation(Exception)`, `ConversationFull(Exception)`, `ConversationBusy(Exception)`, each with a docstring or `pass`. Typing uses `Optional`/`List`/`Dict`, no `|`, no `from __future__`.

**Retry + atomic write to copy** (service.py 106-128):
```python
@staticmethod
def _retry(action, errors, seconds: float = 2.0):
    deadline = time.monotonic() + seconds
    while True:
        try:
            return action()
        except errors:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.02)

@classmethod
def _atomic_write(cls, path: Path, text: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    cls._retry(lambda: os.replace(temporary, path), PermissionError)
```
Read with `_retry(lambda: json.loads(path.read_text(encoding="utf-8")), (PermissionError, json.JSONDecodeError))` (service.py 120-121).

**Liveness predicate to reuse (supplied by the service as `alive`)** (service.py 98-104):
```python
def _dir(self, doc_id: str) -> Path:
    if not DOC_ID.match(doc_id):
        raise NotFound(doc_id)
    path = self.root / doc_id
    if doc_id in self._deleting or not path.is_dir():
        raise NotFound(doc_id)
    return path
```
Writer must never `mkdir(parents=True)` under a document folder (D-03); catch `FileNotFoundError` and count a dropped write.

**Tree removal under the store lock** (service.py 339-349, `_remove_tree` retry loop on `OSError`): `delete()` runs it inside the store `RLock`.

**Id/path rules (RESEARCH):** `re.fullmatch(r"[0-9a-f]{32}", value)` (not `.match` with `^$`); `is None` for absent (`""` is a 404); `owner_key = hashlib.sha256(owner.encode("utf-8")).hexdigest()[:16]`; ids from `secrets.token_hex(16)`; location by declared scope (1 id -> `<root>/<doc_id>/chat/conversations/<id>.json`, else `<root>/_conversations/<owner_key>/<id>.json`); dedupe declared ids with `list(dict.fromkeys(doc_ids))` as in service.py 375. Lease: `_busy` set of `(owner_key, id)` under one mutex plus an idempotent `Lease.release()` (RESEARCH Pattern 1). `append_turn` re-reads the file under the lock and calls `alive(...)` before writing (RESEARCH Pattern 4). `purge_document` also removes unparseable files and `*.json.tmp`.

---

### `rag/api/service.py` (service, request-response + streaming)

**Analog:** itself. Edit points (today's line numbers):

**Imports to add** (after line 34): `scan_text` from `rag.query.guard`; `from rag.api.conversations import ConversationBusy, ConversationFull, ConversationStore, NoSuchConversation`; `from rag.query.history import HISTORY_WINDOW_TURNS, HistoryTurn, render_block, window` (plus Phase 2 additions `fits_context` etc.); `from rag.query.generate import build_prompts`; add `weakref` to stdlib imports.

**Constructor wiring** (lines 62-94): add keyword param `conversations: Optional[ConversationStore] = None` after `extract_memory_mb`; before `self._recover_interrupted()` (line 94): `self.conversations = conversations or ConversationStore(self.root)`. Keyword-with-default style matches the existing params.

**`_retrieve` today (441-456)** returns `rag, trace, {"names","single","started","query_id","first"}`. New order (RESEARCH diagram): `_ready_documents` -> `conversations.open(owner, declared, conversation_id)` -> `lease` -> `try:` load_turns, `check_room`, `_ensure_loaded`, window/render, `retrieval.run` (raw question), budget check only if block != "" -> `except BaseException: lease.release(); raise`. Extend info with `conversation`, `lease`, `history_block`, `declared`, `turn`. Keep the docstring rationale (errors raise here so streaming still gets a status).

**`_describe` (458-488):** add `"conversation_id"` and `"turn"` to the returned dict; the trace is saved at 461-468 before `_remember`, so set `trace.config["conversation"] = {...}` in `_retrieve`. Keep the swallow-on-delete pattern:
```python
try:
    trace.save(self._dir(info["first"]) / "chat")
except (NotFound, FileNotFoundError):
    pass  # deleted while the model was answering
```

**Ask paths (490-523):** `ask` (437-439) gets trailing `conversation_id: Optional[str] = None`. Pattern for `ask_documents`:
```python
rag, trace, info = self._retrieve(owner, doc_ids, question, config, style, conversation_id)
try:
    rag.answer(trace, history_block=info["history_block"])
    result = self._describe(trace, info)
    self._remember(trace, info, result)   # append turn, then release lease
    return result
finally:
    info["lease"].release()
```
Stream: keep the `events()` generator shape from lines 511-523; call `self._remember` between `_describe` and `yield {"event": "final"...}`; add `info["lease"].release()` in the existing `finally: stream.close()`; register `weakref.finalize(gen, info["lease"].release)` on the returned generator (a never-started generator never runs `finally`).

**`delete` (351-362):** wrap `self._remove_tree(directory)` in `with self.conversations.lock:` and call `self.conversations.purge_document(owner, doc_id)` after it and before the `_deleting.discard` line.

---

### `rag/api/main.py` (route, request-response + SSE)

**Analog:** itself.

**Request field** (`AskRequest`, ~line 123-126): `conversation_id: Optional[str] = Field(None, max_length=64)`; see Open Question 6 in RESEARCH (a 65+ char id yields 422, not the 404 CONV-02 wants; decide in planning). `AskAcrossRequest(AskRequest)` inherits it.

**Exception mapping to copy** (`guarded`, 316-326):
```python
try:
    return call()
except NotFound:
    raise HTTPException(404, "no such document")
except BadUpload as err:
    raise HTTPException(409, str(err))
except Exception as err:
    logger.exception("ask failed for %s", what)
    raise HTTPException(502, public_reason(err))
```
Insert before the generic `except Exception`: `NoSuchConversation` -> `HTTPException(404, "no such conversation")`; `ConversationBusy` -> 409 "conversation is busy, retry when the previous answer is finished"; `ConversationFull` -> 409 "this conversation is full; start a new conversation". One fixed string each, no id echoed. Add the import near line 41.

**Four lambdas** (369, 375, 381, 387): append `conversation_id=request.conversation_id` (keyword) to each `svc().ask(...)`, `ask_documents(...)`, `ask_documents_stream(owner, [doc_id], ...)`, `ask_documents_stream(owner, request.doc_ids, ...)`. `stream_request` (334-365) needs no edit: `guarded(start, what)` at line 339 already runs `_retrieve` before any SSE byte. `ask_about` stays untouched. Owner stays `Depends(current_owner)` only.

---

### `rag/query/history.py` (utility, transform; Phase 1 creates, Phase 2 adds)

**Analog:** `.planning/phases/01-safety-net-and-prompt-seam/01-05-PLAN.md` (spec) and `rag/query/guard.py` style. Phase 1 symbols Phase 2 consumes:
```python
@dataclass(frozen=True)
class HistoryTurn:  # question: str, answer: str, asked_at: str, rewritten: Optional[str] = None
def window(turns: Sequence[HistoryTurn], n: int = HISTORY_WINDOW_TURNS) -> List[HistoryTurn]
def neutralize(text: str, max_words: int) -> str
def render_block(turns: Sequence[HistoryTurn]) -> str   # "" for no turns; exactly 2*turns+2 lines from splitlines()
# constants: HISTORY_WINDOW_TURNS=6, HISTORY_BLOCK_MAX_WORDS=400, HISTORY_ANSWER_MAX_WORDS=40,
# HISTORY_QUESTION_MAX_WORDS=60, CONVERSATION_MAX_TURNS=50, TOKENS_PER_WORD=1.5, MODEL_CONTEXT_TOKENS
```
Phase 2 adds in the same file (constants with trailing unit comments, imports absolute): `CONVERSATION_MAX_STORED_WORDS = 20000`, `THINKING_TOKENS = 3000`, `ANSWER_TOKENS = 600`, `estimate_prompt_tokens(system, user)` = `ceil((len(system.split()) + len(user.split())) * TOKENS_PER_WORD)`, `fits_context(system, user)`. Pitfall: `window`'s default binds at import, so the service passes `HISTORY_WINDOW_TURNS` explicitly. No I/O, no owner, no `rag/common/config.py` constants.

---

### `tests/test_conversations.py` (new; unit + threaded service tests)

**Analog:** `tests/test_api.py` 776-800 (blocking-store race pattern) and 28-37 helpers.

**Helpers/imports** (test_api.py 1-37, 795-800):
```python
from rag.api.service import DocumentService
from rag.common.embed import HashingEmbedder
from rag.common.llm import FakeLLM          # in Python only; never name the module in a shell command
from tests.test_api import REPLICATION, COMPACTION, make_client, make_pdf, upload

class _BlockingStore(MemoryChunkStore):
    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()
    def upsert(self, *args, **kwargs):
        self.entered.set()
        assert self.release.wait(10)
        super().upsert(*args, **kwargs)

def _race_service(tmp_path, store):
    service = DocumentService(root=tmp_path / "uploads", embedder=HashingEmbedder(), embedder_spec="hash",
                              llm=FakeLLM(lambda system, user: "Replication keeps copies [1]."), store=store)
    doc_id = service.create("a.pdf", make_pdf(REPLICATION), "local")["id"]
    service.run_ingestion(doc_id)
    return service, doc_id
```
Parametrize doc scope as test_api.py 803: `@pytest.mark.parametrize("doc_ids_of", [lambda doc_id: [doc_id], lambda doc_id: None], ids=["one document", "all documents"])`. Use `GatedLLM(FakeLLM)` with `threading.Event` (RESEARCH "Code Examples"): wait with a 30 s ceiling, never a fixed sleep; swap with `service.llm = gated`. Include: id malformed (`"\n"` suffix, `""`, 65 chars), four-way 404 byte-equality, lease idempotent, stale-read/lost-update, caps with `max_turns=2` store, purge cascade, late-writer drop (`dropped_writes`), `get_llm` spy (RESEARCH snippet, patch by dotted string), worst-case budget at caps. Prove failure on old code with `git stash push -q -m <unique-tag> -- rag`.

---

### `tests/test_api.py` (mod; route-level)

**Analog:** itself. Two-owner pattern (lines 385-403):
```python
@pytest.fixture(params=["memory", "opensearch"])
def two_users(request, tmp_path):
    ...
    app.dependency_overrides[current_owner] = lambda: who["name"]
    yield TestClient(app), service, who
```
Reuse `two_users` for the foreign-owner 404 (give the foreign caller their own document so the "no such document" 404 does not fire first). Reuse `make_client(tmp_path, llm=...)` and `upload(...)` for cap tests (status 409, `FakeLLM` call counter 0). Existing `chat/*.json` trace-count globs stay valid because conversations are one level down in `chat/conversations/` or outside `chat`.

---

### `tests/test_stream_api.py` (mod; streaming)

**Analog:** itself.
```python
def frames(response): ...                       # lines 11-20: (event, data) pairs
def ask_stream(client, doc_id, question="...", **extra):   # line 23-24; pass conversation_id=... via **extra
    return client.post(f"/v1/documents/{doc_id}/ask/stream", json={"question": question, **extra})
```
Add: `conversation_id` present in the `final` event and the ordinary body; second turn prompt contains the history block; busy and full return a non-`text/event-stream` 409 with no model call (stream route); disconnect releases the lease; delete race on the stream route. `test_the_streamed_response_equals_the_ordinary_one` (line 41-49) compares a fixed key tuple, so it needs no edit (RESEARCH Pitfall 10, corrects CONTEXT D-06); add a new assertion that the two calls return different ids. Several threads can share one `TestClient` (precedent test_api.py ~296).

## Shared Patterns

### Domain exceptions in service, status mapping in route
**Source:** `rag/api/main.py` 316-326 (`guarded`). **Apply to:** every conversation failure. Service/store never raise `HTTPException`.

### Owner only from `current_owner`; store filters inside
**Source:** `rag/api/main.py` `current_owner`; `Scope(owner, tuple(names))` at service.py 449. **Apply to:** `conversations.open`, `purge_document` (owner_key in path, never raw owner).

### Atomic write + Windows retry
**Source:** service.py 106-128. **Apply to:** `conversations.py` writes and reads.

### Delete safety (no resurrection)
**Source:** service.py 98-104, 351-362, 409-411 (`_load_into_store`: "deleted while loading: leave nothing behind"), 466-468 (swallow `NotFound`/`FileNotFoundError`). **Apply to:** `append_turn`, `delete`, `purge_document`.

### Logging
Counts and decisions only, never question/answer text; module logger `logging.getLogger("rag.<area>")`.

### Hook-flagged files
Never name `rag/common/llm.py` or `tests/test_vllm.py` in a shell command; Python imports like `from rag.common.llm import FakeLLM` in test code are fine.

## No Analog Found

| File / piece | Role | Data Flow | Reason |
|------|------|-----------|--------|
| Per-conversation lease (busy set, idempotent release, `weakref.finalize`) | concurrency | event-driven | No lease or per-key lock exists; existing locks are global `threading.Lock`s (service.py 87-90). Use RESEARCH Pattern 1. |
| `GatedLLM` test double | test | event-driven | Nearest is `_BlockingStore` (test_api.py 781-792) and `service.llm = watching` swap (test_stream_api.py ~136); use RESEARCH snippet. |
| `get_llm` spy test | test | n/a | No existing spy; RESEARCH snippet. |

## Metadata

**Analog search scope:** `rag/api/service.py`, `rag/api/main.py`, `tests/test_api.py`, `tests/test_stream_api.py`, Phase 1 `01-05-PLAN.md`, Phase 2 CONTEXT/RESEARCH (lines 1-462 of 637 read).
**Tracked-source gate:** all named analogs are tracked repo files under `rag/` and `tests/`; no capability mirror paths.
**Pattern extraction date:** 2026-10-22
