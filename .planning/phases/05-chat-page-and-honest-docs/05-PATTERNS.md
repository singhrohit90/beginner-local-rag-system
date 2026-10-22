# Phase 5: Chat page and honest docs - Pattern Map

**Mapped:** 2026-10-22
**Files analyzed:** 7 (6 modified, 1 new; plus optional `tests/page_harness.js`)
**Analogs found:** 7 / 7 (all tracked source; edit-point detail E1-E14 is in 05-RESEARCH.md and is not repeated here)

## File Classification

| File | Role | Data Flow | Closest Analog | Match |
|------|------|-----------|----------------|-------|
| `rag/api/static/index.html` | component (vanilla page) | request-response + SSE | itself (`streamAsk`, ask handler, `select`) | exact |
| `tests/test_api.py` (rewrite lines 648-653) | test | static page text check | `test_the_page_has_a_light_that_shows_the_details_on_hover` (751-755) | exact |
| `tests/test_page_conversation.py` (new) | test | static text + node subprocess | `test_the_page_script_has_valid_syntax` (758-771) and 751-755 | exact |
| `tests/page_harness.js` (new, optional) | test helper | child process | `tests/sandbox_targets.py` (plain helper module convention) | role-match |
| `rag/README.md` (+ Step 11) | doc | prose | `## Step 10` (lines 314-322), Step 8 | exact |
| `docs/backlog.md` | doc | list | line 10 `**Streaming answers: done** (2026-10-10)` | exact |
| `interview/05_conversation_memory_and_cost.md`, `interview/README.md` | doc | prose | the file's own labels (line 7: Built / Not built / General) | exact |

## Pattern Assignments

### `tests/test_api.py` rewrite of `test_choosing_another_document_keeps_the_conversation_on_the_page` (lines 648-653)

**Current (to be replaced; asserts the opposite of D-02 for scope "one"):**
```python
def test_choosing_another_document_keeps_the_conversation_on_the_page(tmp_path):
    client, _ = make_client(tmp_path)
    page = client.get("/").text
    select_function = page[page.index("function select("):page.index("function scopeLabel")]
    assert "replaceChildren" not in select_function  # the log is not cleared when the selection changes
    assert "asked of:" in page and "no answer" in page
```
Keep the slice, the `"replaceChildren" not in select_function` line (the log clearing lives in `resetConversation`, defined above the comment before `function select(`), and the `"asked of:"`/`"no answer"` line. Add `assert "resetConversation(" in select_function and '$("scope").value === "one"' in select_function`. Rename it to state the new contract (for example `..._resets_the_conversation_only_under_scope_one`).

### `tests/test_page_conversation.py` (new)

**Static test pattern** (tests/test_api.py 751-755):
```python
def test_the_page_has_a_light_that_shows_the_details_on_hover(tmp_path):
    client, _ = make_client(tmp_path)
    page = client.get("/").text
    assert 'id="light"' in page and "function checkStatus" in page and "/v1/status" in page
```
**Setup:** file header and `make_client` come from tests/test_api.py lines 1-30 (`from fastapi.testclient import TestClient`, `create_app`, `DocumentService`, `HashingEmbedder`, `FakeLLM`; `make_client(tmp_path, llm=None)` returns `(client, service)`). Import `make_client` with `from tests.test_api import make_client` only if other test files already do that (check with the Grep tool on `import make_client`); otherwise copy the 8-line helper. No relative imports.

**Node subprocess pattern, skip when node is missing** (tests/test_api.py 758-771):
```python
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    client, _ = make_client(tmp_path)
    script = re.search(r"<script>(.*)</script>", client.get("/").text, re.S).group(1)
    path = tmp_path / "page.js"
    path.write_text(script, encoding="utf-8")
    check = subprocess.run([node, "--check", str(path)], capture_output=True, text=True)
    assert check.returncode == 0, check.stderr
```
Static cases to assert: `"conversationId = null"` present, `conversation_id` present, `resetConversation(` appears at the scope onchange, the checkbox handler, delete handler, `select`, upload handler, and the New conversation button; `type="button"` on `id="newconv"`; `page.count("innerHTML") == 1`; no `outerHTML|insertAdjacentHTML|document.write`; `"AbortController"` present. Each must fail on the old page. For the harness (optional, scenarios a-h in RESEARCH Code Example 5), run `[node, str(harness), ...]` with `subprocess.run(..., input=script, capture_output=True, text=True)`, keep the JS in `tests/page_harness.js` (a plain module, as `tests/sandbox_targets.py` is for child processes). Do not name or glob `tests/` in shell commands; use Read/Grep by exact path.

