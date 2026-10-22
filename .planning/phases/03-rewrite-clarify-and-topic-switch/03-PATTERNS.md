# Phase 3: Rewrite, clarify and topic switch - Pattern Map

**Mapped:** 2026-10-22
**Files analyzed:** 8 (4 new, 3 modified, plus `rag/api/conversations.py` which Phase 2 creates and Phase 3 extends)
**Analogs found:** 8 / 8 (two are planned symbols, not yet on disk; shapes come from the Phase 1 and 2 plans)

All analog paths below are git-tracked (`git ls-files` confirmed for `rag/api/service.py`, `rag/api/main.py`, `rag/query/about.py`, `tests/test_ollama.py`, `tests/test_stream_api.py`, `tests/test_api.py`, `.env.example`, `data/golden/*`). Phase 1 and 2 symbols (`rag/query/history.py`, `rag/api/conversations.py`, `tests/test_conversations.py` helpers) do NOT exist yet: re-check against `01-xx-SUMMARY.md` / `02-xx-SUMMARY.md` at plan time (RESEARCH A1).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `rag/query/rewrite.py` (new) | service (pure query step; owns its prompt, parses model output, guards it) | request-response (one LLM call, total function) | `rag/query/about.py` | role-match (same prompt+scan+parse shape) |
| `rag/api/service.py` (modify: ctor, `_retrieve`, `_describe`, `_clarify_response`, `_remember`, `ask_documents*`) | service | request-response + streaming | itself (lines 441-523) + Phase 2 plan 02-04 | exact (in-place edit) |
| `rag/api/main.py` (modify: `build_default_service`) | config / factory | request-response | itself (lines 141-168) | exact |
| `rag/api/conversations.py` (Phase 2 file; extend `new_turn`, add `since_topic_start`) | model / storage helper | CRUD (file) | `02-03-PLAN.md` line 197 `new_turn` | exact (planned) |
| `.env.example` (modify) | config | n/a | itself (lines 1-33) | exact |
| `tests/test_rewrite.py` (new) | test (pure module) | request-response | `tests/test_ollama.py` + `tests/test_stream_api.py` style | role-match |
| `tests/test_rewrite_api.py` (new) | test (service + routes) | request-response + SSE | `tests/test_stream_api.py` + Phase 2 `tests/test_conversations.py` helpers | role-match |
| `data/golden/conversations_draft.jsonl` (new) | data fixture (human-written, not loaded by tests) | batch | `data/golden/about_questions.jsonl` / `ddia_questions.jsonl` | partial (format only) |

## Pattern Assignments

### `rag/query/rewrite.py` (service, request-response, pure)

**Analog:** `rag/query/about.py` (module docstring that says why it is separate; module-owned `*_SYSTEM_PROMPT` constant; `scan_text` on untrusted text; regex parse of model output; `llm.generate(SYSTEM, prompt, max_output_tokens=N)`; result dataclass).

**Imports pattern** (about.py lines 12-17; project style: `typing` generics, fully qualified `rag.` imports, no `from __future__`):
```python
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from rag.common.llm import LLM
from rag.query.guard import scan_text
```
For rewrite.py also import `logging`, `time`, `Optional`, `filter_output` from `rag.query.guard`, `tokenize` from `rag.common.bm25`, and `render_block`/`HistoryTurn` from `rag.query.history` (Phase 1). Logger: `logger = logging.getLogger("rag.query")` (convention `rag.<area>`). Do not import `rag.api`.

**Module-owned system prompt pattern** (about.py lines 19-27): one parenthesised implicit-concatenation string constant. Copy the shape for `REWRITE_SYSTEM_PROMPT` and `REWRITE_SYSTEM_PROMPT_NO_CLARIFY` (draft wording is in RESEARCH Code Examples 7; max 250 words, test-enforced; no example may come from `data/golden`).

**Untrusted-text scan pattern** (about.py lines 40-47):
```python
def _clean(text: str, withheld: List[str], where: str) -> str:
    """Text from a document with anything that looks like an instruction to the model removed."""
    text = _defang(text)
    result = scan_text(text)
    if result.flagged:
        withheld.append(f"{where} ({', '.join(result.rules)})")
        return ""
    return text
```
Reuse for document names in the rewriter prompt: collapse whitespace (`" ".join(name.split())[:60]`), drop when `scan_text(name).flagged`, at most 8 names (about.py `_one_line`, line 88-89, is the same one-liner idea).

