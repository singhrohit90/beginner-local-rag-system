# Phase 5: Chat page and honest docs - Research

**Researched:** 2026-10-22
**Domain:** vanilla-JS chat page state (conversation id lifecycle, SSE, abort) plus documentation honesty (README step, backlog, interview note)
**Confidence:** HIGH for the page (the whole file was read this session); MEDIUM for the docs (Phases 2-4 are planned, not executed, so the code and the results file they produce do not exist yet; every value taken from a PLAN is tagged CITED and must be re-read from the real file at execution time)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Carried forward (locked earlier)
- Every ask route accepts `conversation_id` and returns it in the body and the `final` SSE event; foreign/unknown/malformed/wrong-scope ids are one 404 body "no such conversation"; full is 409 "this conversation is full; start a new conversation"; busy is 409 (Phase 2 D-04..D-08, D-16).
- A clarification returns `kind: "clarify"` with `passages: []`, `citations: []`, and on the stream one `final` with no `token` events; responses carry `kind` and `rewrite` (Phase 3 D-10, D-12).
- Untrusted text goes into the DOM with `textContent` only; answers stream only through `StreamGuard` (CLAUDE.md).

#### Conversation id on the page (PAGE-01)
- **D-01:** One module-level `let conversationId = null;` in the page script. After a successful ask (ordinary or stream), set it from `r.conversation_id`. Send it as `conversation_id` in the request body only when non-null (no key when null). [auto: recommended]
- **D-02:** Reset `conversationId = null` on: the new "New conversation" button next to Ask; any change to `$("scope")`; `select(id)` choosing a different document; checking or unchecking a document while scope is "checked"; deleting a document that is in the current target set. A reset also clears the visible chat log so the screen matches the server's notion of the conversation. [auto: recommended — ARCHITECTURE.md: scope binding means the page must reset on a target change]
- **D-03:** Stale id: when an ask with a non-null id returns HTTP 404 with body detail "no such conversation", the page clears `conversationId`, shows a one-line notice "Started a new conversation (the previous one is no longer available).", and resends the same question once with no id. A 404 for any other reason (e.g. "no such document") is shown as today's error. Never more than one automatic retry. [auto: recommended]
- **D-04:** 409 "full" shows its message and a "New conversation" hint in the error area and leaves the id as is (the user chooses); 409 "busy" shows its message and re-enables Ask. A stream that is superseded by "New conversation" while running is aborted with the existing abort path, and its late `final` does not set `conversationId`. [auto: recommended — SUMMARY.md superseded-stream trap]

#### Clarifying question (PAGE-02)
- **D-05:** When `r.kind === "clarify"`, the answer bubble shows `r.answer` with `textContent` (via the existing `msg.replaceChildren(text)` path), with no passages panel and a small "clarifying question" meta label; the next question is sent with the same `conversationId` so the server can resolve it. [auto: recommended]
- **D-06:** Every new string the page shows (notices, labels, clarify text) is inserted with `textContent` / `replaceChildren` of text nodes; no `innerHTML` is introduced. A static check in the plan greps the page for `innerHTML` (count must stay 0 outside the existing comment). [locked by CLAUDE.md]

#### Verification of the page
- **D-07:** The page has no automated test today. Verification is (a) static checks (grep for `conversation_id`, `conversationId = null` at each reset site, no `innerHTML`), (b) API-level tests already in Phases 2-3 for the contract the page relies on, and (c) a manual browser pass covering ROADMAP success criteria 1-3, written as a checklist in the phase VERIFICATION and marked `human_needed` (the run is unattended, so it does not block planning or execution of the docs plans). [auto: recommended — ROADMAP scope note]

#### Docs (DOCS-01)
- **D-08:** `rag/README.md` gains "## Step 11: chat memory" after Step 10: what a conversation is, where it is stored and deleted, the history block, the hard cap, the rewrite switch `RAG_REWRITE` and `RAG_REWRITER` with their shipped defaults, and the Phase 4 numbers copied from `docs/chat_memory_eval.md` (with a link). [auto: recommended]
- **D-09:** `docs/backlog.md`: the "Chat has no memory" item is marked done with a pointer to Step 11; new items added: compaction of long histories (rolling summary at about 70% of the history budget), conversation retention (TTL for conversations of documents never deleted; orphan one-turn files from page questions before this phase), a reload-resume GET, and showing the rewritten question in the pipeline panel. [auto: recommended]
- **D-10:** `interview/05_conversation_memory_and_cost.md`: each point is relabelled only if it is built and has a test or a recorded number: section 1 (follow-up) becomes **Built** for server-side history, the history block and the rewrite step, citing the files and `docs/chat_memory_eval.md` numbers, and states plainly whether rewriting ships on or off and why; section 2 (compaction) stays **Not built** (hard cap built instead, labelled Built); section 3 (cost tracking) stays **Not built**. The opening status paragraph is updated to match. Numbers are copied from committed files only, never from gitignored `runs/`. [locked by DOCS-01 and CLAUDE.md "keep interview/ notes honest"]
- **D-11:** If Phase 4 left the results provisional (golden rows `pending-human`), the docs say so in the same words as `docs/chat_memory_eval.md` and do not present the numbers as final. [auto: recommended]

#### UI design contract
- **D-12:** No new visual design: reuse the page's existing button, notice and meta styles (`button`, `.msg`, `small.meta`, the error area). A UI-SPEC is not needed for one button, one label and two notices; if the plan-phase UI gate requires one, it is generated in auto mode from these decisions. [auto: recommended]

### Claude's Discretion
- Exact notice wording beyond D-03; button placement detail; Step 11 section order.

### Deferred Ideas (OUT OF SCOPE)
- Reload-resume GET and a conversation list (v2)
- Rewritten question in the pipeline panel (v2 CONV-08)
- Turn counter and cap warning before the cap is hit
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PAGE-01 | `rag/api/static/index.html` keeps the conversation id across questions, resets it on "new conversation" or a change of selected documents, and handles a stale id (404) by starting a new conversation | Edit-point table (state, body build, six reset sites, stale retry, superseded stream); Code Examples 1-4; pinned page tests that must keep passing |
| PAGE-02 | The clarifying question (RWR-03) is shown as an ordinary assistant turn, rendered with `textContent` | The existing `msg.replaceChildren(r.answer || "")` already renders text; only the label and the click panel need a `clarify` branch (Code Example 5); devtools fetch override gives a manual check without a real ambiguous question |
| DOCS-01 | `rag/README.md` Step 11; `docs/backlog.md` marks the item done and adds compaction and retention; `interview/05_...` relabelled only for what is built and measured, with recorded numbers | Docs targets with exact headings and line numbers; stale statements outside the three named files; claim-to-source table; number-provenance and path-existence checks |
</phase_requirements>

## Summary

The page change is small in lines but has four traps the CONTEXT does not mention. (1) **The page already has nine tests that read its text**, so "no automated test today" (D-07) is wrong: one of them, `test_choosing_another_document_keeps_the_conversation_on_the_page`, asserts the opposite of D-02 for `select()` and has to be rewritten in the same commit; three others pin exact substrings in `streamAsk` and the error bubble that an edit must keep verbatim; one runs `node --check` on the script (node 24.20.0 is installed here, so it really runs). (2) **There is no "existing abort path"** (D-04): the page has no `AbortController`, no `signal`, nothing; superseding a running stream needs a new abort plus an epoch counter, or a late `final` resurrects the old id. (3) The page's only content route is `POST /v1/ask/stream`; the ordinary `api()` path is used only for `/v1/ask-about`, which stays stateless, so the id applies to one call site. (4) The error object thrown by `streamAsk` carries only a message string (`"404: no such conversation"`), so D-03 and D-04 need `err.status` and `err.detail` added at the one place the error is built.

The docs part is mostly rewriting known targets, but three statements outside the three named files become false and must change too: `interview/05...md` line 57 ("Because the app is stateless..."), `interview/README.md` line 20 ("all three are not built here") and `docs/backlog.md` line 27 (query rewriting "only add them if the golden set shows a gain"). The numbers for Step 11 and the interview note come from `docs/chat_memory_eval.md`, which Phase 4 creates; the docs plans must read it at execution time, branch on its `Decision:` line, and check every copied number mechanically against it.

