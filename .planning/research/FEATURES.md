# Feature Landscape

**Domain:** Conversational memory (multi-turn chat with query rewriting) for a local, plain-Python, per-owner RAG system over uploaded PDFs
**Researched:** 2026-10-21
**Overall confidence:** MEDIUM. The rewrite-before-retrieval pattern is cross-checked (LlamaIndex and LangChain docs agree). Product UX claims (ChatGPT, NotebookLM, Copilot) come from single help-page or forum snippets and are LOW; where a claim rests on general product knowledge with no source it is tagged "training knowledge" (LOW). The requirements mapping (R1-R10) is HIGH: it is read directly from `.planning/PROJECT.md`.

## How to read the "R1-R10" column

- **Covered** = a requirement in `PROJECT.md` already says to build it.
- **Gap** = not in R1-R10 and I recommend adding it (or an explicit decision).
- **Deferred** = `PROJECT.md` Out of Scope names it as a later item.
- **Omit** = recommended as an anti-feature; do not build.

## Table Stakes

Features users of any chat-with-your-documents tool expect. Missing = the chat feels broken or unsafe.

| Feature | Why Expected | Complexity | R1-R10 | Notes |
|---------|--------------|------------|--------|-------|
| Follow-up with a pronoun retrieves the right passages (rewrite to a standalone question before retrieval) | The standard pattern in LlamaIndex (`condense_question`, `condense_plus_context`) and LangChain (`create_history_aware_retriever`): condense history plus latest message into a standalone question, retrieve on that, answer from the passages. Without it, "what is its population?" searches for the pronoun. (MEDIUM, two docs agree) | Med | Covered: R3 | Both frameworks tell the model to reformulate, not answer, and to return the message unchanged if it is already standalone; that is the R3 "skip when standalone" rule. LlamaIndex also ships a `skip_condense` flag, so a bypass switch is normal. |
| Skip the rewrite when the message is standalone | Frameworks return the question unchanged; a needless rewrite costs a model call and can distort the question | Low | Covered: R3 ("cheap check first, model second") | Cheap check = first turn of a conversation (no history) always skips, which is also the byte-identical single-turn guarantee. |
| Conversation id that survives the round trip; new one created when absent | Every chat product has a thread/session; API equivalents (OpenAI Assistants threads, Griptape threads, Portkey threads) are id-addressed | Low | Covered: R1 | Validate the id's shape like `DOC_ID` (`^[0-9a-f]{12}$`) before it becomes a path; an unknown id and another owner's id must both be 404 with the same body so existence does not leak. R1 names only the other-owner case. |
| History stored server-side, per owner | Products keep history on the server; a client-sent history is user-controlled | Med | Covered: R2, Out of Scope "client-supplied history" | Store the answer "as shown" (after filter), never the raw blocked text. |
| Recent turns in the answer prompt | Coherent answers ("as I said above", "the second one") need the last few turns | Low | Covered: R5 | Single-turn prompt byte-identical to today is the project constraint; the history block is added only when history exists. "Short answers" must be a deterministic truncation (first ~40 words, citations stripped), because compaction (a summariser model) is deferred. |
| "New conversation" button | Universal (ChatGPT "New chat", NotebookLM clear). Users need an escape hatch from a wrong context | Low | Covered: R9 | Client drops the id; the next ask creates a fresh conversation. The old one stays on disk until its document is deleted. |
| History rendered safely in the page | Untrusted text from earlier answers returns to the page | Low | Covered: R6, R9 | `textContent` only. Rendered history must go through the same defanging as live answers. |
| Stored history treated as untrusted | An earlier answer can carry text from a poisoned document and re-enters every later prompt | Med | Covered: R6 | Scan with `scan_text`, defang with `filter_output`-style handling before reuse. Do not store a prior blocked answer's raw text. |
| Conversation ends when its document is deleted | The project's stated privacy rule: derived text must not outlive the document. ChatGPT, by comparison, removes a deleted chat from view at once and purges within 30 days (LOW, single help page) | Med | Covered: R2 | Single-document: `data/uploads/<doc_id>/chat/` goes with the folder. Cross-document is the hard case; see "Decisions the requirements do not yet make". |
| A hard cap with a clear message when it is hit | Copilot ("this conversation has reached its limit, start a new chat") and ChatGPT ("maximum length for this conversation") do exactly this. Users complain when it arrives with no warning (LOW, forum threads) | Low-Med | Partly: R7 sets the cap but not what the user sees | See "History length limits" below. Refuse the turn with a specific status and a message, do not silently drop history. |
| History survives a page reload | Every chat product auto-saves; NotebookLM made auto-saved history a headline feature in Dec 2025 (LOW, news snippets) | Low | Gap | R9 says the page "keeps the conversation id across questions" but not across a reload. Cheapest: id in `sessionStorage` plus `GET /v1/conversations/{id}` returning the stored turns. Without it, the server-side history is unreachable after F5. |
| Citations kept with each stored turn | A rehydrated answer that says `[S 2]` with no source list is useless; all chat-with-documents tools keep the source link with the answer | Low | Gap | R2 lists message, rewrite, answer, scope, timestamp. Add the per-turn citation list (document, PDF page, chunk id), not the passage text. |
| Per-conversation write safety | Two tabs or a double submit append to one conversation | Low | Gap | A per-conversation lock (same style as the service locks) and "store the turn only after the final event". An aborted stream stores nothing, so history never holds a half answer. |