**LLM call + regex-parse pattern** (about.py lines 109-119):
```python
result = llm.generate(ABOUT_SYSTEM_PROMPT, prompt, max_output_tokens=600)
cited: List[int] = []
for match in _CITATION.finditer(result.text):
    ...
return AboutAnswer(result.text, cited, result.prompt_tokens, result.output_tokens), prompt, shown
```
Phase 3 differs: `llm.generate(system, user, max_output_tokens=120)` (REWRITE_MAX_OUTPUT_TOKENS, no `json_mode`) is wrapped in `try/except Exception` (the one allowed boundary: a down rewriter must not fail the question), the failure is classified to a closed reason code, and the function is TOTAL (never raises). Result type: `@dataclass(frozen=True) class RewriteResult` with at least `status`, `question`, `reason`, plus `elapsed_ms`, `rewritten_question` (field names beyond `status/question/reason` are discretion).

**Core pattern to copy from RESEARCH (use as starting point, prototype passed 27/27):**
- Gate `needs_rewrite(message, window)` and `anaphora_markers` - Code Example 1.
- Parser `parse_reply` (`_REPLY` regex on first non-empty line) - Code Example 2.
- Guards `check_text`, `_numbers`, `_vocab`, `leaked` - Code Examples 3 and 4.
- `classify_failure`, `rewrite_question(llm, message, window, allow_clarify=True, doc_names=())` - Code Example 5.

**Error handling pattern:** reason strings are codes from a closed set (`unavailable`, `timeout`, `empty`, `unparsed`, `dropped_constraint`, `invented_detail`, `too_long`, `flagged`, `topic_leak`, `input_too_long`); never `str(err)`. Log reason and exception class name only:
```python
logger.warning("rewrite fell back: %s (%s)", classify_failure(err), type(err).__name__)
```
Wrong call-site input raises `ValueError` (convention). Do not log question, answer or history text.

**Reuse, do not hand-roll:** `scan_text(text).flagged`, `filter_output(text, "").blocked` (rag/query/guard.py), `render_block(window)` (Phase 1, already neutralizes), `tokenize(text, drop_stopwords=False)` (rag/common/bm25.py).

---

### `rag/api/service.py` (service, request-response + streaming) - modify

**Analog:** itself. Current code to edit (tracked, lines 441-523).

**`_retrieve` current shape** (lines 441-456) - the edit point. Keep `started = time.perf_counter()` BEFORE the rewrite so `seconds` includes rewrite latency; replace the `retrieval.run(query_id, question, ...)` line with `effective`:
```python
statuses = self._ready_documents(owner, doc_ids)
for status in statuses:
    self._ensure_loaded(status)
names = {status["id"]: status["name"] for status in statuses}
retrieval = RetrievalPipeline(self.store, self.embedder, Scope(owner, tuple(names)), self.reranker)
single = len(statuses) == 1
started = time.perf_counter()
query_id = f"{statuses[0]['id'] if single else 'multi'}-{int(time.time() * 1000)}"
rag = RagPipeline(retrieval, self.llm, style=style, subject="document")
trace = retrieval.run(query_id, question, CONFIGS[config])
return rag, trace, {"names": names, "single": single, "started": started, "query_id": query_id,
                    "first": statuses[0]["id"]}
```
Phase 2 (plan 02-04) wraps this in conversation open + lease + `check_room` and adds `info["lease"]`, `info["history_block"]`, `trace.config["conversation"]`. Phase 3 inserts, after `check_room` and the `_ensure_loaded` loop and before `retrieval.run`:
`switch off -> effective = question, rewrite status "off"`; else `topic_turns = since_topic_start(turns)`; `win = window(to_history_turns(topic_turns), HISTORY_WINDOW_TURNS)`; `needs_rewrite` -> `rewrite_question(self.rewrite_llm, question, win, allow_clarify=<last stored turn not kind "clarify">, doc_names)`; clarify returns `(None, None, info)` with `info["clarify"]`; `NEW_TOPIC` -> block is `render_block([])`; render the history block AFTER the decision. Phase 2's budget check must use `trace.question`, not `question`.

**`__init__` addition:** `rewrite: bool = False, rewrite_llm: Optional[LLM] = None` after `conversations`; `if rewrite and rewrite_llm is None: raise ValueError("rewrite needs a rewrite_llm")`.

