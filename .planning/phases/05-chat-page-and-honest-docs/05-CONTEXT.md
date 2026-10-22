# Phase 5: Chat page and honest docs - Context

**Gathered:** 2026-10-22
**Status:** Ready for planning
**Mode:** `--auto` (every gray area took the recommended option; each pick is recorded as an assumption below)

<domain>
## Phase Boundary

The chat page uses conversations, and the docs describe only what was built and measured. Delivers: `rag/api/static/index.html` keeps the `conversation_id` from each `final` event / response and sends it with the next question, resets it on "New conversation" and on any change of the selected documents or scope, recovers from a 404 on a stored id by starting a new conversation on its own, shows a clarifying question (`kind: "clarify"`) as an ordinary assistant turn with `textContent`, and shows the 409 messages (conversation full, conversation busy) as readable notices; `rag/README.md` gains Step 11; `docs/backlog.md` marks chat memory done and adds compaction and conversation retention; `interview/05_conversation_memory_and_cost.md` relabels from "Not built" to "Built" only what was built and measured, with the recorded numbers.

Requirements: PAGE-01, PAGE-02, DOCS-01. Not in this phase: a reload-resume `GET` (v2 CONV-05), a conversation list, showing the rewritten question in the "what the pipeline saw" panel (v2 CONV-08), any API change.

</domain>

<decisions>
## Implementation Decisions

### Carried forward (locked earlier)
- Every ask route accepts `conversation_id` and returns it in the body and the `final` SSE event; foreign/unknown/malformed/wrong-scope ids are one 404 body "no such conversation"; full is 409 "this conversation is full; start a new conversation"; busy is 409 (Phase 2 D-04..D-08, D-16).
- A clarification returns `kind: "clarify"` with `passages: []`, `citations: []`, and on the stream one `final` with no `token` events; responses carry `kind` and `rewrite` (Phase 3 D-10, D-12).
- Untrusted text goes into the DOM with `textContent` only; answers stream only through `StreamGuard` (CLAUDE.md).

### Conversation id on the page (PAGE-01)
- **D-01:** One module-level `let conversationId = null;` in the page script. After a successful ask (ordinary or stream), set it from `r.conversation_id`. Send it as `conversation_id` in the request body only when non-null (no key when null). [auto: recommended]
- **D-02:** Reset `conversationId = null` on: the new "New conversation" button next to Ask; any change to `$("scope")`; `select(id)` choosing a different document; checking or unchecking a document while scope is "checked"; deleting a document that is in the current target set. A reset also clears the visible chat log so the screen matches the server's notion of the conversation. [auto: recommended — ARCHITECTURE.md: scope binding means the page must reset on a target change]
- **D-03:** Stale id: when an ask with a non-null id returns HTTP 404 with body detail "no such conversation", the page clears `conversationId`, shows a one-line notice "Started a new conversation (the previous one is no longer available).", and resends the same question once with no id. A 404 for any other reason (e.g. "no such document") is shown as today's error. Never more than one automatic retry. [auto: recommended]
- **D-04:** 409 "full" shows its message and a "New conversation" hint in the error area and leaves the id as is (the user chooses); 409 "busy" shows its message and re-enables Ask. A stream that is superseded by "New conversation" while running is aborted with the existing abort path, and its late `final` does not set `conversationId`. [auto: recommended — SUMMARY.md superseded-stream trap]

### Clarifying question (PAGE-02)
- **D-05:** When `r.kind === "clarify"`, the answer bubble shows `r.answer` with `textContent` (via the existing `msg.replaceChildren(text)` path), with no passages panel and a small "clarifying question" meta label; the next question is sent with the same `conversationId` so the server can resolve it. [auto: recommended]
- **D-06:** Every new string the page shows (notices, labels, clarify text) is inserted with `textContent` / `replaceChildren` of text nodes; no `innerHTML` is introduced. A static check in the plan greps the page for `innerHTML` (count must stay 0 outside the existing comment). [locked by CLAUDE.md]

### Verification of the page
- **D-07:** The page has no automated test today. Verification is (a) static checks (grep for `conversation_id`, `conversationId = null` at each reset site, no `innerHTML`), (b) API-level tests already in Phases 2-3 for the contract the page relies on, and (c) a manual browser pass covering ROADMAP success criteria 1-3, written as a checklist in the phase VERIFICATION and marked `human_needed` (the run is unattended, so it does not block planning or execution of the docs plans). [auto: recommended — ROADMAP scope note]