## Differentiators

Not expected by users; valued, and several fit this project's "traceable, measured" identity.

| Feature | Value Proposition | Complexity | R1-R10 | Notes |
|---------|-------------------|------------|--------|-------|
| Visible rewritten question | The user and the developer can see what was actually searched. Most products hide it (Open WebUI shows follow-up suggestion chips, not the rewrite; training knowledge says Perplexity and ChatGPT search show only the generated search queries). Directly serves "every answer traceable to the stage" | Low | Partly: R3 records both texts in the trace; the page display is not required | Put `rewritten_question` in the response and show it in the existing "What the pipeline saw" panel, not in the chat bubble. Render with `textContent` (it is model output built from untrusted history). |
| Clarifying question on genuine ambiguity | Research says LLMs recognise ambiguity but rarely ask (arXiv 2605.25284: "Knowing but Not Showing"; retrieved context makes it worse; arXiv 2605.25831: default behaviour is to answer, not clarify) (LOW, abstracts only). Most commercial tools guess. A correct, rare clarification is a real differentiator | High | Covered: R4, R9 | Hard part is the threshold, not the UI. Ask only when two readings are "equally plausible"; one question per turn; never two clarifications in a row (force a best-effort answer on the second). The clarification is an ordinary assistant turn stored with a kind marker, skips retrieval and generation, and the user's next message is rewritten against it. A retrieval-coherence signal (do the top hits of the two readings point at the same pages?) is a researched alternative to a pure prompt decision (Arabzadeh et al., CIKM 2022), but is a later experiment. |
| Topic-switch detection that cleans the rewrite history | TopiOCQA's own statistics show topic switching is normal: about 13 turns and 4 topics per conversation (LOW, dataset paper snippets). Leaking an old topic into a new question is a named failure mode | Med | Covered: R4 | Most explicit switches ("Now tell me about Berlin") are already standalone, so the R3 skip handles them for free. Detection matters for the ambiguous middle ("and the other one?"). Cheapest design: the rewriter returns a structured result (`standalone_question`, `ambiguous`, `topic_switch`), one call, no separate classifier. Tension to resolve: after a switch the rewrite history is clean, but R5 still puts the last N turns in the answer prompt. Decide whether the prompt history is also cut at the switch (recommended: yes, same boundary). |
| Rewrite on/off measured on a multi-turn golden set, with an oracle | The project rule is "add a stage only when measurement shows a gain". Public sets (QReCC, TopiOCQA, ChatRAG-Bench) all pair conversations with human standalone rewrites, which is the pattern to copy | Med | Covered: R8 | Add a third arm: a hand-written standalone question per follow-up (oracle). Raw vs rewritten vs oracle shows the ceiling and tells you whether a gap is rewriter quality or retrieval. Score retrieval on page hits (hit@5, MRR), answers with the per-question fact checklist; never the holistic correctness judge. Noise warning: one turn is about 2.7 points on 37 questions; a multi-turn set with 10 to 15 follow-up turns has a noise band far above 8 points, so the "gain outside the noise band" test may never fire. Either write at least about 30 follow-up turns or report paired per-turn wins/losses and keep the default off. |
| Failure-mode tests named in the requirements | Invented details, dropped constraints, wrong pronoun, topic leakage are the standard rewrite failures | Med | Covered: R4 | Each becomes one golden entry with an expected rewrite property. Cheap to check by string (constraint words must survive). |
| Explicit "memory window" indicator | Silent history loss is what users dislike in long chats (ChatGPT/Copilot reports). Showing "using your last 6 turns" or a turn counter near the cap makes the hard cap legible | Low | Gap (nice to have) | Return `turn_count` and `turns_remaining` in the response; the page shows a small line. Reuses the same numbers the cap needs. |
| Explicit delete of one conversation | ChatGPT and NotebookLM both offer "delete chat" / "delete chat history" in the UI; for this project it is the user-facing half of the privacy rule | Low | Gap | R2 only removes history through a document delete. `DELETE /v1/conversations/{id}`, owner-filtered, 404 for others, removes one file. |
| Conversation list / resume sidebar | ChatGPT, Claude, Copilot and NotebookLM all have one (NotebookLM keeps it per notebook) | Med | Gap, recommended Defer | Needs a listing endpoint, a title, ordering and cross-document handling. Single-owner learning project: ship reload-resume and delete first; list when there is more than one live conversation per document. |
| Auto-generated conversation titles | Polish in every sidebar product | Med | Omit for now | Needs a model call whose input is document-derived text. Use the first user message, truncated, as the title if a list is ever built. |