**Primary recommendation:** Do the page as one tracer plan (state, button, six reset sites, id in the stream body, retry-once, abort-and-epoch, clarify branch) followed by a test plan that rewrites the one contradicted test, adds a static contract test, and adds an optional `node` behaviour harness that drives the real script against a stub `fetch`; do the docs in two plans after the page plan (README plus backlog; interview note plus interview README), each opening with a precondition that `docs/chat_memory_eval.md` has exactly one `Decision: ships` line.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Which conversation a question belongs to (id lifecycle) | Browser / Client (holds the opaque id in memory) | API / Backend (issues, validates, scopes it) | The server owns truth (owner, scope, delete cascade); the page only echoes the id it was given and drops it when the target set changes or the server says 404 |
| Detecting a stale or foreign id | API / Backend | Browser / Client | One 404 body for every miss is decided in the store; the page reacts to the status and detail, never decides ownership |
| History, window, caps, rewrite, clarify decision | API / Backend | — | Already built in Phases 2-3; the page sends only the new message and the id (client-supplied history is out of scope) |
| Rendering answers, clarifications, notices | Browser / Client | — | Untrusted text goes in through `textContent` only |
| Aborting a superseded stream | Browser / Client (fetch signal) | API / Backend (closes generator on disconnect, releases the lease) | The client cancels; the server's `frames()` finally already closes the model stream |
| Docs describing what is built and measured | Repository docs | — | `docs/chat_memory_eval.md` is the only source of measured numbers |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| (none) | — | No package is added; the page is one vanilla HTML file with no build step | Project convention: "No build step", FastAPI plus vanilla HTML page [CITED: .claude/CLAUDE.md "Constraints: Tech stack"] |

### Supporting
| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| node | v24.20.0 | `node --check` syntax test already in `tests/test_api.py`; optional behaviour harness (native `fetch`, `Response`, `TextDecoder`, `vm`) | Static syntax proof and the optional harness; both skip when node is missing [VERIFIED: `node --version` printed v24.20.0 this session] |
| pytest | >=8 | Static contract test over the served page text | Same pattern as the existing page tests [CITED: .claude/CLAUDE.md Technology Stack] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Explicit reset call at each target-changing site (D-02) | A signature of `targets()` compared inside `updateChat()` | `updateChat()` also runs on every 2 s poll and after upload; a side effect that clears the log there is risky. Rejected; explicit sites plus the server 404 safety net |
| jsdom or Playwright for page tests | Plain `node` with a recording fake DOM | No new dependency allowed; the harness below needs about 100 lines and skips without node |

**Installation:** none. **Version verification:** not applicable (no packages).

## Package Legitimacy Audit

No external package is installed by this phase, so the gate has nothing to check.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none) | — | — | — | — | — | — |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
user types question
      |
      v
 ask form submit ---> targets() null|[ids]|[]  ([] = nothing to ask, return)
      |
      |  mine = epoch ; ctl = new AbortController ; inflight = ctl
      v
 mode == "about" ? ---yes---> POST /v1/ask-about {question, doc_ids}   (no id, stateless, signal only)
      | no
      v
 body = {question, doc_ids, config} (+ conversation_id only if conversationId)
      |
      v
 POST /v1/ask/stream --- HTTP error before any byte ---> err.status / err.detail
      |                        404 "no such conversation" and an id was sent
      |                           --> conversationId = null, note in log, resend ONCE without id
      |                        409 full / busy --> readable message in the same failure bubble, id unchanged
      |                        other --> today's failure bubble
      v
 SSE: token* then one final   (clarify: no token, one final, kind "clarify")
      |
      v
 mine !== epoch ? --yes--> drop everything (log was cleared, stream aborted), no id set
      | no
      v
 conversationId = final.conversation_id ; msg.replaceChildren(final.answer) ; tags ; click -> detail panel