**`_describe` current shape** (lines 458-488): reads `trace.stage("context").hits` and `trace.stage("context").meta` (line 470, 484) - must NOT be reached on the clarify path. Add `"kind": "answer"` and `"rewrite": {"status", "reason", "rewritten_question"}` to the dict (always; no existing test compares the full key set). Add a separate `_clarify_response(info)` building the dict from `info` only, with every key the page reads: `answer, blocked: [], citations: [], skipped_by_scanner: [], passages: [], stages: [], abstained: False, documents, query_id (f"clarify-{ms}"), llm (self.rewrite_llm.name), seconds, kind: "clarify", rewrite, conversation_id, turn` (+ `replace: False` on stream).

**Ask routes current shape** (lines 490-523). Ordinary route gets the clarify branch; stream route returns `iter([{"event": "final", "data": result}])` for clarify (zero token events), persisting eagerly before returning:
```python
rag, trace, info = self._retrieve(owner, doc_ids, question, config, style)
...
def events() -> Iterator[Dict[str, Any]]:
    try:
        for kind, value in stream:
            if kind == "token":
                yield {"event": "token", "data": {"text": value}}
            else:
                result = self._describe(trace, info)
                result["replace"] = bool(value)
                yield {"event": "final", "data": result}
    finally:
        stream.close()
```
Sketch for the new branch is RESEARCH Code Example 8. Lease is released in `finally` on every exit (Phase 2 plan 02-04).

**Compatibility rule (critical):** with the switch off, add NO key to `trace.config["conversation"]` (exactly `{"id","turn","history_turns","dropped_turns"}`) and NO key to a stored turn (exactly the seven Phase 2 keys). `kind`, `topic_start` and rewrite fields appear only when the switch is on / value non-default; readers use `turn.get("kind", "answer")`, `turn.get("topic_start", False)`. Do not persist in a `finally`.

**Error handling:** service raises domain exceptions only (`NotFound`, `BadUpload`, `TooLarge` at lines 49-58); never `HTTPException`. Rewrite failure is data (`RewriteResult.status == "fallback"`), so `guarded()` (main.py line 316) stays unchanged; anything raised out of the rewrite step would become a 502 and silently turn D-09 fail-open into fail-closed.

---

### `rag/api/main.py` (config/factory) - modify `build_default_service`

**Analog:** itself, lines 141-168.

**Settings + no-cache pattern** (lines 143-168):
```python
from rag.common.llm import get_llm
from rag.common.secrets import setting
...
return DocumentService(
    root=DATA_DIR / "uploads",
    embedder=embedder,
    store=store,
    embedder_spec=spec,
    # no cache: it would keep every uploaded passage and question on disk after a delete
    llm=get_llm(setting("RAG_LLM", "vllm:/models/gpt-oss-20b"), cache_dir=None),
)
```
Add (RESEARCH Pattern 5), inside the function, before the return:
```python
rewrite = setting("RAG_REWRITE", "") == "1"   # D-01: "1" on, anything else off
rewrite_llm = get_llm(setting("RAG_REWRITER", "ollama:qwen2.5:7b"), cache_dir=None) if rewrite else None
```
and pass `rewrite=rewrite, rewrite_llm=rewrite_llm`. Every `get_llm` call here must keep `cache_dir=None` (Phase 2 AST guard `test_no_get_llm_call_in_rag_api_omits_cache_dir_none` and spy test cover it). No route change.

---

### `rag/api/conversations.py` (Phase 2 file; storage helper) - extend

**Analog:** `02-03-PLAN.md` line 197 (planned, not on disk):
`def new_turn(question, answer, doc_ids, query_id, rewritten=None) -> Dict` returns exactly `question, rewritten, answer, doc_ids, asked_at, query_id, scan` (seven keys).
Phase 3 extension: `new_turn(..., kind="answer", topic_start=False)` adds `"kind"` only when `kind != "answer"` and `"topic_start": True` only when true. Add pure `since_topic_start(turns)` (RESEARCH Pattern 4; scan from the end for `turn.get("topic_start")`, return `list(turns[i:])`, else `list(turns)`). Do not change `HistoryTurn`/`window` (Phase 1 verify calls `window([1, 2, 3], 2)` with ints).

---

### `.env.example` (config) - modify

**Analog:** itself. Commented-name convention (lines 28-33):
```
# Spotlight prompt nonce. Random per process by default. ...
# RAG_NONCE_KEY=

# API request checks (see docs/auth_plan.md): ...
# RAG_ALLOWED_HOSTS=127.0.0.1,localhost
# RAG_ALLOWED_ORIGINS=
```
Add a block in the same style: a one-to-two line comment, then `# RAG_REWRITE=` and `# RAG_REWRITER=` with no values; mention spec-string format (`ollama:<model>`, default `ollama:qwen2.5:7b`) and that `OLLAMA_KEEP_ALIVE` is an Ollama server setting (cold load measured ~30.7 s). The spec-string comment block at lines 3-8 documents `vllm:/ollama:/gemini:`. Never read the real `.env`.