## Anti-Features

Deliberately NOT built in this milestone.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Client-supplied history in the request | User-controlled, bypasses the scan and the owner filter | Client sends only the new message and the conversation id (already Out of Scope) |
| Always-on rewriting | Costs a model call per turn and can distort standalone questions; the project ships it only if measured | Skip rule plus a config switch; default decided by R8 numbers |
| Silent truncation of old turns | Users believe the system remembers; answers drift without a signal | Hard cap with an explicit message (above). The fixed prompt window (last N turns) is a documented design choice, not a hidden failure, and the page says so |
| Rolling summary / structured memory / vector memory over history | Compaction needs a summariser and its own evaluation (probe questions at turn 5, 20, 50) | Deferred to a later phase; this milestone enforces the hard cap |
| Cross-conversation user memory (ChatGPT-style "memory" across chats) | Retains user text beyond any document, breaks "delete the document, delete the text" | None; each conversation is self-contained |
| Multi-round clarification dialogues, clarification buttons or chips | More UI and state for a rare case; invites interrogation | One clarifying question per turn, then answer best-effort |
| Suggested follow-up question chips (Open WebUI has this) | Another model call, and generated text drawn from documents | None |
| Edit-and-regenerate, branching conversations | Turns the append-only history into a tree; breaks the simple "last N turns" rule | New conversation |
| Export and share conversation | Moves document text out of the deletable folder | None |
| Caching rewrites or answers through the LLM disk cache for uploads | A delete would not remove the cached text | `get_llm(spec, cache_dir=None)` for the rewriter too |
| Letting the rewritten question edit or replace the stored user message | The audit trail must show what the user typed | Store both texts (R2/R3) |
| Search across all conversations, per-turn feedback buttons, voice | Not part of the milestone goal | Later backlog |