```

Reset path (any of six sites): `epoch++`, `conversationId = null`, abort the running ask, clear log and detail panel, clear error, `updateChat()`.

### Edit points in `rag/api/static/index.html` (line numbers are the file as read this session, 380 lines; no Phase 2-4 plan edits this file [VERIFIED: the "MUST NOT edit ... rag/api/static/index.html" prohibition in 02-04-PLAN.md line 61 and 03-04-PLAN.md line 61, and `files_modified` lists in 02-04 and 03-04])

| # | Line(s) now | What is there | Change |
|---|-------------|---------------|--------|
| E1 | 105 | `<button class="primary" type="submit" id="send" disabled>Ask</button>` inside `div.controls` | Insert before it `<button type="button" id="newconv" title="Start a new conversation">New conversation</button>`. `type="button"` is mandatory: inside the `form` a default button submits the ask form. CSS already puts `margin-left:auto` on `button.primary` (line 36), so the new button sits after the selects. Existing order test needs `question < scope < config < send`; placing it between `config` and `send` keeps it |
| E2 | 117 | comment `// Everything shown comes from documents or a model, so it is untrusted: only textContent is used, never innerHTML.` | Keep untouched. Any new comment must not contain the word `innerHTML` (see Pitfall 1) |
| E3 | 119-120 | `let docs = [], selected = null, answers = {}, poll = null, ready = false;` and `const checked = new Set();` | Add after line 120: `let conversationId = null, epoch = 0, inflight = null;` and `const DETAIL_HINT = ...` (read the panel's initial text once, same pattern as `LOADING_TEXT` at line 340). Top-level `let` in a classic script is reachable from the devtools console, which the manual check uses |
| E4 | 129-137 | `api(path, options)` throws `new Error(\`${res.status}: ...\`)` | Optional: build the error through the shared helper (Code Example 2). `api()` needs no signal change: it already forwards `options` to `fetch` |
| E5 | after 152 (`showError`) | — | Add `resetConversation()`, `httpError()`, `askContent()`, `detailClarify()` here, above line 183, so none of them lands inside the slice the old `select` test cuts |
| E6 | 166 | checkbox `pick.onclick = (e) => { e.stopPropagation(); ...; updateChat(); }` | Add `if ($("scope").value === "checked") resetConversation();` before `updateChat()` |
| E7 | 170 | delete `del.onclick = async (e) => {... await api(DELETE); if (selected === d.id) selected = null; checked.delete(d.id); refresh().then(updateChat); }` | Compute membership before the await (`const ids = targets(); const touches = ids === null ? d.state === "ready" : ids.includes(d.id);`), then `if (touches) resetConversation();` after the DELETE succeeds (a failed delete must not clear the log). Note the existing handler has no error handling: a failed DELETE is an unhandled rejection today; not this phase's job |
| E8 | 183-184 | comment `// Choosing another document keeps the conversation: ...` and `function select(id) { selected = id; refresh().then(updateChat); }` | New body: `if ($("scope").value === "one" && id !== selected) resetConversation(); selected = id; refresh()...`. Rewrite the comment (it is now only true for the scopes where the target set does not change) |
| E9 | 209 | `$("scope").onchange = updateChat;` | `$("scope").onchange = () => resetConversation();` (reset ends with `updateChat()`) |
| E10 | 220 | upload handler: `selected = d.id;` | Gap not in D-02: under scope "one" an upload (and a duplicate upload that selects the existing document) changes the target set without going through `select()`. Add `if ($("scope").value === "one" && selected !== d.id) resetConversation();` before the assignment |
| E11 | 229-254 | `async function streamAsk(path, body, onText)`; HTTP-error branch lines 231-235; `fetch(path, {method, headers, body})` at 230 | Add a 4th parameter `signal`, pass it to `fetch`; build the HTTP error with `httpError(res.status, detail)` so it carries `status` and `detail`; keep the message text `"${status}: ${detail}"` for unknown cases. Keep `async function streamAsk` and the literal `/v1/ask/stream` somewhere in the page (pinned) |
| E12 | 256-298 | the ask handler | See Code Example 3: `mine`/`ctl`/`inflight`, `askContent(...)` for the content route, `signal` on the about call, superseded checks after the await and in the catch, set `conversationId` only for non-about, `kind === "clarify"` branch, tail in a `finally` guarded by `mine === epoch`. Keep the three pinned strings (below) |
| E13 | 273 | `r = await streamAsk("/v1/ask/stream", { question, doc_ids: ids, config: $("config").value }, (text) => { shown.data += text; ... })` | Moves into `askContent`; the callback with `shown.data += text` stays at the call site (pinned) |
| E14 | 291 | `msg.onclick = () => {...; r.profiles ? detailAbout(r) : detail(r); };` | Add a clarify branch first (`detailClarify()`), so no empty stages table or empty passages heading appears (D-05 "no passages panel") |

### Pinned page text that an edit must keep (these tests already exist)

| Test (file::name) | Pins (verbatim quote) |
|---|---|
| `tests/test_api.py::test_the_page_is_served` (lines 134-138) | `"RAG document chat" in response.text`; `"innerHTML" not in response.text.replace("never innerHTML", "")` |
| `tests/test_api.py::test_choosing_another_document_keeps_the_conversation_on_the_page` (648-653) | `select_function = page[page.index("function select("):page.index("function scopeLabel")]`; `assert "replaceChildren" not in select_function  # the log is not cleared when the selection changes`; `assert "asked of:" in page and "no answer" in page` |
| `tests/test_api.py::test_the_ask_box_is_multi_line_with_scope_and_mode_below_it_and_errors_fold` (656-662) | `'<textarea id="question"'`; `page.index('id="question"') < page.index('id="scope"') < page.index('id="config"') < page.index('id="send"')`; `page.index('<option value="all">') < page.index('<option value="one">')`; `"function longText" in page and '"more"' in page` |
| `tests/test_api.py::test_the_page_shows_skeleton_rows_and_waits_for_the_models` (689-693) | `"function skeletonRows"`, `"skeleton"`, `"checkReady"`, `'id="starting"'`, `"const can = ready &&"` |
| `tests/test_api.py::test_the_page_has_a_light_that_shows_the_details_on_hover` (751-755) | `'id="light"'`, `"function checkStatus"`, `"/v1/status"`, `'$("status").title'`, `"click to check again"` |
| `tests/test_api.py::test_the_page_script_has_valid_syntax` (758-771) | `re.search(r"<script>(.*)</script>", client.get("/").text, re.S)` then `node --check` (skipped when node is missing). The greedy regex means a new string must never contain the characters `</script>` |
| `tests/test_stream_api.py::test_the_page_reads_the_stream_and_shows_text_only` (146-151) | `"async function streamAsk" in page and "/v1/ask/stream" in page`; `"shown.data += text" in page and "replaced after the final check" in page`; `".innerHTML" not in page` |
| `tests/test_stream_api.py::test_a_failed_ask_leaves_one_bubble_and_the_page_has_no_second_one` (201-205) | `"const failed" not in page`; `'msg.append(el("br"), longText(err.message))' in page` (so the 409 text must be made readable in `err.message` itself, not by changing this line) |
| `tests/test_stream_api.py::test_the_page_shows_why_the_models_did_not_load` (400-403) | `"h.error" in page and "Could not start" in page` |

[VERIFIED: tests/test_api.py:134-138, 648-662, 689-693, 751-771; tests/test_stream_api.py:146-151, 201-205, 400-403, all opened with Read this session]

### Recommended Project Structure (files this phase touches)

```
rag/api/static/index.html          # page edits E1-E14
tests/test_api.py                  # rewrite test at lines 648-653 only
tests/test_page_conversation.py    # new: static contract tests (+ optional node harness test)
tests/page_harness.js              # new, optional: plain JS child-process helper (project rule: helpers for child processes live in a plain module)
rag/README.md                      # + "## Step 11: chat memory" after line 322
docs/backlog.md                    # item at line 7 and neighbours
interview/05_conversation_memory_and_cost.md
interview/README.md                # line 20
```

### Pattern 1: Epoch plus AbortController for a superseded ask
**What:** every ask captures `mine = epoch`; `resetConversation()` does `epoch++` and aborts `inflight`. After each `await`, `if (mine !== epoch) return`. The tail (`send` re-enable, focus) runs in `finally` only when `mine === epoch`; the reset itself re-enables Ask through `updateChat()`.
**When to use:** any state that a long-running request would write back after the user has moved on (here the conversation id).
**Why:** without it, "New conversation" during a stream clears the log, then the old handler's `final` sets `conversationId` to the discarded conversation and the next question continues it (the superseded-stream trap).

### Pattern 2: Retry exactly once on a stale id
**What:** `askContent` remembers the id it sent, and only when that id was non-null and the error is `status 404` with `detail === "no such conversation"` does it clear the id, add the log note and resend once without it. A 404 before any SSE byte means no turn was stored and no model call was made, so the resend cannot duplicate anything. A 409 is never retried.

### Anti-Patterns to Avoid
- **Putting the id in the DOM or in `localStorage`:** the id stays in a JS variable. Reload-resume is deferred (v2 CONV-05); persisting it would also outlive a server-side delete.
- **Sending `conversation_id` to `/v1/ask-about`:** that route is stateless by decision (Phase 2 04-04 prohibition "MUST NOT change /v1/ask-about"). `AboutRequest` has only `question` and `doc_ids` [VERIFIED: rag/api/main.py:129-131].
- **A catch-all `err.message.includes("404")`:** match `err.status === 404 && err.detail === CONV_GONE`; a "404: no such document" must stay a plain error (D-03).
- **Writing a comment or string containing `innerHTML`:** the existing test only forgives the exact phrase `never innerHTML`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cancelling a running fetch/stream | A flag the read loop polls | `AbortController` and `fetch(..., { signal })` | The abort closes the connection, which makes the server's `frames()` finally close the generator and release the conversation lease [CITED: rag/api/main.py:341-349 and 02-04-PLAN.md truth 5] |
| Escaping model/notice text | A sanitizer | `textContent`, text nodes, `replaceChildren` (existing `el()` appends strings as text nodes) | The project rule; `node.append(string)` creates a text node, never markup |
| Parsing the error body twice | A second parser for 404/409 | One `httpError(status, detail)` helper used by `streamAsk` (and optionally `api`) | The same two lines are duplicated at 131-134 and 231-234 today |
| Page behaviour tests | jsdom/Playwright | A recording fake DOM in plain node (below) | No new dependency |

**Key insight:** the server already decides everything about conversations (owner, scope, cap, busy); the page's whole job is to hold one opaque string and drop it at the right moments. Every extra rule in the page is a chance to disagree with the server, so lean on the 404 safety net rather than predicting server state.

## Runtime State Inventory

Not a rename/refactor/migration phase. Omitted per the template. (One related note: conversation files that Phases 2-3 write to disk are not touched by this phase; the retention backlog item below is about them.)

## Common Pitfalls

### Pitfall 1: A new comment or string contains `innerHTML`
**What goes wrong:** `test_the_page_is_served` and `test_the_page_reads_the_stream_and_shows_text_only` fail. The first strips only the exact phrase `never innerHTML`; the second fails on `.innerHTML` anywhere.
**How to avoid:** write "no markup is built from text" instead. Baseline: `grep -c innerHTML rag/api/static/index.html` prints 1 (line 117) [VERIFIED: Bash this session]. After the phase it must still print 1.

### Pitfall 2: The old `select` test goes green for the wrong reason, or red
**What goes wrong:** the test cuts the page between `function select(` and `function scopeLabel` and asserts `"replaceChildren" not in` it. If `resetConversation` is defined between those markers the test fails; if it is defined above, the test passes while its stated intent ("the log is not cleared when the selection changes") is now false for scope "one". Either way the test no longer describes the page.
**How to avoid:** rewrite it in the same commit (see Validation, V-3). Define the new helpers above the comment at line 183.

### Pitfall 3: "Existing abort path" does not exist
**What goes wrong:** the plan says "abort with the existing abort path" and the executor finds nothing. `grep -c -E 'abort|AbortController|signal' rag/api/static/index.html` prints 0 [VERIFIED: Grep this session, no matches].
**How to avoid:** the plan creates it (Pattern 1). Only `streamAsk` and the about `api()` call take the signal.

### Pitfall 4: Error identity lives only in a message string
**What goes wrong:** `streamAsk` throws `new Error("404: no such conversation")`; matching on text works but also matches "404: no such document"-like future strings and breaks if the format changes.
**How to avoid:** attach `status` and `detail` where the error is built (E11), keep the message format.

### Pitfall 5: `final` for the about path has no `conversation_id`
**What goes wrong:** `conversationId = r.conversation_id` after an about answer sets it to `undefined`; the next content ask then omits it (`if (conversationId)` is false) and silently starts a new conversation.
**How to avoid:** set the id only for the content route and only when the value is truthy.

### Pitfall 6: The 409 text is unreadable or the pinned bubble line is changed
**What goes wrong:** the failure bubble shows `409: this conversation is full; start a new conversation`, which is understandable, but D-04 wants a New-conversation hint, and the bubble code line is pinned by a test.
**How to avoid:** make `err.message` itself readable when `httpError` sees a conversation 409 (for "full": the server detail plus `" Use the New conversation button."`; for "busy": the detail alone). The bubble and `showError(err.message)` stay verbatim.

### Pitfall 7: `New conversation` submits the ask form
**What goes wrong:** a `<button>` without `type="button"` inside `form#ask` is a submit button; clicking it sends the question box content.
**How to avoid:** `type="button"` (E1) and a grep check for it.

### Pitfall 8: Chrome/Edge keep serving the old page during the manual pass
**What goes wrong:** `FileResponse` gives ETag/Last-Modified, but a soft reload may still show the previous script.
**How to avoid:** the manual checklist starts with a hard reload and the devtools "Disable cache" box.

### Pitfall 9 (docs): a README or interview number that is not in `docs/chat_memory_eval.md`
**What goes wrong:** a rounded or remembered figure drifts from the committed one.
**How to avoid:** the number-provenance check in Validation V-9; copy, never retype.

### Pitfall 10 (docs): the path check trips the secrets hook
**What goes wrong:** `interview/05...md` line 79 cites the provider module by path; running a command that names that file, or printing it through a grep, is flagged by the project hook.
**How to avoid:** the path-existence loop must skip it with a character-class pattern that does not spell the path (for example `grep -v 'common/l[l]m'`), and the plan must not name it in any command.

## Code Examples

These are proposals written against the file as read; the executor adapts names but keeps the pinned strings.

### 1. State and reset (E3, E5)
```js
let conversationId = null, epoch = 0, inflight = null;  // the server's id; counts resets; the running ask's AbortController
const DETAIL_HINT = $("detail").textContent;

// Start over: the next question carries no id. A running ask is cancelled and its late result is ignored.
function resetConversation() {
  epoch++; conversationId = null;
  if (inflight) { inflight.abort(); inflight = null; }
  $("log").replaceChildren(); $("detail").replaceChildren(DETAIL_HINT); showError("");
  updateChat();
}
$("newconv").onclick = () => resetConversation();
```

### 2. HTTP error with status and detail; readable conversation 409 (E4, E11)
```js
const CONV_GONE = "no such conversation";
function httpError(status, detail) {
  const text = typeof detail === "string" ? detail : JSON.stringify(detail);
  const hint = status === 409 && text.includes("conversation is full") ? " Use the New conversation button." : "";
  const err = new Error(status === 409 && text.includes("conversation is") ? text + hint : `${status}: ${text}`);
  err.status = status; err.detail = text;
  return err;
}
```
Use in `streamAsk`: `throw httpError(res.status, detail);` and pass `signal` into `fetch`.

### 3. Ask handler skeleton (E12-E14)
```js
$("ask").onsubmit = async (e) => {
  e.preventDefault(); showError("");
  const question = $("question").value.trim(); const ids = targets(); if (!question || (ids !== null && !ids.length)) return;
  $("question").value = ""; $("send").disabled = true;
  const mine = epoch, ctl = new AbortController(); inflight = ctl;
  const asked = el("div", { class: "msg q" }, question, el("br"), el("small", { class: "meta" }, "asked of: " + scopeLabel()));
  $("log").append(asked);
  try {
    const about = $("mode").value === "about";
    const msg = el("div", { class: "msg a" });
    const shown = document.createTextNode("");
    msg.append(shown); $("log").append(msg);
    let r;
    try {
      if (about) {
        r = await api("/v1/ask-about", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, doc_ids: ids }), signal: ctl.signal });
      } else {
        r = await askContent(question, ids, ctl.signal, (text) => { shown.data += text; msg.scrollIntoView({ block: "nearest" }); },
                             (note) => msg.before(el("div", { class: "meta" }, note)));
      }
    } catch (err) {
      if (mine !== epoch) return;  // superseded: the log was cleared and the stream aborted
      showError(err.message);
      msg.prepend(el("span", { class: "tag bad" }, shown.data ? "incomplete" : "no answer"), el("br"));
      msg.append(el("br"), longText(err.message));
      msg.scrollIntoView(); checkStatus();
      r = null;
    }
    if (mine !== epoch) return;
    if (r) {
      if (!about && r.conversation_id) conversationId = r.conversation_id;
      answers[r.query_id] = r;
      msg.replaceChildren(r.answer || "");
      if (r.kind === "clarify") msg.prepend(el("span", { class: "tag" }, "clarifying question"), el("br"));
      /* ... replace / blocked / abstained tags exactly as today ... */
      msg.onclick = () => { document.querySelectorAll(".a").forEach((n) => n.classList.remove("sel")); msg.classList.add("sel");
        r.kind === "clarify" ? detailClarify() : r.profiles ? detailAbout(r) : detail(r); };
      msg.click(); msg.scrollIntoView();
    }
  } catch (err) {
    if (mine === epoch) showError(err.message);
  } finally {
    if (inflight === ctl) inflight = null;
    if (mine === epoch) { $("send").disabled = false; $("question").focus(); }
  }
};
```

### 4. Content ask with one retry (E5, E13)
```js
async function askContent(question, ids, signal, onText, onNote) {
  const body = { question, doc_ids: ids, config: $("config").value };
  if (conversationId) body.conversation_id = conversationId;
  const sent = body.conversation_id;
  try { return await streamAsk("/v1/ask/stream", body, onText, signal); }
  catch (err) { if (!(sent && err.status === 404 && err.detail === CONV_GONE)) throw err; }
  conversationId = null;  // the server no longer knows it; start again, once
  onNote("Started a new conversation (the previous one is no longer available).");
  delete body.conversation_id;
  return streamAsk("/v1/ask/stream", body, onText, signal);
}
function detailClarify() {
  $("detail").replaceChildren(el("div", { class: "meta" }, "A clarifying question: no passages were retrieved for it."));
}
```
The note is inserted before the answer bubble with `msg.before(...)` so it reads in order; it is a text node inside a `div.meta`.

### 5. Optional node harness (design, not full code)
`tests/page_harness.js` reads the page's `<script>` text from stdin, builds a context with a recording fake DOM, and prints one JSON result; `tests/test_page_conversation.py` runs it with `subprocess` and skips when `shutil.which("node")` is None (same pattern as the syntax test).

- Fake DOM: `document.getElementById(id)` returns a cached fake element (`value`, `textContent`, `disabled`, `hidden`, `children[]`, `append/prepend/replaceChildren/before` recording text, `classList.add/remove`, `scrollIntoView`, `focus`, `click()` calling `onclick`); `createElement`, `createTextNode` (`{data}`), `querySelectorAll` returning `[]`. Defaults: `scope.value = "all"`, `mode.value = "content"`, `config.value = "weighted"`.
- Globals: `setTimeout`/`clearTimeout` no-ops (the script starts polling timers), `fetch` a function that routes by URL: `/v1/health` -> `{ready:true}`, `/v1/status` -> a small ok object, `/v1/documents` -> one ready document, `/v1/ask/stream` -> a scripted `new Response(body, {status})` (node 24 has native `Response`, `TextDecoder`, `AbortController`); it records every request body.
- Read state with `vm.runInContext("conversationId", ctx)` (top-level `let` lives in the context's global lexical scope).
- Scenarios (each asserts on recorded request bodies and recorded DOM text): (a) first ask sends no `conversation_id`, the `final` returns an id, the second ask sends it; (b) `$("newconv").onclick()` then ask sends none; (c) `$("scope").onchange()` resets; (d) scripted 404 `{"detail":"no such conversation"}` with an id sent -> exactly two requests, the second without the id, a note recorded; (e) 404 `"no such document"` -> one request, error shown; (f) 409 full -> one request, id unchanged, message contains "New conversation"; (g) clarify `final` with answer `Do you mean <b>x</b>?` -> bubble children are the text node with the literal `<b>x</b>` and a "clarifying question" tag, no `detail` table; (h) reset while a never-finishing stream is open -> the request's `signal.aborted` is true and the late `final` does not set `conversationId`.

If the planner judges (h) too heavy, drop it and keep it in the manual list; (a)-(g) are cheap.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Page sends only the question; log is client-only | Page keeps one server-issued id and resets it with the target set | This phase | Follow-ups work in the browser; scope-bound conversations need the reset sites |
| `select()` keeps the log across documents (comment line 183, test 648) | `select()` resets under scope "one" only | This phase | Old test rewritten; other scopes unchanged |

**Deprecated/outdated:** the comment at line 183 and the test `test_choosing_another_document_keeps_the_conversation_on_the_page` describe the old contract.

## Docs Targets (DOCS-01)

### `rag/README.md` (322 lines now; last heading is `## Step 10: questions about the documents themselves` at line 314, ending at line 322)
Style to match: heading `## Step N: lowercase description`; an optional 4-space-indented command or request line; then plain prose with backticked paths and settings; Step 10 is 9 lines, Step 8 is about 18 lines, Step 9 carries tables [VERIFIED: rag/README.md lines 227-322 read this session]. Step 11 goes at the end of the file as `## Step 11: chat memory`; keep it to roughly 25-40 lines. Content (D-08), each claim checked against its source of truth at execution time:

| Claim to write | Source of truth to open at execution | Planned value [CITED: plan] |
|---|---|---|
| A conversation is a server-side file per `conversation_id`; the client sends only the new message and the id | `rag/api/conversations.py` constants `CONVERSATION_ID`, `CONVERSATIONS_DIR`; 02-03-SUMMARY.md D-01 outcome | single-document: `data/uploads/<doc_id>/chat/conversations/<id>.json`; several or all: `data/uploads/_conversations/<owner key>/<id>.json` (02-04-PLAN.md artifacts row) |
| Delete removes it | `DocumentService.delete` and `purge_document` | folder removal plus purge under the store lock (02-04-PLAN.md Task 3) |
| History block | `rag/query/history.py` | `HISTORY_WINDOW_TURNS = 6`, `HISTORY_BLOCK_MAX_WORDS = 400`, `HISTORY_ANSWER_MAX_WORDS = 40`, `HISTORY_QUESTION_MAX_WORDS = 60` (01-05-PLAN.md lines 139-142) |
| Hard cap | `rag/query/history.py`, `rag/api/conversations.py` | `CONVERSATION_MAX_TURNS = 50`, `CONVERSATION_MAX_STORED_WORDS = 20000` (02-02-PLAN.md line 160); refusal 409 `"this conversation is full; start a new conversation"` |
| Errors the client sees | `rag/api/main.py` `guarded()` | 404 `"no such conversation"`; 409 `"conversation is busy, retry when the previous answer is finished"`; 409 `"this conversation is full; start a new conversation"` (02-04-PLAN.md truth 4, quoted verbatim) |
| Rewrite switch and shipped defaults | `build_default_service` in `rag/api/main.py`; `.env.example`; the `Decision:` line | `RAG_REWRITE` (`"1"` turns on, unset or anything else off), `RAG_REWRITER` default `ollama:qwen2.5:7b` (03-04-PLAN.md truths 2); both can change in Phase 4 plan 04-09, so read the code, not this table |
| Phase 4 numbers | `docs/chat_memory_eval.md` `## Results` | labelled lines include `Decision: ships on|off`, `Rewriter chosen:`, `Question slot:`, `Judge and rewriter are the same model:`, `Rule commit:` (04-08-PLAN.md lines 24-25 and 04-09-PLAN.md line 26) |
| Provisional status | same file | With any pending-human row the Decision line reads `Decision: ships off (...; provisional: items pending human review)` (04-08-PLAN.md truth 5); D-11: say so in those words |

Also add one sentence at the end of Step 8 (line 244, after the streaming paragraph): follow-ups keep a conversation, see Step 11. Optional but cheap, and Step 8's API list at line 238-239 does not mention `conversation_id`.

### `docs/backlog.md` (49 lines)
Two conventions are in use [VERIFIED: docs/backlog.md read this session]: the "UI and API" section writes `- **Title: done** (date). what it is. Still open: ...`; the "Retrieval and evaluation" and "From the code review" sections use `- [x]` checkboxes. The item to change lives in "UI and API", so use the `**Title: done** (date)` form.

| Line | Now | Change |
|---|---|---|
| 7 | `- **Chat has no memory.** Every question stands alone, ...` (one long bullet) | Replace with `- **Chat memory: done** (<date from `date +%F` at execution>). ...` pointing to `rag/README.md` Step 11 and `docs/chat_memory_eval.md`, and ending `Still open:` with the items below. Date is the execution date, not a guess |
| after 7 (UI and API) | — | New bullets: compaction of long histories (rolling summary at about 70% of the history budget; the hard cap and window replace it today); a reload-resume `GET` for one conversation (v2 CONV-05); the rewritten question and the rewrite `fallback` flag shown in the "what the pipeline saw" panel (v2 CONV-08; the page ignores `rewrite.status` today); turn counter and cap warning before the cap is hit (deferred in CONTEXT) |
| 20 (Security) `- Retention for traces in data/uploads/<id>/chat/ of documents that are not deleted.` | traces only | Add a sibling bullet: conversation retention, a TTL for conversation files of documents that are never deleted, for cross-document files under `_conversations/<owner key>/`, for conversations abandoned by "New conversation" or a scope change (the page has no per-conversation delete, CONV-06), and for one-turn files made by page questions before this phase (the page sent no id, so each question created its own conversation file) |
| 27 `- Query rewriting and intent classification: only add them if the golden set shows a gain.` | stale | Split: query rewriting for follow-ups is built behind `RAG_REWRITE` and measured in `docs/chat_memory_eval.md` (state ships on or off as the Decision line says); intent classification is still open under the same rule |
| 13 | `Cross-document questions are not saved as traces; decide ...` | Leave; true. (Conversation files for several or all documents are stored, which is a different thing: do not blur them) |

### `interview/05_conversation_memory_and_cost.md` (94 lines)
Labels line 7 defines `Built`, `Not built`, `General` [VERIFIED: file lines 7]. The ROADMAP and REQUIREMENTS words "designed" and "built" map to the file's actual labels `Not built` and `Built`; use the file's labels. If an item is built but its answer-level result is unreviewed, add a fourth label `Not measured` to line 7 and use it, because CLAUDE.md asks each point to be labelled built, designed, general or not measured.

| Lines | Now | Change |
|---|---|---|
| 5 | "In this project the chat is **single-turn**: every question stands alone. Conversation memory and compaction are **not built**. ..." | Rewrite: conversation memory (server-side history, history block, rewrite step, one clarifying question, topic switch) is **built**; whether rewriting is on by default and the measured effect come from `docs/chat_memory_eval.md` (state ships on or off and the provisional wording of D-11 when it applies); compaction and cost tracking stay **not built**; the hard cap and window are what exist instead of compaction |
| 27-29 | section 1 "In this repo": `**Not built.**` AskRequest/pipeline description, "Where it would plug in", backlog pointer | Replace with `**Built.**` bullets citing real files: `rag/api/conversations.py`, `rag/query/history.py`, `rag/query/rewrite.py`, `rag/api/service.py`, `rag/api/main.py`, `rag/api/static/index.html`, `rag/experiments/conversation.py`, `data/golden/ddia_conversations.jsonl`, `docs/chat_memory_eval.md` (each path confirmed to exist at execution); keep "Where it plugs in" as past-tense fact |
| 18-24 ("Go deeper") | General interview knowledge, plus named failure modes and an evaluation design | Keep as **General**; add one-line `Built:` pointers only where a test or number exists (four named bad fake rewrites -> the Phase 3 tests; evaluation design -> the Phase 4 experiment). Do not label the "keep the previous turn's passages" idea Built: nothing builds it |
| 56-57 | section 2 "In this repo": `**Not built.** ...` and "Because the app is stateless, it can never overflow the context from history; it is the first thing that would change when memory is added." | Split: **Built** = sliding window of the last N turns, the answer/question word cuts, the turn and word hard cap with a 409, and the prompt-budget check including the 3000 thinking tokens (all with Phase 2 tests); **Not built** = rolling summary, structured memory, retrieval over history, the 70% threshold. Delete the "stateless" sentence: it is false now |
| 78-83 | section 3 | Stays **Built, partial** / **Not built**. Add nothing unless a fact is verified; do not claim the rewrite call's tokens are recorded (not checked) |
| 89-92 (one-line revision) | General | Leave |

Also change **`interview/README.md` line 20** (index row: "**all three are not built here, the file is the design plus what exists**") and check line 70 (a General answer; it points to `05`, section 1: leave). The other docs contain no further "single-turn", "stateless" or "no memory" statement [VERIFIED: Grep over interview/*.md, docs/*.md, rag/README.md, CLAUDE.md this session; only the lines listed above matched].

### What must stay "Not built"
Compaction (rolling summary, structured memory, retrieval over history, the 70% trigger); cost tracking and the tracing tool; time to first token; a reload-resume `GET`; a conversation list; rewrite-fallback shown in the page; automatic routing to the about path. What is "Built" is the hard cap, window, history block, owner-scoped deletable store, rewrite step and clarify, each backed by a test; what is "measured" is only what `docs/chat_memory_eval.md` records.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Phase 2-4 strings and constants (404/409 details, `RAG_REWRITE`/`RAG_REWRITER` names and defaults, `HISTORY_*` and `CONVERSATION_*` values, file layout) will be built as their PLAN files say. Tagged [CITED: plan] throughout, not [VERIFIED], because the code does not exist yet | Docs Targets, Edit points | The page would mismatch a deviating detail string; mitigated by a plan precondition that opens `02-04-SUMMARY.md` and `03-04-SUMMARY.md` and greps the real `guarded()` strings before editing |
| A2 | `select()` should reset only under scope "one" (narrowing D-02's unconditional "select(id) choosing a different document") | Edit points E8, Open Questions | If the owner wants the literal D-02, a highlight click under "all my documents" would also drop the conversation and clear the log; one-line change |
| A3 | An upload under scope "one" must also reset (gap E10) | Edit points | Low: without it the server 404 plus retry note covers it, with a misleading notice |
| A4 | The optional node harness is acceptable although D-07 says "the page has no automated test" and plans manual verification | Validation | If rejected, criteria 1-3 rest on the manual pass plus static greps only |
| A5 | Phase 4 will have written `docs/chat_memory_eval.md` with one `Decision: ships` line | Docs Targets | If Phase 4 is blocked the docs plans must say "not measured"; precondition V-8 catches it |
| A6 | A top-level `let` in a classic `<script>` is readable and assignable from the devtools console (used by the manual stale-id check) | Validation manual list | If not, use the two-tab procedure instead; both are listed |

## Open Questions (RESOLVED)

1. **D-04 says "the existing abort path"; the page has none.**
   - What we know: `AbortController`, `abort`, `signal` all count 0 in `index.html`.
   - RESOLVED: the plan adds `AbortController` plus the epoch counter (Pattern 1); the server side already releases the lease when the client disconnects.

2. **D-07 says the page has no automated test.**
   - What we know: nine tests read the served page; one contradicts D-02.
   - RESOLVED: keep the eight compatible tests green by preserving their pinned strings; rewrite `test_choosing_another_document_keeps_the_conversation_on_the_page` in the page commit; add the new static contract test.

3. **D-02 "select(id) choosing a different document": unconditional or scope-aware?**
   - What we know: under scope "all" or "checked" the target set does not change when the highlighted row changes; ROADMAP criterion 1 says "a change of the selected documents".
   - RESOLVED: reset only when `scope === "one"` and the id differs (narrowing recorded as A2). The old comment at line 183 is rewritten to say so.

4. **Where else does the target set change without D-02 naming it?**
   - RESOLVED: the upload handler's `selected = d.id` (line 220) under scope "one" (E10). Everything else is covered by the server 404 safety net.

5. **CONTEXT "Specific Ideas" says: delete the document mid-conversation and the next question starts fresh with the notice.**
   - What we know: under D-02 the page resets on delete (log cleared, no notice); the notice appears only when the page did not know.
   - RESOLVED: the manual checklist tests the delete case as "log clears, next request carries no id", and tests the notice separately with (a) the console line `conversationId = "a".repeat(32)` then ask, or (b) two tabs with at least two documents under scope "all", deleting a document in tab B then asking in tab A. With scope "one" and a deleted document the server answers `404 "no such document"` (document check runs first, 02-04-PLAN.md truth 3), which is correctly not the stale path.

6. **D-01 says "ordinary or stream"; which routes does the page use?**
   - RESOLVED: the page's only content route is `POST /v1/ask/stream` (line 273); `api()` carries only `/v1/ask-about`, which stays stateless. The id is set and sent at exactly one call site.

7. **Phase 4 numbers do not exist yet and may be provisional.**
   - RESOLVED: docs plans open with a precondition on `docs/chat_memory_eval.md`; Step 11 and the interview note copy figures from its Results lines only, and use the file's own provisional wording when the Decision line says so (D-11). V-9 checks it mechanically.

8. **Should the page surface `rewrite.status === "fallback"` (the visible flag of Phase 3 D-09)?**
   - RESOLVED: no, out of scope (CONV-08 and "Not in this phase"); recorded as part of the backlog item so the gap is honest. Flag it in the phase summary for the owner.

9. **Does a scope-"all" conversation survive a newly finished upload?**
   - What we know: the scope key for `doc_ids = None` is `("all", ())`, independent of which documents exist (02-03-PLAN.md `scope_of`).
   - RESOLVED: yes; no page reset is needed when a document becomes ready.

10. **Roadmap/requirement wording says "designed"; the interview file's labels are `Not built`.**
    - RESOLVED: use the file's labels (`Built`, `Not built`, `General`; add `Not measured` only if needed).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| node | `test_the_page_script_has_valid_syntax`, optional harness | yes | v24.20.0 [VERIFIED: Bash] | tests skip without node |
| python / pytest | all test commands | yes (project baseline) | — | — |
| A desktop browser | manual pass (criteria 1-3) | not usable by the unattended run | — | VERIFICATION marked `human_needed` (D-07) |
| Model tunnel, Ollama, OpenSearch | real clarification and stale-id manual checks | not needed for the automated checks | — | devtools fetch override gives a canned `final` (below) |

**Missing dependencies with no fallback:** none for planning or execution. **With fallback:** the browser pass is `human_needed`.

## Validation Architecture

`workflow.nyquist_validation` is `true` in `.planning/config.json`.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8 plus node 24 for syntax and the optional harness |
| Config file | none (no pytest.ini; see CLAUDE.md) |
| Quick run command | `python -m pytest tests/test_page_conversation.py -q` (new; seconds, no models) |
| Pinned-page run | see V-1 (explicit node ids, no glob) |
| Full suite command | `python -m pytest tests -q` (baseline after Phase 4 is in `.planning/STATE.md`; not run by this research) |

### Phase Requirements -> Test Map

| ID | Check | Type | Command | fails_when |
|----|-------|------|---------|------------|
| V-1 | The eight compatible page tests still pass and the rewritten one passes | automated | `python -m pytest tests/test_api.py::test_the_page_is_served tests/test_api.py::test_choosing_another_document_keeps_the_conversation_on_the_page tests/test_api.py::test_the_ask_box_is_multi_line_with_scope_and_mode_below_it_and_errors_fold tests/test_api.py::test_the_page_shows_skeleton_rows_and_waits_for_the_models tests/test_api.py::test_the_page_has_a_light_that_shows_the_details_on_hover tests/test_api.py::test_the_page_script_has_valid_syntax tests/test_stream_api.py::test_the_page_reads_the_stream_and_shows_text_only tests/test_stream_api.py::test_a_failed_ask_leaves_one_bubble_and_the_page_has_no_second_one tests/test_stream_api.py::test_the_page_shows_why_the_models_did_not_load -q` | any failure, or a skip of the syntax test while `node --version` works (the check did not run) |
| V-2 | Syntax of the edited script | automated | `python -m pytest tests/test_api.py::test_the_page_script_has_valid_syntax -q` | exit non-zero (a typo in the edit) |
| V-3 | The contradicted test now states the new contract | automated | in the page commit, the test body asserts `resetConversation(` and `$("scope").value === "one"` inside the `function select(` slice, keeps `"replaceChildren" not in select_function`, keeps `"asked of:"` and `"no answer"` | the test still says only "the log is not cleared when the selection changes", or the slice contains no `resetConversation(` |
| V-4 | PAGE-01 id lifecycle, static | automated | new `tests/test_page_conversation.py`, cases below | any assertion fails on the new page; and every case must FAIL on the old page (see fail-first) |
| V-5 | PAGE-01/02 behaviour | automated, optional (A4) | the node harness scenarios (a)-(h) | request bodies, abort flag or DOM text differ from the scenario |
| V-6 | D-06 no markup insertion | automated grep | `test "$(grep -c 'innerHTML' rag/api/static/index.html)" = 1 && test "$(grep -cE 'outerHTML|insertAdjacentHTML|document\.write' rag/api/static/index.html)" = 0` | any count differs |
| V-7 | Docs structure | automated grep | see "Docs checks" | see there |
| V-8 | Phase 4 file precondition for docs plans | automated | `test "$(grep -cE '^Decision: ships (on\|off)' docs/chat_memory_eval.md)" = 1 && grep -q '^## Results' docs/chat_memory_eval.md` | file missing, no or two Decision lines: stop and record "not measured" instead of writing numbers |
| V-9 | Every copied number exists in the eval file | automated | see "Docs checks" | a number in Step 11's measured paragraph or the interview note is absent from `docs/chat_memory_eval.md` |
| V-10 | Manual browser pass, criteria 1-3 | manual, `human_needed` | checklist below | any step's expectation not seen |

### Static contract cases for `tests/test_page_conversation.py` (V-4), with baselines on the current page

Baselines measured this session: `conversation_id` 0, `conversationId` 0, `resetConversation` 0, `AbortController` 0, `newconv` 0, `no such conversation` 0, `innerHTML` 1.

| Case | Assertion on `client.get("/").text` | fails_when (old page) |
|---|---|---|
| declares the state | `page.count("let conversationId = null") == 1` | 0 on the old page |
| New conversation button is a non-submitting button | regex `<button type="button" id="newconv"` present, and `page.index('id="question"') < page.index('id="scope"') < page.index('id="config"') < page.index('id="newconv"') < page.index('id="send"')` | absent |
| six reset call sites plus the definition | `page.count("resetConversation(") == 7` | 0 |
| each site is where it should be | the `$("scope").onchange` line contains `resetConversation(`; the `function select(` slice contains `resetConversation(` and `$("scope").value === "one"`; the `pick.onclick` line contains `$("scope").value === "checked"` and `resetConversation(`; the `del.onclick` line contains `resetConversation(`; the `$("newconv").onclick` line contains `resetConversation(` | any missing |
| id only sent when set, and only on the content route | `"body.conversation_id = conversationId"` in page; the `/v1/ask-about` line contains no `conversation`: `[l for l in page.splitlines() if "/v1/ask-about" in l]` all lack `conversation` | missing / about line has it |
| id taken from the response, not from the DOM | `"r.conversation_id"` in page and `"localStorage"` not in page | missing |
| stale-id retry is exact | `'"no such conversation"'` in page and `"err.status === 404"` in page and the retry exists once: `page.count("Started a new conversation (the previous one is no longer available).") == 1` | 0 |
| abort wired | `page.count("new AbortController") == 1` and `"signal" in streamAsk slice` | 0 |
| clarify rendering | `'r.kind === "clarify"'` in page and `"clarifying question"` in page | missing |
| script length sanity | the script contains no `</script>` before the real end (the syntax test regex is greedy) | n/a |

### Fail-first procedure (project rule)
`git stash push -q -m p5-page-tests -- rag`, run `python -m pytest tests/test_page_conversation.py -q` (must fail), then `git stash pop -q`. `index.html` is under `rag/`, so the stash removes the page edit and keeps the tests. Use a unique message because the stash stack is shared by worktrees.

### Docs checks (V-7, V-9)
```
# structure
test "$(grep -c '^## Step 11: chat memory' rag/README.md)" = 1
test "$(grep -n '^## Step' rag/README.md | tail -1 | grep -c 'Step 11')" = 1
test "$(grep -c 'Chat has no memory' docs/backlog.md)" = 0
test "$(grep -c 'Chat memory: done' docs/backlog.md)" = 1
grep -qi 'compaction' docs/backlog.md && grep -qi 'retention' docs/backlog.md
test "$(grep -c 'single-turn' interview/05_conversation_memory_and_cost.md)" = 0
test "$(grep -c 'Because the app is stateless' interview/05_conversation_memory_and_cost.md)" = 0
test "$(grep -c 'all three are not built here' interview/README.md)" = 0
# honesty: compaction and cost stay not built
grep -c 'Not built' interview/05_conversation_memory_and_cost.md   # must stay >= 2 (sections 2 and 3)
```
fails_when: any `test` exits non-zero; the `Not built` count drops below 2 (a section was over-relabelled).

Number provenance (V-9): put the measured figures under a labelled paragraph or sub-heading (for example a line starting `Measured:` in Step 11, and a `Measured` bullet in interview section 1) so the check can isolate them:
```
for n in $(sed -n '/^Measured:/,/^$/p' rag/README.md | grep -oE '[0-9]+\.[0-9]+|[0-9]+/[0-9]+' | sort -u); do
  grep -qF -- "$n" docs/chat_memory_eval.md || echo "NOT IN EVAL FILE: $n"; done
```
fails_when: any `NOT IN EVAL FILE` line prints. Constants such as 6, 400, 50 are checked separately against `rag/query/history.py` with a plain `grep -F 'HISTORY_WINDOW_TURNS = 6'` per constant, because they are code values, not eval numbers.

Path existence (honesty rule: cite only real paths), skipping the one hook-flagged path with a pattern that does not spell it:
```
grep -oE '`[A-Za-z0-9_./-]+\.(py|md|html|jsonl|js)`' interview/05_conversation_memory_and_cost.md rag/README.md | sed 's/.*`\(.*\)`/\1/' | sort -u | grep -v 'common/l[l]m' | while read p; do test -e "$p" || echo "MISSING $p"; done
```
fails_when: any `MISSING` line.

Also: the Decision words must match: `grep -c` the interview note for `ships on` or `ships off` and compare to the eval file's line; with `pending-human` rows present, the note must contain `provisional`.

### Manual browser checklist (V-10, goes into the phase VERIFICATION as `human_needed`)
Setup: `RAG_REWRITE=1 RAG_STORE=opensearch python -m uvicorn rag.api.main:app --port 18642` (environment first, so no `.env` read; start WSL, OpenSearch and the tunnel per CLAUDE.md), two ready PDFs, browser devtools open on the Network tab with "Disable cache" ticked, hard reload.

1. **Follow-up (SC1).** Scope "all my documents", ask a content question; in the Network tab the first `ask/stream` request body has no `conversation_id`; its `final` has one. Ask "and what about its drawbacks?"; the second request body contains the same id and the answer refers to the earlier subject. Expected: same id, answer uses the earlier turn. Fails if the second body has no id or a different id.
2. **New conversation (SC1).** Click "New conversation": the log empties, the pipeline panel shows its hint. Ask again: request body has no `conversation_id`. Fails if the id is sent, or the log stays.
3. **Target change (SC1).** After one answer, change the scope select: log empties, next body has no id. Repeat: under scope "checked" tick a document; under scope "this document" click another document in the list. Under scope "all" click a row: log stays and the id is kept. Fails if the id survives a scope or target change, or is dropped by a mere highlight under "all".
4. **Delete (SC1/D-02).** Scope "all", one answer, delete a document: log empties, next body has no id.
5. **Stale id (SC2).** (a) Console: type `conversationId = "a".repeat(32)` then ask: the Network tab shows a 404 then a second request without `conversation_id`; the log shows "Started a new conversation (the previous one is no longer available)." above the answer; no red error remains. Or (b) two tabs, two documents, scope "all": ask in tab A, delete a document in tab B, ask a follow-up in tab A: same outcome. Fails if an error is left to clear by hand, or more than two requests are sent.
6. **Clarify renders as text (SC3).** In the console override fetch so one ask returns a canned clarification, then ask:
   ```
   const realFetch = window.fetch;
   window.fetch = async (u, o) => u.endsWith("/v1/ask/stream") ? new Response("event: final\ndata: " + JSON.stringify({kind:"clarify", answer:"Do you mean <b>x</b> or the other one?", conversation_id:"a".repeat(32), turn:2, passages:[], citations:[], stages:[], blocked:[], skipped_by_scanner:[], documents:[], abstained:false, replace:false, llm:"rewriter", seconds:0, query_id:"clarify-1", rewrite:{status:"clarify"}}) + "\n\n", {status:200}) : realFetch(u, o);
   ```
   Expected: the bubble shows `<b>x</b>` literally (no bold), a "clarifying question" tag, clicking it shows the one-line meta note and no stages table; the next real request (restore `window.fetch = realFetch`) carries that id. With a real model and `RAG_REWRITE=1`, ask an ambiguous pronoun follow-up when two plausible referents exist to see the genuine path. Fails if `x` is bold, a passages heading appears, or the id is dropped.
7. **Superseded stream (D-04).** Start a long answer, click "New conversation" while tokens arrive: the stream stops, the log is empty, Ask is enabled, and the next request has no id (the late `final` must not bring the old id back; check by asking once more and reading the body).
8. **Messages (D-04).** Console fetch override returning `new Response(JSON.stringify({detail:"this conversation is full; start a new conversation"}), {status:409})`: the bubble and error area show a readable sentence ending with "Use the New conversation button."; the id is unchanged; Ask is enabled. Repeat with the busy sentence.
9. **Dark mode and layout.** The new button matches the other buttons in light and dark themes and does not wrap the controls row at a 900 px window.

### Sampling Rate
- **Per task commit:** V-2 and the new `tests/test_page_conversation.py` (seconds).
- **Per wave merge:** V-1 plus the new file plus V-6.
- **Phase gate:** full suite green at the recorded baseline, V-7 to V-9 for docs, then the `human_needed` checklist.

### Wave 0 Gaps
- [ ] `tests/test_page_conversation.py` - V-4 (and V-5 if A4 is accepted)
- [ ] `tests/page_harness.js` - only if A4 is accepted
- [ ] Rewrite `tests/test_api.py` lines 648-653 (V-3) in the same commit as the page edit, so no commit leaves the suite red

## Security Domain

`security_enforcement` is `true`, ASVS level 1, block on high [VERIFIED: .planning/config.json lines 48-50].

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No login yet (`current_owner`, `docs/auth_plan.md`); the page adds none |
| V3 Session Management | yes (light) | The `conversation_id` is a server-issued opaque handle, not a credential; ownership is enforced by the store from `current_owner`, so a leaked or guessed id gives a 404. The page keeps it in memory only (no `localStorage`, no URL, no cookie) |
| V4 Access Control | yes | Server side only (404 not 403, owner filter in the store); the page must never send an owner or history field |
| V5 Input Validation / Output Encoding | yes | `textContent` and text nodes for every new string: the clarification, the notices, the labels, the server `detail` shown in errors (through `longText`) |
| V6 Cryptography | no | Nothing hand-rolled; the id comes from the server |
| V13 API / Web Service | yes | The page's requests keep the same-origin POST that passes the server's Origin and Host checks |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XSS through model-written or poisoned text in a clarifying question (`<b>x</b>`, `<img onerror>`) | Tampering / Elevation | Render with `msg.replaceChildren(r.answer)` (text node); never build markup; static counts V-6; manual step 6 |
| XSS through the error `detail` shown for a 404/409 | Tampering | `showError` and `longText` use text; `httpError` only builds a string |
| Conversation id surfacing in the DOM or logs | Information disclosure | Never rendered; `console` not used; no `localStorage` (static assertion) |
| Automatic retry loop on 404 | Denial of service | Retry exactly once, only when an id was sent; static count of the retry note equals 1; harness scenario (d) counts two requests |
| Late result of an aborted ask resurrecting a discarded conversation | Repudiation / integrity | Epoch guard plus abort (Pattern 1); manual step 7 |
| Client-supplied history or owner | Spoofing | No such field is added to any request body; static case checks the body keys (`question`, `doc_ids`, `config`, `conversation_id` only) |
| Untrusted content in docs (secrets, emails, tunnel host) | Information disclosure | Docs checks: no email, IP address or `.env` content in Step 11, the backlog or the interview note (same grep as 04-08-PLAN.md line 179: `grep -cE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}\|[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+'` must print 0 on the new text) |

## Project Constraints (from CLAUDE.md)

- Run tests with `python -m pytest tests -q`; list without running with `--collect-only -q`. Do not start the app in this research; the manual pass starts it with `RAG_STORE=opensearch python -m uvicorn rag.api.main:app --port 18642`.
- Never name the provider module under `rag/common/` or the vLLM test file in a command or search; never glob `tests/` or `rag/common/`; never read `.env`; do not read `HANDOFF.md` with Read.
- `SYSTEM_PROMPT` word for word; page numbers are PDF pages; no LLM disk cache for uploads; caller only from `current_owner`; 404 not 403; `textContent` never `innerHTML` in `rag/api/static/index.html`; answers stream only through `StreamGuard`.
- Commit messages: write to a file and `git commit -F <file>`; do not push or open a PR.
- Prove a new regression test fails on old code: `git stash push -q -m <unique-tag> -- rag`, then `git stash pop -q`.
- Timing-sensitive tests wait on a condition (Event/poll with a 30 s ceiling), never a fixed sleep: applies to harness scenario (h).
- Keep `interview/` honest: label each point built, designed, general or not measured; cite only real paths and recorded numbers; numbers from committed files, never gitignored `runs/`.
- Typing and style: `Optional[...]`-style typing, double quotes, lines <= 120 characters in Python; the page is JS, follow its existing one-line handler style.
- GSD workflow enforcement: file edits go through a GSD command (`/gsd-execute-phase`); the flow run owns the `flow/chat-memory` branch.

## Sources

### Primary (HIGH confidence)
- `rag/api/static/index.html` (all 380 lines, Read this session) - edit points, handlers, existing comments
- `tests/test_api.py` lines 120-160, 640-810 and `tests/test_stream_api.py` lines 138-217, 395-404 (Read) - pinned page text
- `rag/api/main.py` lines 118-140, 286-395 (Read) - request models, `guarded`, stream wiring, `_sse`
- `rag/README.md` 1-58, 225-323; `docs/backlog.md` (all); `interview/05_conversation_memory_and_cost.md` (all) (Read)
- `.planning/phases/05-chat-page-and-honest-docs/05-CONTEXT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md` (Read)
- `node --version` -> v24.20.0 (Bash)

### Secondary (MEDIUM confidence, plan text of unexecuted phases)
- `.planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-04-PLAN.md` (404/409 strings, response keys, truth 3 ordering), `02-03-PLAN.md` (`scope_of`, `purge_document`), `02-02-PLAN.md`, `01-05-PLAN.md` (constants)
- `.planning/phases/03-rewrite-clarify-and-topic-switch/03-04-PLAN.md` (clarify shape, `RAG_REWRITE`, `RAG_REWRITER`)
- `.planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-02-PLAN.md`, `04-08-PLAN.md`, `04-09-PLAN.md` (results file shape, Decision line, labelled lines)

### Tertiary (LOW confidence)
- none. No web research was needed: every question is answered by the repository; Context7 and web search were not used.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no packages; node verified
- Architecture (page edit points, pinned tests): HIGH - whole file and every page-reading test opened this session
- Docs targets: MEDIUM - exact current text is verified, replacement values depend on unexecuted Phases 2-4
- Pitfalls: HIGH for the page, MEDIUM for docs numbers

**Research date:** 2026-10-22
**Valid until:** until Phase 2-4 execution changes any string quoted above (re-read `02-04-SUMMARY.md`, `03-04-SUMMARY.md`, `04-08-SUMMARY.md`, `04-09-SUMMARY.md` before planning edits against them); otherwise 30 days