### `rag/api/static/index.html` (component, request-response + SSE)

**Analog: the file itself.** Pinned strings that must survive (copied from tests, see RESEARCH table): `RAG document chat`; `async function streamAsk`; `/v1/ask/stream`; `shown.data += text`; `replaced after the final check`; `'msg.append(el("br"), longText(err.message))'`; `"const failed"` must be absent; `function select(` before `function scopeLabel`; `'$("status").title'`; `h.error` and `Could not start`; `.innerHTML` absent, and the only `innerHTML` text is the comment on line 117 ("never innerHTML"). New comments must not say `innerHTML`.
Untrusted text rule: build nodes with `el(...)`, `replaceChildren`, `textContent`; follow the existing `el()` string-as-text-node behaviour. See RESEARCH Code Examples 1-4 for the proposed bodies.

### `rag/README.md` Step 11 (doc)

**Analog: Step 10 (lines 314-322)**, heading style `## Step N: lowercase description`, optional 4-space-indented request line, then plain prose with backticked paths:
```
## Step 10: questions about the documents themselves

    POST /v1/ask-about     {"question": "...", "doc_ids": [...] | null}

"When should I use this book and when that one?" is about the documents, so no passage answers it. ...
```
Write `## Step 11: chat memory` after line 322, with an indented `{"question": "...", "conversation_id": "..."}` request line, about 25-40 lines. Add one sentence at the end of Step 8 pointing to Step 11. Every value is read from real code/`docs/chat_memory_eval.md` at execution (table in RESEARCH "Docs Targets").

### `docs/backlog.md` (doc)

**Analog: line 10** (the "UI and API" done convention):
```
- **Streaming answers: done** (2026-10-10). `POST /v1/ask/stream` and ... Still open: a Stop button, streaming for the "about the documents" path ...
```
Replace line 7 (`- **Chat has no memory.** ...`) with `- **Chat memory: done** (<date from date +%F>). ... Step 11 ... Still open: ...`; add new bullets in the same section for compaction (about 70% of history budget), reload-resume GET, rewritten question in the pipeline panel; add the conversation-retention bullet next to the Security bullet at line 20; split line 27 (query rewriting) per RESEARCH.

### `interview/05_conversation_memory_and_cost.md`, `interview/README.md` (doc)

**Analog:** the file's own labelling (line 7 defines `Built`, `Not built`, `General`; section "In this repo" bullets start with `**Not built.**`). Flip to `**Built.**` only where a test or a number in committed `docs/chat_memory_eval.md` exists; delete the "Because the app is stateless" sentence (line 57); update line 5 and `interview/README.md` line 20. Cite only real, existing paths; do not name the provider module path in any command (use a `l[l]m` character class if grepping).

## Shared Patterns

### Untrusted text in the DOM
**Source:** `rag/api/static/index.html` header comment line 117 and `el()` helper. **Apply to:** every new string (notice, label, clarify answer): `textContent`, `replaceChildren`, text nodes only.

### Page-test style
**Source:** tests/test_api.py 751-771. **Apply to:** both test files: `make_client(tmp_path)`, `client.get("/").text`, substring asserts, `shutil.which("node")` skip.

### Docs numbers
**Source:** `docs/chat_memory_eval.md` (Phase 4). **Apply to:** README Step 11, backlog, interview note: copy, never retype; follow its `Decision:` line and provisional wording (D-11); never cite gitignored `runs/`.

## No Analog Found

| File | Role | Reason |
|------|------|--------|
| `tests/page_harness.js` | test helper | No JS test helper exists; use RESEARCH Code Example 5 (recording fake DOM, native `fetch`/`Response`) |
| AbortController/epoch logic in `index.html` | component | Page has no abort path today (grep count 0); use RESEARCH Pattern 1 |

## Metadata

**Analog search scope:** `tests/test_api.py` (lines 1-30, 640-771), `rag/README.md` 308-322, `docs/backlog.md` 1-14, 05-RESEARCH.md (first 513 of 662 lines; the remainder is validation and docs-check detail not needed for analogs)
**Pattern extraction date:** 2026-10-22