### Docs (DOCS-01)
- **D-08:** `rag/README.md` gains "## Step 11: chat memory" after Step 10: what a conversation is, where it is stored and deleted, the history block, the hard cap, the rewrite switch `RAG_REWRITE` and `RAG_REWRITER` with their shipped defaults, and the Phase 4 numbers copied from `docs/chat_memory_eval.md` (with a link). [auto: recommended]
- **D-09:** `docs/backlog.md`: the "Chat has no memory" item is marked done with a pointer to Step 11; new items added: compaction of long histories (rolling summary at about 70% of the history budget), conversation retention (TTL for conversations of documents never deleted; orphan one-turn files from page questions before this phase), a reload-resume GET, and showing the rewritten question in the pipeline panel. [auto: recommended]
- **D-10:** `interview/05_conversation_memory_and_cost.md`: each point is relabelled only if it is built and has a test or a recorded number: section 1 (follow-up) becomes **Built** for server-side history, the history block and the rewrite step, citing the files and `docs/chat_memory_eval.md` numbers, and states plainly whether rewriting ships on or off and why; section 2 (compaction) stays **Not built** (hard cap built instead, labelled Built); section 3 (cost tracking) stays **Not built**. The opening status paragraph is updated to match. Numbers are copied from committed files only, never from gitignored `runs/`. [locked by DOCS-01 and CLAUDE.md "keep interview/ notes honest"]
- **D-11:** If Phase 4 left the results provisional (golden rows `pending-human`), the docs say so in the same words as `docs/chat_memory_eval.md` and do not present the numbers as final. [auto: recommended]

### UI design contract
- **D-12:** No new visual design: reuse the page's existing button, notice and meta styles (`button`, `.msg`, `small.meta`, the error area). A UI-SPEC is not needed for one button, one label and two notices; if the plan-phase UI gate requires one, it is generated in auto mode from these decisions. [auto: recommended]

### Claude's Discretion
- Exact notice wording beyond D-03; button placement detail; Step 11 section order.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scope
- `.planning/REQUIREMENTS.md` — PAGE-01, PAGE-02, DOCS-01
- `.planning/ROADMAP.md` §"Phase 5" — success criteria 1-4, manual browser pass note

### Earlier phases (planned; executed before this phase runs)
- `.planning/phases/02-conversation-store-and-memory-in-the-answer-prompt/02-CONTEXT.md`, `02-04-PLAN.md` — response fields, 404/409 bodies
- `.planning/phases/03-rewrite-clarify-and-topic-switch/03-CONTEXT.md`, `03-04-PLAN.md` — `kind`, `rewrite`, clarify shape on both routes
- `.planning/phases/04-multi-turn-evaluation-and-the-default-decision/04-CONTEXT.md`, `04-02-PLAN.md`, `04-08-PLAN.md` — `docs/chat_memory_eval.md` (rule, results, decision)

### Code and docs
- `rag/api/static/index.html` — `streamAsk` (~line 230), the ask handler (~260-290), `select` (184), `$("scope").onchange` (209), `targets()` (~194), the `textContent`-only comment (117), `showError` (152), `longText` (139)
- `rag/README.md` (Steps 1-10 layout), `docs/backlog.md` ("UI and API" section, line 7), `interview/05_conversation_memory_and_cost.md` (labels at line 7; sections 1-3)
- `CLAUDE.md` — security conventions; keep `interview/` notes honest

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `el(tag, props, ...children)` helper and `replaceChildren` with text — the only DOM insertion pattern
- `showError(message)` and `longText` — error area with "more" folding
- `streamAsk(path, body, onToken)` — SSE reader returning the `final` data; the ordinary path through `api(path, options)`

### Established Patterns
- Untrusted text only via `textContent`; the file states it in a comment
- The page decides the target set in `targets()` and `scopeLabel()`; changes go through `updateChat`

### Integration Points
- Request body built at the ask handler (`{ question, doc_ids: ids, config }`) gains `conversation_id`
- Reset hooks: `$("scope").onchange`, `select`, the checkbox handler, the delete handler, the new button

</code_context>

<specifics>
## Specific Ideas

- Manual pass checklist: ask, follow up with "and what about its drawbacks?", confirm the answer uses the earlier turn; click New conversation and confirm the next request has no id (devtools network tab); delete the document mid-conversation and confirm the next question starts fresh with the notice; trigger a clarification (rewrite on) and confirm it renders as text, including a clarification containing `<b>x</b>` shown literally.

</specifics>

<deferred>
## Deferred Ideas

- Reload-resume GET and a conversation list (v2)
- Rewritten question in the pipeline panel (v2 CONV-08)
- Turn counter and cap warning before the cap is hit

</deferred>

---

*Phase: 05-chat-page-and-honest-docs*
*Context gathered: 2026-10-22 (auto mode)*