## Specific questions from the brief

### Conversation listing and resume
Commercial products always list and resume. For this milestone: persist the id for the browser session, rehydrate with a single-conversation GET, and defer the list. R1-R10 give the id but no way to read a conversation back, so this is the largest functional gap.

### "New conversation"
Covered by R9. Behaviour to specify: it clears the page log and id only; it does not delete the old conversation (that is the separate delete action). Also decide scope binding: a conversation is tied to the document scope it started with, and changing the scope selector on the page should start a new conversation, otherwise history from document A feeds retrieval over document B.

### Visible rewritten query
Recommended as a low-cost differentiator in the pipeline panel (see table). Not in R1-R10 as a UI item, only as a trace field.

### Clarifying questions
Covered by R4 and R9; high complexity because of the decision threshold, not the rendering. Evaluate with the "ambiguous follow-up" golden entry and also include a "looks ambiguous but is not" entry so the system is penalised for over-asking.

### Topic switch handling
Covered by R4. See the structured-rewriter design and the open tension with R5.

### History length limits and what the user sees at the cap
R7 sets a hard cap on turns and words and says nothing about the user's view. Recommendation (a requirement to add):
1. Two separate numbers: the prompt window (last N turns, N=6 to start) and the conversation cap (total stored turns or words). The window slides by design; the cap ends the conversation.
2. At the cap, the ask returns a distinct client error (not a 5xx) with a plain message ("This conversation is full. Start a new conversation.") and the page shows it as an assistant turn plus a highlighted "new conversation" button. Do not drop turns silently, do not run retrieval.
3. A turn counter or a warning a few turns before the cap, because the main complaint in ChatGPT and Copilot threads is a cutoff with no warning (LOW).
4. The cap budget must include history, passages (1500 words), and the answer budget with the reasoning model's 3000 thinking tokens (`docs/models.md`), as R7 states.

### Deleting a conversation
Document delete removing history is covered (R2). An explicit single-conversation delete is not in R1-R10 and is cheap; recommend adding it. For multi-document conversations see below.

### How history is shown in the UI
Vertical log of user and assistant bubbles (every product). Keep: citations with PDF page numbers per assistant turn, the clarifying question as an ordinary assistant turn (R9), blocked answers shown as the replacement text, all via `textContent`. Add: the rewritten question in the pipeline panel only.

## Decisions the requirements do not yet make

| Question | Why it matters | Recommendation |
|----------|----------------|----------------|
| Cross-document conversation storage (open question 1 in `PROJECT.md`) | The page's multi-document mode is where follow-ups are most natural; refusing history there leaves the feature absent in that mode. Cross-document asks are not traced today, so no retention rule exists to reuse | Store under a per-owner folder with the `doc_ids` list; delete a conversation when any referenced document is deleted. Simple, conservative, and keeps "delete the document, delete the text". If that is too much for the first phase, refuse history for cross-document scope with a clear message rather than ignoring the id |
| Unknown vs foreign conversation id | Both should be 404, identical response | Add to R1 acceptance |
| Rewriter model (open question 2) | Reasoning generator is slow to first token and the rewrite sits in front of it | Prefer the local instruction model for the rewrite; measure latency and rewrite quality in R8. Not decidable from feature research |
| Rewrite fails (model server down) | R3 says errors surface as HTTP statuses before any SSE byte | Keep that, do not fall back silently to the raw message; a silent fallback hides the exact failure being measured |
| Turn stored when the answer was abstained, blocked, or the stream was cancelled | History content drives later prompts | Store abstentions and the replaced text of blocked answers as shown; store nothing for cancelled or errored turns |

## Feature Dependencies