---

### `tests/test_rewrite.py` (test, pure)

**Analog for fake-LLM and monkeypatch style:** `tests/test_ollama.py`.

**Imports pattern** (test_ollama.py lines 1-7):
```python
import io
import json
import urllib.error

import pytest

from rag.common.llm import CachedLLM, FakeLLM, OllamaLLM, get_llm
```
**FakeLLM with call record** (test_ollama.py lines 58-63): `inner = FakeLLM(lambda s, u: "x")` ... `assert len(inner.calls) == 2`. `.calls[0][0]` is the system prompt, `.calls[0][1]` the user prompt (RESEARCH A6: verify; a raising reply function may not record - use a counting subclass for failure paths).

**Table-driven tests:** use a dict of case id -> (message, LINE, expected reason) for BAD_REWRITES (RESEARCH Code Example 6 table, fixture: turn `("How does replication work in the Raft design?", "Raft keeps copies on several nodes and elects a leader.")`, document names `raft.pdf`, `Paxos-notes.pdf`). Name tests for behaviour (e.g. `test_the_gate_decides_without_a_model`, `test_each_bad_rewrite_falls_back_with_its_reason`, `test_a_wrong_pick_between_two_names_in_the_window_is_a_known_limit`, `test_the_guards_never_raise_on_odd_text`, `test_an_oversized_rewriter_prompt_is_a_fallback_without_a_call`). Full list: RESEARCH "Phase Requirements -> Test Map". Tests are pure: no TestClient, no OpenSearch.

---

### `tests/test_rewrite_api.py` (test, service + routes + SSE)

**Analog 1 (SSE parsing and route helpers):** `tests/test_stream_api.py` lines 1-25, 41-49.
```python
from rag.common.llm import FakeLLM, LLMResult, StreamPiece
from tests.test_api import COMPACTION, REPLICATION, make_client, make_pdf, upload

def frames(response):
    """The server-sent events of a response as (event, data) pairs."""
    out = []
    for block in response.text.split("\n\n"):
        if not block.strip():
            continue
        name = next(line[7:] for line in block.splitlines() if line.startswith("event: "))
        data = json.loads(next(line[6:] for line in block.splitlines() if line.startswith("data: ")))
        out.append((name, data))
    return out

def ask_stream(client, doc_id, question="How does replication survive a node failure?", **extra):
    return client.post(f"/v1/documents/{doc_id}/ask/stream", json={"question": question, **extra})
```
Import `frames`/`ask_stream` from `tests.test_stream_api` and `make_pdf`, `REPLICATION`, `COMPACTION`, `upload`, `make_client` from `tests.test_api` (fully qualified, no relative imports). Clarify stream assertion: `[name for name, _ in frames(r)] == ["final"]` and `data["kind"] == "clarify"`.

**Analog 2 (service-level helpers, Phase 2 plan 02-07 lines 136-141, planned):** import from `tests.test_conversations`: `make_service(tmp_path, llm=None, **options)` (passes `rewrite=True, rewrite_llm=FakeLLM(...)` via `**options`), `add_document(service, text, owner="local", name="a.pdf")`, `client_for(service, owner="local")`, `conversation_file(...)`, `stored(path)`, `seed_turns(service, owner, doc_ids, resolved, pairs)`, `GatedLLM`. `seed_turns` writes plain turns only; for stored `kind: "clarify"` / `topic_start` turns call `ConversationStore.append_turn(conversation, new_turn(..., kind="clarify"), alive=lambda ids: True)` directly.

**Analog 3 (rewriter-down test, real client):** `tests/test_ollama.py` lines 41-47:
```python
def test_ollama_unreachable_gives_a_helpful_error(monkeypatch):
    def refuse(request, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", refuse)
    with pytest.raises(RuntimeError, match="ollama serve"):
        OllamaLLM("x").generate("s", "u")
```
Adapt: rewriter = `OllamaLLM("qwen2.5:7b")`, refuse raises `urllib.error.URLError(ConnectionRefusedError())` (project rule: a closed local port times out here; always patch). Assert HTTP 200, answer present, `rewrite == {"status": "fallback", "reason": "unavailable", "rewritten_question": None}`. Payload characterization test copies lines 18-38 (capture `request.data`, check `payload["options"]` keys, `temperature == 0.0`, `num_predict == 120`, record the `timeout` argument). Settings tests monkeypatch `rag.common.secrets.load_env` to a no-op and `monkeypatch.setenv/delenv` `RAG_REWRITE`/`RAG_REWRITER`, with a `get_llm` spy asserting `cache_dir is None`.