```
R1 conversation id + owner check
   -> R2 server-side history store (deletable location)
        -> R6 scan/defang on read (history is untrusted)
        -> R3 rewrite (needs history)
             -> R4 clarify / topic switch (rewriter output fields)
             -> R8 multi-turn golden set + on/off experiment
        -> R5 history block in prompt (needs history, needs R6)
        -> R7 hard cap (needs turn and word counts from R2)
             -> cap-hit message (Gap)
        -> GET one conversation (Gap) -> page reload resume
             -> conversation delete (Gap) -> conversation list (Defer)
R9 page: id kept + new conversation + history render (needs R1, GET, R6)
R10 docs: after R8 numbers exist
Cross-document storage decision -> R2 for multi-document scope
```

## MVP Recommendation

Prioritise:
1. R1 + R2 + R6: id, deletable per-owner store, untrusted-history handling. Everything else depends on it, and it carries the security conventions.
2. R3 rewrite with the skip rule, trace of both texts, plus R5 history block with single-turn prompt byte-identical (regression test against the golden prompts).
3. R7 hard cap with a user-visible message, and R9 page changes including reload-resume (small GET) and the pipeline-panel display of the rewritten question.
4. R8 multi-turn golden set with an oracle arm, then decide the default. Place R4 clarification and topic switch before R8 so the golden entries for them exist, but keep each as a switchable stage so a bad measurement can turn it off.

Defer (named in Out of Scope): compaction (rolling summary at about 70% of the history budget), cost and token totals per request, tracing (Langfuse or LangSmith), tool calling, Keycloak. Also defer from this research: conversation list sidebar, auto titles, suggested follow-ups, export.

Add to the requirement set (small): explicit conversation delete, GET one conversation, per-turn citations, cap-hit message and counter, per-conversation lock, scope-change starts a new conversation, 404 for an unknown id.

## Sources

- LlamaIndex Condense Plus Context Chat Engine reference and example: https://developers.llamaindex.ai/python/framework-api-reference/chat_engines/condense_plus_context/ , https://developers.llamaindex.ai/python/examples/chat_engine/chat_engine_condense_plus_context/ (MEDIUM, cross-checked with LangChain)
- LangChain "Add chat history" / `create_history_aware_retriever`: https://python.langchain.com/docs/use_cases/question_answering/chat_history (MEDIUM)
- Open WebUI follow-up prompts (suggestion chips, not rewriting): https://docs.openwebui.com/features/chat-conversations/chat-features/follow-up-prompts (LOW)
- NotebookLM chat history help page and rollout coverage: https://support.google.com/notebooklm/answer/16179559?hl=en , https://alternativeto.net/news/2025/12/notebooklm-chat-history-now-live-for-all-users-on-mobile-and-web (LOW)
- OpenAI help, deleting and archiving chats: https://help.openai.com/en/articles/8809935-deleting-and-archiving-chats-in-chatgpt (LOW)
- Conversation-limit UX complaints (Copilot, ChatGPT forum threads): https://techcommunity.microsoft.com/discussions/microsoft-copilot/sorry-this-conversation-has-reached-its-limit-lets-start-a-new-chat-/4137520/replies/4494087 , https://community.openai.com/t/chat-limit-exceed-too-early/1402023 (LOW)
- TopiOCQA: https://ar5iv.labs.arxiv.org/html/2110.00768 ; QReCC / question rewriting: https://arxiv.org/pdf/2010.04898 ; ChatRAG-Bench: https://huggingface.co/datasets/nvidia/ChatRAG-Bench/blob/main/README.md (LOW to MEDIUM; dataset statistics disagree between sources)
- Clarifying vs answering: https://arxiv.org/pdf/2605.25284 , https://www.alphaxiv.org/abs/2605.25831 , survey https://arxiv.org/html/2505.12543v2 (LOW, abstracts only)
- Project documents: `.planning/PROJECT.md`, `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/CONCERNS.md`, `interview/05_conversation_memory_and_cost.md`, `docs/backlog.md` (HIGH)
- Not found: AnythingLLM thread behaviour and Perplexity thread behaviour could not be confirmed by search; statements about them in this file are absent by design.