**Streaming-order assertion:** for the service-level stream, rewriter `calls` has length 1 right after `ask_documents_stream(...)` returns and before the first `next()` (proves the decision precedes any SSE byte). Timing-sensitive tests wait on an Event/poll, never a fixed sleep.

---

### `data/golden/conversations_draft.jsonl` (data, human-written)

**Analog:** `data/golden/about_questions.jsonl` and `data/golden/ddia_questions.jsonl` (JSON Lines, one object per line; read one row of each at plan time to copy key naming). Schema from RESEARCH Open Question 10: `turns`, `message`, `standalone`, `gold_pages` (PDF pages; DDIA printed + 22), `category`, `expect`, `must_contain`, `must_not_contain`. Plan this as a `checkpoint:human-action` task with 4 stub rows (pronoun follow-up, topic switch, ambiguous follow-up, standalone-inside-conversation). Not loaded by any test; the rewriter prompt must share no example with it. Companion docs in the same folder: `data/golden/question_writer_rules.md`.

---

## Shared Patterns

### Never-raise boundary with a visible reason (D-09)
**Source:** RESEARCH Code Example 5 (`rewrite_question`) and `rag/api/main.py` `guarded()` (line 316, maps every `Exception` to 502).
**Apply to:** `rag/query/rewrite.py`, `_retrieve`. The single allowed `except Exception` sits inside `rewrite_question`, records the reason in the result, trace and response.

### Untrusted-text scanning
**Source:** `rag/query/guard.py` `scan_text(...)` / `filter_output(text, "")`; usage in `rag/query/about.py` lines 40-47.
**Apply to:** rewriter output (`REWRITE:` and `CLARIFY:` payloads), document names in the rewriter prompt, history (via `render_block`).

### No LLM disk cache for service models
**Source:** `rag/api/main.py` line 167 `get_llm(..., cache_dir=None)` with comment "no cache: it would keep every uploaded passage and question on disk after a delete".
**Apply to:** the new `RAG_REWRITER` call in `build_default_service`.

### Settings through `setting(...)` only in `build_default_service`
**Source:** `rag/api/main.py` lines 146-156.
**Apply to:** `RAG_REWRITE`, `RAG_REWRITER`; spec-string convention like `RAG_LLM`.

### Pre-model work in `_retrieve`, domain exceptions from the service, status mapping in the route
**Source:** `rag/api/service.py` lines 441-444 docstring.
**Apply to:** gate, rewrite call, clarify short-circuit, topic window. All happen before any SSE byte.

### Code style
`typing` generics (`Optional[str]`, `List[...]`), no `X | None`, no `from __future__ import annotations`, double quotes, lines <= 120 chars, module logger `logging.getLogger("rag.<area>")`, docstrings explain why, no question/answer/history text in logs.

## No Analog Found

| File / Piece | Role | Data Flow | Reason |
|--------------|------|-----------|--------|
| Skip gate, tagged-line parser, `check_text` guards, `topic_leak` rule inside `rewrite.py` | utility | transform | No existing deterministic input/output guard of this kind; use RESEARCH Code Examples 1-4 (prototype-verified). `rag/query/guard.py` supplies only the scanner and output filter. |
| Clarify short-circuit response (`_clarify_response`) and zero-token SSE `final` | service | request-response | No existing route returns a non-retrieval answer through the normal shape; closest is `ask_about` (`filter_output(answer.text, context)` at service.py ~line 423) for the "text leaves only in `final.answer`" precedent. Use RESEARCH Pattern 3 and Code Example 8. |
| `data/golden/conversations_draft.jsonl` multi-turn schema | data | batch | Existing golden files are single-turn; schema is from RESEARCH Open Question 10 / PITFALLS.md Pitfall 11. |

## Metadata

**Analog search scope:** `rag/query/`, `rag/api/service.py`, `rag/api/main.py`, `.env.example`, `data/golden/`, `tests/test_ollama.py`, `tests/test_stream_api.py` (read by exact path; no glob of `tests/` or `rag/common/`; the provider module and vLLM test file were not named or opened).
**Files scanned:** about 14 (plus Phase 1/2 plan greps).
**Pattern extraction date:** 2026-10-22
