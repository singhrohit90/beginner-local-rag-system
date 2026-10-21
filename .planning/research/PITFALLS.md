# Pitfalls Research

**Domain:** Conversational memory and query rewriting added to an existing single-turn, plain-Python, guarded RAG system (FastAPI + SSE, reasoning generator behind a tunnel, local judge, per-owner deletable storage)
**Researched:** 2026-10-21
**Confidence:** HIGH for pitfalls derived from this codebase (read: `rag/api/main.py` 300-410, `rag/api/service.py` 340-524, `rag/query/generate.py`, `rag/query/guard.py`, the `.planning/codebase/` maps, `interview/05_conversation_memory_and_cost.md`). MEDIUM for general conversational-RAG failure modes (literature and practitioner reports, secondary sources). LOW where marked (hardware contention, model behaviour not measured here).

**Unverified by design:** the LLM provider module and its disk-cache key were not read (project rule: a hook flags that file). Every claim about the cache key below is a thing to test, not a fact.

**Phase labels used below** (match the expected roadmap; one change proposed in "Pitfall-to-Phase Mapping"):
- **P1** History store + conversation id on the API
- **P2** Rewrite step + history in the prompt + budget (+ clarifying path)
- **P3** Evaluation / multi-turn golden set
- **P4** Page + docs

---

## Critical Pitfalls

### Pitfall 1: The "additive" change quietly alters the single-turn prompt or call pattern

**What goes wrong:**
`build_prompts` (`rag/query/generate.py:51`) has three branches (`spotlight`, `naive`, `standard`). A new `history` argument gets threaded into one branch and not the others, or an empty history still emits a header ("Conversation so far: (none)"), a blank line, or a trailing newline. Separately, the first turn of a new conversation still calls the rewriter (a wasted model call that can also distort the question). Either way the golden results and the LLM cache (keyed on the prompt) silently stop matching the numbers recorded in `CLAUDE.md`.

**Why it happens:**
The byte-identity rule is easy to state and easy to break by one character. The retrieval invariant (hit@5 0.865, mrr 0.663) only proves retrieval is unchanged, not the prompt. Prompt text is built by string concatenation in `rag/query/prompt.py` (`build_user_prompt`) and `rag/security/defenses.py` (`spotlight_user_prompt`), two places that both need the same rule.

**How to avoid:**
- Add the history as a separate prefix block built by one function (for example `build_history_block(turns) -> str`) that returns `""` for `None` or `[]`, and compose `block + existing_user_prompt` only when non-empty. Never edit `build_user_prompt` itself.
- Snapshot test: for 10+ golden questions and a fixed list of `Hit`s, assert `build_prompts(q, ctx)` equals a string literal captured BEFORE the change (commit the snapshot first, in P1). Run it for `standard`, `spotlight` and `naive`, with `history=None` and `history=[]`.
- Add the "history is data" instruction (Pitfall 4) as an addendum appended only when history is present, the way `SPOTLIGHT_ADDENDUM` is appended to the base prompt, never by editing `SYSTEM_PROMPT` / `DOCUMENT_SYSTEM_PROMPT`.
- Call-count test with `FakeLLM`: a first-turn message (no history) makes exactly the same model calls as today (zero rewrite calls, one answer call).
- Re-run `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` at the end of P1 and P2 (expect 0.865 / 0.663).

**Warning signs:** snapshot test missing; `history` default is `[]` shared across calls (mutable default); a golden run after the change shows a different cache hit rate; a trace for a first turn has a `rewrite` entry.

**Phase to address:** P1 (commit the snapshot), P2 (enforce it).

---

### Pitfall 2: The rewriter invents details, drops a constraint, resolves the wrong entity, or drags in an old topic

**What goes wrong:**
The project's four named failure modes, plus the fifth that actually dominates in practice: **over-rewriting a question that was already standalone** ("What is replication?" after a Kafka discussion becomes "What is replication in Kafka?"). A wrong rewrite is invisible: retrieval finds confident, well-cited, wrong passages, so it looks like a good answer.

**Why it happens:**
LLM rewriters are trained to be helpful and add context. A 7B instruction model (`ollama:qwen2.5:7b`, the likely rewriter) is weaker at "return unchanged". "Most recently mentioned entity" is the default heuristic and is wrong whenever the user means the earlier one. Constraints ("only before 2020", "in the second book", "without Raft") are the first thing a paraphrase drops. Broad benchmarks (CORAL, MTRAG) name topic shift and context drift as the open problems, and no benchmark scores over-rewriting directly, so you will have to build that check yourself.

**How to avoid:**
Do not rely on the prompt alone. Put cheap deterministic gates around the model output in `rag/query/rewrite.py`, each unit-testable with `FakeLLM` returning a deliberately bad rewrite:
1. **Skip gate before any model call.** Rewrite only when the message shows a dependency marker: pronoun/demonstrative (it, its, they, that, this, those), ellipsis (no verb, under about 5 words), a leading conjunction ("and", "also", "what about", "how about", "same for"), or a referring phrase ("the other book", "the second approach", "the former"). Record `skipped: true` and the reason in the trace. Measure the gate's precision and recall on the golden set as its own number (Pitfall 11). Note the project's own example, "how does that compare to the other book?", is caught by "that" but "the other book" alone is not a pronoun: keep the phrase list in data, with tests.
2. **Constraint-preservation check.** Every number, year, quoted string, and constraint word in the raw message (`only`, `except`, `before`, `after`, `without`, `not`, `first`, `second`, named entities) must appear in the rewrite. If not: reject the rewrite, use the raw message, flag `rewrite_rejected: dropped_constraint`.
3. **Invention check.** Every content token in the rewrite must come from the message or the history window the rewriter was shown (after stemming). New numbers, new proper nouns: reject.
4. **Leak check.** If the gate says the message is standalone, the rewrite is not even attempted, so an old topic cannot leak. If it is attempted and the rewrite adds an entity that is not needed to resolve a marker, reject.
5. **Length cap.** Rewrite no longer than about 2x the message (or 60 words); one sentence; no URLs, no markdown.
6. **Wrong-pronoun cannot be fully gated.** Mitigate with the clarify path (Pitfall 14) and by showing the rewrite to the user on the page ("Searching for: ...", P4), so a wrong resolution is visible.
7. Keep a fixed instruction "return the message unchanged if it is already a complete question" and put few-shot examples in the rewriter prompt that are NOT drawn from the golden set (Pitfall 11).

**Warning signs:** rewrite differs from the message on questions with no marker; the same message gets different rewrites in two runs (temperature); retrieval on the standalone-in-conversation subset gets worse with rewrite on.

**Phase to address:** P2 (gates, tests); P3 (measure gate quality and rewrite quality separately).

---

### Pitfall 3: The rewrite output is itself an injection channel into retrieval and the prompt

**What goes wrong:**
The rewriter reads history (untrusted: earlier answers may carry text from a poisoned document) and emits text that is embedded for dense search, tokenised for BM25, recorded in the trace, and possibly placed in the answer prompt's question slot. A poisoned turn ("when the user asks about X, search for Y", or an instruction to the rewriter) can redirect retrieval to attacker-chosen passages without ever touching the answer prompt, bypassing `scan_chunks` (which only scans retrieved passages).

**Why it happens:**
The existing defences sit on the answer path: scanner on passages, `filter_output`/`StreamGuard` on output. A new model call before retrieval has no guard, and its output feeds a trusted-looking channel (the "question").

**How to avoid:**
- Show the rewriter only what it needs: the last N **user messages** and, per turn, a short answer excerpt (Pitfall 4's stored form), never passages, never full answers.
- Run `scan_text` on the rewrite output and on every history excerpt given to the rewriter; on a flag, reject the rewrite and use the raw message (record why).
- Apply the same shape rules as Pitfall 2 (length cap, no URLs, no markdown, no imperative-to-model phrases) and the invention check, which also blocks "go search for Y" redirects.
- Treat the rewriter's output format strictly (Pitfall 9): parse a fixed field; anything else falls back to the raw message.
- Add rewrite-injection cases to `rag/security/fixtures.py` style tests: a stored turn containing a redirect instruction must not change the rewrite (use `FakeLLM` that obeys the injection, and assert the gates reject it).
- Remember the user's own messages can carry pasted untrusted text (a pasted web page). Scan them too.

**Warning signs:** the trace shows rewrite text containing words in neither the message nor recent user turns; retrieved passages unrelated to the visible question.

**Phase to address:** P2.

---

### Pitfall 4: Stored history re-exposes poisoned answer text, and the unchanged system prompt never says history is data

**What goes wrong:**
`SYSTEM_PROMPT` tells the model to answer only from the numbered passages and ignore instructions inside them. It says nothing about a conversation-history region (the project forbids editing it). An earlier answer that carried injected text now sits in the user prompt of every later turn, outside the region the model was told to distrust. Memory-poisoning research (persistent "sleeper" instructions in stored memory, secondary sources below) shows persistence is what makes this worse than a one-shot injection. There is also a quieter bug: earlier answers contain `[S1]`-style citation labels that referred to the PREVIOUS turn's passages; in the new prompt `[S1]` means the new passage 1, the model may copy them, and `citation_is_valid` still passes because the numbers are in range, so citations are silently wrong.

**Why it happens:** history looks like the app's own output, so it is not treated as input. Citation labels are local to one prompt.

**How to avoid:**
- Store the answer **as shown** (`trace.answer` after `filter_output`), never `StreamGuard.full_text` (that includes unreleased or blocked text). For a blocked answer store the `BLOCKED` notice, not the raw text.
- Build the history block from a **defanged short form**: strip `[S n]` markers (or replace with "(sources omitted)"), strip URLs, markdown links/images and HTML (run the same renderer-view normalisation used in `rag/query/guard.py`, `_as_a_renderer_reads_it`), cap each answer to a sentence budget (Pitfall 12 on how long), and run `scan_text` on each turn. A flagged turn is replaced by a fixed placeholder ("[earlier answer withheld]"), not dropped, so the turn count and pronoun structure stay coherent.
- Add the history-is-data addendum to the system prompt only when history is present (Pitfall 1).
- Keep the history block in the user prompt after a fixed delimiter, with the passages and question after it, so the structure is stable.
- Do NOT add history text to `context_text` passed to `filter_output` / `StreamGuard` (the URL allow-list). Keeping it out means a URL that appears only in history still counts as "not in context" and is blocked.
- Consider adding the addendum's key phrase to `_PROMPT_ECHO` in `rag/query/guard.py`; check that doing so does not change any `tests/test_stream_guard.py` case (run it; the 270 cases are the safety net).
- Render history on the page with `textContent` (already the rule; add a test or manual browser check since the page has no automated test).

**Warning signs:** a poisoned-fixture run (`python -m rag.security.indirect`) with a second turn shows the canary or an attacker URL appearing in turn 2; answers cite `[S4]` when only 3 passages exist or cite the wrong passage.

**Phase to address:** P1 (what is stored: shown form only), P2 (what is put in the prompt: defanging, addendum, citation stripping).

---

### Pitfall 5: Conversation ids leak across owners, scopes, or by enumeration

**What goes wrong:**
(a) The lookup reads a file by id without the owner in the key, so another owner's id works. (b) "Exists but not yours" returns a different status or message than "does not exist", which is an enumeration oracle. (c) The id becomes a path and `../` or an odd `owner` string escapes the folder. (d) A client-supplied unknown id is created on demand (squatting, and an id existence oracle). (e) A conversation started on document A is accepted on `/v1/ask` over document B, and A's text enters B's prompt.

**Why it happens:**
`current_owner()` returns the constant `LOCAL_OWNER` today, so a missing owner key passes every test until Keycloak arrives (`docs/auth_plan.md`). Document ids are validated by `DOC_ID = ^[0-9a-f]{12}$` before they become a path; conversation ids need the same discipline. If owner becomes a Keycloak subject, using it raw in a path is a traversal and collision risk.

**How to avoid:**
- Generate ids server-side with `secrets.token_hex(16)` (128 bits; the 12-hex document id is 48 bits and not enough for an unguessable capability), validate with a strict regex BEFORE any path join, and never list conversations (no `GET /v1/conversations`).
- Resolve ownership through the existing document check: single-document conversations live under `self._dir(doc_id)` after `self.get(doc_id, owner)` has already raised `NotFound` for a foreign document. For cross-document conversations use `data/conversations/<hash(owner)>/<conv_id>.jsonl` (hash or encode the owner; do not trust its characters), and filter by owner inside the store function, not after reading.
- Return the **same** 404 with the **same** body (`"no such conversation"`) for unknown id, foreign id, malformed id, and wrong-scope id. Unknown client-supplied ids are never created: absent id creates, present id must already exist.
- Bind a conversation to its scope at creation (the document id set). A request with a different scope returns the same 404 (or starts a new conversation explicitly). Note `doc_ids: null` means "every ready document you own", which changes when the owner uploads another document, so store the resolved ids and treat a change as a scope mismatch.
- Never read the owner from the body or a header (project rule); take `owner` from `Depends(current_owner)` and pass it down, as the document routes do.
- Tests (pattern: override `current_owner` as in `tests/test_api.py`): second owner gets 404 for owner one's id on all four ask routes; unknown id and foreign id produce byte-identical responses; id `../x` and a 200-char id give 404, not 500; wrong-scope id gives 404.

**Warning signs:** a conversation helper whose signature has no `owner`; a test that only asserts the 404 status but not that the bodies are equal.

**Phase to address:** P1.

---

### Pitfall 6: A document delete leaves conversation text behind (or resurrects the folder)

**What goes wrong:**
Five ways the retention rule breaks:
1. **Cross-document history** stored outside any document folder survives the delete of one of its documents, and still holds paraphrases of the deleted document's text.
2. **Late writer**: a stream is in flight, the user deletes the document, `_remove_tree` removes `data/uploads/<doc_id>/`, then the turn is appended with `mkdir(parents=True)` and the deleted document's folder reappears holding conversation text. The existing code anticipates this for traces (`except (NotFound, FileNotFoundError): pass` around `trace.save`); a new history writer that creates directories will not.
3. **Scope change** (Pitfall 5e) mixes A's text into a conversation that outlives A.
4. **Rewrite and clarification model calls** go through the LLM disk cache (Pitfall 7).
5. **Side copies**: debug logs of the rewriter prompt, the trace `config`, experiment runs under `runs/`.

**Why it happens:** deletion was designed around one folder per document; conversations are a second kind of derived data with a different lifetime.

**How to avoid:**
- Single-document conversations: write only into an **existing** `data/uploads/<doc_id>/chat/` folder; no `parents=True`; if the folder is missing at write time, drop the write silently like the trace path does. Better, take the document's `_load_lock`/`_deleting` check before writing, in the same order `delete` uses (the codebase warns that changing lock order reintroduces the delete/load race).
- Cross-document conversations (open question 1 in `PROJECT.md`): my recommendation is to **refuse history for cross-document scope in P1** (new conversation per request, no storage) unless the owner explicitly wants it, because it is the only case that cannot be deleted by removing one folder. If it is built: each turn records its `doc_ids`; `DocumentService.delete` removes every cross-document conversation whose any turn touched that document (delete the whole conversation, not scrub lines), and a test proves it.
- Keep the answer text out of every shared place: no `logger` call with message/rewrite/history text (the current `logger.exception("ask failed for %s", what)` logs only the label; keep it that way).
- Test: ask in a conversation, delete the document, assert the whole tree is gone and a following request with the old id gives the standard 404. Add the race test with an `Event`: start a stream, delete mid-stream, finish the stream, assert `data/uploads/<doc_id>` does not exist.
- Keep conversation files out of the folder that trace consumers glob: `rag/observe/retrieval_quality/run_eval.py:65` globs `*.json` in a trace dir. Use `chat/conversations/<id>.jsonl` (subfolder and a different suffix) so a conversation is never parsed as a trace.

**Warning signs:** `Path.mkdir(parents=True, exist_ok=True)` anywhere in the history writer; a conversation location not under `data/uploads/<doc_id>/` with no delete hook.

**Phase to address:** P1 (storage location and delete hook); re-verify in P2 when the rewrite call is added.

---

### Pitfall 7: The LLM disk cache holds upload-derived text, or the cache key ignores history

**What goes wrong:**
Two opposite failures:
- **Leak:** the new rewriter (and the clarifier) is a **new model object**, built with `get_llm(spec)` and the default `cache_dir`. Its cached outputs are paraphrases of the user's uploaded-document conversation and survive a delete. The project rule (`get_llm(spec, cache_dir=None)` for uploads) is applied by the existing code to the answer LLM only.
- **Collision:** a hand-written memo for the rewrite keyed on the message alone, or an answer cache that does not see history, returns the same rewrite/answer for "what about its population?" in two different conversations. Also an experiment cache keyed by golden question id does not distinguish rewrite on from rewrite off.

**Why it happens:** new component, new construction site, no one remembers the rule; or a cache key is chosen for convenience.

**How to avoid:**
- Build the rewriter model in `build_default_service` (`rag/api/main.py`) with `cache_dir=None` for the product path, and write a service-level test that wraps `get_llm` with a spy and asserts every LLM constructed for the service has `cache_dir=None`.
- For golden-set experiments on the DDIA book (non-upload, caching allowed and useful for reproducibility): the rewrite cache key must include (rewriter model spec, rewriter prompt version string, the exact message, the exact history window text, max tokens, temperature). Test: same message with two different histories produces two cache entries; changing the prompt version produces a new entry.
- The answer cache is keyed by the full prompt, so history that is in the prompt separates entries automatically. History used only by the rewriter changes the rewritten question, which changes the prompt, which also separates entries: verify with a test that two conversations ending in the same literal message but different histories do not return each other's cached answer.
- A cached rewrite freezes ONE sample at temperature above 0, so "rewrite on vs off" compares a single draw. Use temperature 0 (and verify the provider honours it) so the cache means something.

**Warning signs:** a second `get_llm(` call in `rag/api/` or `rag/query/rewrite.py` without `cache_dir=None`; a files-under-cache-dir check after an upload conversation shows new entries.

**Phase to address:** P2 (construction and keys); P3 (experiment keys).

---

### Pitfall 8: Two requests on one conversation corrupt or reorder the history

**What goes wrong:**
Double-click on Send, two browser tabs, or a retry after a timeout puts two requests on the same conversation. With a read-modify-write of one JSON file the second write erases the first turn (lost update). With append-only JSONL the turns interleave in completion order, not question order; or request B reads history that lacks request A's still-streaming turn, so "and its population?" is rewritten against the wrong last turn. On Windows an open file also makes `os.replace` / delete raise `PermissionError` (the existing `_remove_tree` retries for this reason).

**Why it happens:** the service is a threadpool (`run_in_threadpool`, `iterate_in_threadpool`), streaming holds a request open for seconds (4.4 s to first token was measured), and a single local user makes concurrency feel impossible.

**How to avoid:**
- One lock per `(owner, conversation_id)`, taken by the request for its **whole** lifetime including streaming, and released in a `finally` that also runs on client disconnect (the same place `events.close()` runs; `_close_when_idle` waits for a running generator). A second request on a busy conversation gets **409 before any SSE byte** (it fits `guarded(...)`, which already maps `BadUpload` to 409). Prefer reject over queue: a queued request waits behind a slow reasoning generation and looks hung.
- Do not keep the lock in a module-level dict that grows forever: key it by conversation id and drop it when idle (or use one `threading.Lock` map guarded by a lock, with removal at release).
- Persist **one atomic append per completed turn** (a single `write()` of one JSON line under the lock), with a monotonically increasing `turn` number read under the lock. Readers tolerate a truncated final line (crash mid-write) by skipping it.
- Make the trace/query id unique per request (the current `query_id` is `<doc>-<ms timestamp>`; two requests within the same millisecond collide, and a trace file named by it could be overwritten; add a counter or random suffix if the trace filename derives from it, to be checked in `rag/common/trace.py`).
- Test with an `Event` (never a sleep): request A blocked inside a scripted `FakeLLM` stream, request B on the same conversation gets 409, A finishes, history has exactly one turn; client disconnect in A releases the lock.

**Warning signs:** `json.load` then `json.dump` of the whole conversation per turn; no `finally` around lock release; a test that uses `time.sleep` to order requests.

**Phase to address:** P1 (store + lock), P2 (lock held across rewrite and streaming).

---

### Pitfall 9: Errors, the rewrite call and the clarifying path break the "HTTP status before any SSE byte" contract

**What goes wrong:**
- The rewrite is a model call. If it runs inside the generator (after `StreamingResponse` is created) a rewriter failure becomes an `error` SSE event instead of a 502, and the page cannot tell it from a mid-answer failure.
- A conversation id lookup or a busy-lock check done lazily inside the stream becomes a 200 with an error frame instead of 404/409.
- The clarifying path skips retrieval, but `DocumentService._describe` reads `trace.stage("context").hits` unconditionally (`rag/api/service.py:470`); with no retrieval stage that raises, and the failure shows up as a stream `error` after the user already waited.
- The rewriter returns prose, a markdown fence, or two candidates instead of the expected single field; the parser throws, or worse, passes the whole blob to retrieval.
- A turn is persisted in `finally`, so a client disconnect or model failure saves a partial answer, which then becomes "what the assistant said" in later prompts. The `replace: true` case (guard blocked after text was sent) is stored as the unredacted text.

**How to avoid:**
- Do all of this inside `DocumentService._retrieve` / `ask_documents_stream` before `rag.stream(trace)` returns (that is exactly where the existing comment says NotFound/BadUpload/retrieval failures are raised): conversation lookup, lock acquisition, history load, skip-gate, rewrite call, clarify decision. Only then does `stream_request` create the `StreamingResponse`.
- Introduce a typed exception for the new cases (for example `ConversationNotFound` mapped to the same 404 as `NotFound`, `ConversationBusy` mapped to 409) and map them in `guarded`.
- Make the clarifying turn flow through the **same** event contract the page already handles: optional `token` events, one `final` with `answer` = the question, `passages: []`, `citations: []`, `clarifying: true`, `abstained: false`. Give `_describe` a branch (or build the clarifying response in one place) so no code reads `trace.stage("context")` when none exists. Run the clarifying text through `filter_output` as well: it is model text containing entities taken from untrusted history.
- Parse the rewriter reply with a strict, tiny grammar (one JSON object or one tagged line). On any parse failure: use the raw message, set `rewrite: "failed:<reason>"` in the trace and the response. On a transport failure (tunnel/Ollama down): decide once and document it. My recommendation: degrade to the raw message AND surface a visible `rewrite: "unavailable"` flag on the response and page (silent degradation hides the loss of memory; hard failure makes the chat unusable whenever the second model is down). Count these in experiments as failures, never as "off".
- Persist the turn only when the `final` event is produced and the answer was not cut: persist from the code path that builds `final`, not from a `finally`. Persist the post-filter text; when `replace` is true persist `final["answer"]`.
- Tests: rewriter raises -> response is the documented behaviour with a status code, not a 200 SSE with an error frame; unknown conversation -> 404 with no body bytes of `text/event-stream`; disconnect mid-stream -> history unchanged; guard-blocked stream -> stored text is the BLOCKED notice.

**Warning signs:** `yield` appears before the rewrite call in any new code; `_describe` unchanged after adding a no-retrieval path; `try/finally` containing `history.append`.

**Phase to address:** P2 (ordering, parser, clarify response shape); P1 (typed exceptions and the status mapping).

---

### Pitfall 10: Evaluation cannot distinguish a real gain from noise

**What goes wrong:**
The decision rule in `PROJECT.md` ("ship only if the gain is outside the noise band") is applied to a number that cannot carry it:
- The documented 8-point band belongs to the **37-question single-turn answer score**. A multi-turn set will have far fewer items per category; at 20 follow-ups one question is 5 points, so any band must be recomputed from n.
- The judge is noisy (7B local model, 89 percent faithfulness calibration, false "unfaithful" marks), so answer-level on/off differences are mostly judge variance.
- The rewriter is stochastic; one run per arm compares two samples.
- The history the second turn sees is the **model's own previous answer**, which differs between the on and off runs, so the arms differ in more than the rewrite (error propagation: a turn-1 failure changes turn 2).
- Averages hide regressions: a rewrite that helps pronoun follow-ups and hurts standalone questions can net out to "no change".
- The threshold is chosen after seeing the numbers.

**How to avoid:**
- **Primary metric: retrieval on the rewritten query** (hit@5 and mrr from `rag/observe/retrieval_quality/metrics.py`). It is deterministic given the rewrite and has no judge in it. Report answer quality as secondary, informational only.
- **Teacher-forced histories:** each golden conversation stores fixed prior turns (including the prior assistant answer text). Both arms receive identical history, so the only difference is the rewrite. Run a small separate end-to-end live run for realism, never for the decision.
- **Three arms, not two:** rewrite off (floor), rewrite on, and **oracle** = the human-written standalone question stored in the golden item (ceiling). Report "fraction of the oracle gap closed". An off arm that already equals the oracle means the item cannot discriminate (Pitfall 11).
- **Paired reporting:** list per-item win/tie/loss between arms. State the shipping rule before running (for example: net wins of at least N on the follow-up subset AND no losses on the standalone-in-conversation subset AND skipped-gate accuracy at least X). Record the rule in the experiment README before the first run.
- **Determinism:** temperature 0, fixed seeds where the provider supports it, repeat 3 times and report instability separately, rewrite cache keyed per Pitfall 7.
- **Regression arm:** replay the 37 existing answerable single-turn questions inside a fake conversation with 1-2 irrelevant prior turns. Rewrite must be (near) a no-op and hit@5 must stay 0.865 on the non-skipped path; report how many were altered. This is the "over-rewriting" detector.
- **Per-category tables** (pronoun, topic switch, ambiguous, standalone-in-conversation, constraint-bearing), never only a total.
- If the result is inside the band: ship **off** and record the numbers (the stated rule), not "on, probably helps".

**Warning signs:** one number in the report; the same arm labels used for different histories; threshold appears in the commit after the run.

**Phase to address:** P3 (design the harness before the rewriter prompt is tuned; see mapping).

---

### Pitfall 11: Multi-turn golden-set design mistakes

**What goes wrong:**
- Items the baseline already passes (the follow-up message still contains the topical word, so BM25 finds it): the set cannot show a gain. A wrong "no difference" conclusion.
- Pronoun items with a single candidate entity; no item where the wrong-but-recent entity is the trap.
- Gold labels written for the raw follow-up instead of the standalone intent; or gold pages that mix printed and PDF page numbers (project rule: PDF pages, for DDIA printed + 22).
- Ambiguous items scored with retrieval metrics (the correct behaviour is a clarifying question, there is nothing to retrieve).
- Topic-switch items scored only by hit@5, which hides the leak (the passages can be right while the rewrite carries an old topic).
- Rewriter few-shot examples copied from the golden set (contamination), or the set written by an LLM and never reviewed (the existing set already carries agent-written key facts, see `data/golden/KEY_FACTS_REVIEW.md`).
- The judge sees the raw follow-up ("what about its population?") and cannot resolve it.
- A single book (DDIA): "topic switches" are between nearby topics (replication to partitioning), so embedding similarity gives weak signal, and any pass here does not predict a cross-book scenario ("compare to the other book").

**How to avoid:**
- Each item stores: `turns` (fixed prior user and assistant text), `message`, `standalone` (human-written), `gold_pages` for the standalone, `category`, `must_contain` (constraint terms that the rewrite must keep), `must_not_contain` (terms from an earlier topic that must not appear), `expect: rewrite | skip | clarify`. `must_contain`/`must_not_contain`/`expect` give mechanical, judge-free checks for dropped constraint, leak, over-rewrite, and clarify behaviour.
- Include distractor-entity items (the right entity is not the most recent), constraint items, items whose antecedent is two turns back, items with a clarification reply ("the first one"), items with a document-name reference, and standalone-in-conversation items.
- Baseline check before committing an item: if rewrite-off already gets hit@5 for it, label it `control`, keep it for the regression arm, and make sure at least half the follow-up items are baseline misses.
- Score clarify items by: did it ask (yes/no), did it name both candidates; and for every non-ambiguous item, the false-clarify rate.
- Give the judge the human `standalone` question, not the raw follow-up.
- Rewriter prompt examples are hand-written fresh; keep a note of which questions were used.
- Human-review every item (the author is not the rewriter); write a `data/golden/MULTITURN_REVIEW.md` like the existing review files. Mind that `data/golden/` is committed.

**Warning signs:** most items have `off` hit@5 equal to the oracle; only one category has more than a handful of items; a gold page that is a printed number.

**Phase to address:** P3, with item authoring started at the beginning of P2 (before the rewriter prompt is tuned).

---

### Pitfall 12: History budget overflow and silent truncation

**What goes wrong:**
- The budget counts **words** (R7, `select_context` 1500-word cap) but the model counts tokens. DDIA code blocks, numbers and identifiers tokenise far worse than prose, so a window that "fits" in words overflows in tokens. The server returns a context-length error that surfaces as a 502 with a confusing message (`guarded` maps any exception to 502).
- Reasoning-model output budget: the 3000 hidden thinking tokens plus the answer must fit after the prompt. More history means more to think about and more truncated answers. The project already had to add a retry for truncated answers (commit `4fc6186`), which doubles latency for those turns. (Hypothesis: history raises the truncation rate. Measure it.)
- Dropping the oldest turn silently can delete the very antecedent of the pronoun ("it" meant the thing from turn 1): the rewriter now resolves to the wrong entity or leaves the pronoun, and nothing records it.
- "Short answers" cut mid-list drop the referent for "the second approach".
- Per-message cap is 2000 chars (`AskRequest.question`), so 6 turns of maximum-length messages alone are 12,000 chars before answers.
- A hard cap on conversation length that just refuses without telling the user, or a conversation file that grows without bound and is fully re-read each request.

**How to avoid:**
- Compute the budget in tokens with an explicit safety factor: `window - system - 1500-word passages (converted at a conservative ratio, say words*2 for code-heavy text) - 3000 thinking - answer max - margin`. Take the window from `docs/models.md` / the server config, not from memory (not verified here), and put it in `rag/common/config.py`-style constants with a comment on its source.
- Separate three limits and name them: (1) **window** of turns put into prompt/rewriter (N=6 is a starting guess, to be set by P3), (2) **per-turn caps** (user message already 2000 chars; stored answer excerpt about 300 characters for old turns, longer, for example about 120 words, for the LAST assistant turn because it holds the likely referent), (3) **conversation cap** (max stored turns, max file size) enforced at write time.
- On overflow, choose an explicit policy and tell the user: when the cap is reached return a clear 409/422 ("conversation is full, start a new one") **before** any SSE byte, or trim in a defined order and record `history_turns_dropped` in the trace and the response so the page can say "older turns not used". Never trim silently.
- Test with a deliberately oversized history and `FakeLLM` that records the prompt: the built prompt stays under the configured token budget for the worst case (max-length messages, code-like text), and the trace shows what was dropped.
- Keep the first user message of a conversation (often defines the topic) pinned if you trim, or document that you do not.
- Measure real prompt tokens from `trace.config["usage"]["prompt_tokens"]` in the first live run and compare with the estimate.

**Warning signs:** budget code that uses `len(text.split())` only; no test that drives the prompt to the limit; an intermittent 502 "context length" error in long chats.

**Phase to address:** P2 (budget, caps, drop reporting); P1 (storage cap).

---

### Pitfall 13: The rewrite call before retrieval makes every follow-up feel slow, and may contend for the GPU

**What goes wrong:**
Time to first token is already about 4.4 s on the reasoning generator (measured, `docs/models.md`). A rewrite on the same reasoning model adds its own thinking tokens before retrieval starts, and nothing can stream until retrieval has finished (the HTTP-status contract, Pitfall 9). The page shows nothing for the whole interval. If the rewriter is the local `qwen2.5:7b` it shares an 8 GB GPU with the embedder (the codebase serialises ingestion for exactly this reason) and Ollama may swap models in and out, which adds seconds per cold call (LOW confidence: contention not measured in this repo).

**How to avoid:**
- The skip gate (Pitfall 2) means most standalone messages and all first turns pay zero extra latency; keep it deterministic and cheap.
- Rewriter model: do not use the reasoning generator (hidden thinking, slow first token, token budget can be consumed before any visible rewrite appears, giving an empty string that looks like "no rewrite"). Use the fast instruction model with a small `max_output_tokens` (for example 80-100), temperature 0, and a timeout. Treat an empty or truncated rewrite as a **failure** (Pitfall 9), not as an unchanged question.
- Record a `rewrite` timing in the trace (`elapsed_ms`, skipped or not) so the cost is measured, not guessed. Follow the trace convention carefully: stages hold hits, so put rewrite details in `trace.config["rewrite"]` rather than a hit-less stage that `run_eval` consumers might iterate.
- The page should show a client-side "working on it" state immediately on Send (before the first byte) and, on arrival, the text "Searching for: <rewrite>" from the `final` event or a header.
- Measure p50/p95 added latency in P3 on both skipped and rewritten follow-ups. If Ollama is cold, set a keep-alive on the rewrite model.

**Warning signs:** rewriter spec equals the generator spec; no timing in the trace; user-visible blank for 8+ seconds on a follow-up.

**Phase to address:** P2 (model choice, limits, timing); P4 (page state).

---

### Pitfall 14: Clarifying questions loop, over-fire, are scored as abstentions, or lose the original question

**What goes wrong:**
- The rewriter asks "Do you mean A or B?", the user answers "the first one", and that reply is itself a non-standalone message; if the stored history treats the clarification as an ordinary assistant turn the rewriter sees "the first one" with no pending question, and the loop repeats or the rewrite is nonsense.
- A 7B model either never asks or asks about every pronoun; both look fine in a demo.
- A clarifying turn (no passages, no citations) matches `looks_like_abstention` patterns, or reaches `citation_is_valid` with zero passages, and pollutes abstention metrics in `rag/experiments/answer.py`.
- The clarification text is model-written from untrusted history and is shown without a filter.

**How to avoid:**
- Persist a clarifying turn with `kind: "clarify"` and the original unresolved message. The next turn's rewrite gets `[original message] + [clarifying question] + [reply]` as one unit.
- Limit to **one** clarification per original message: if the previous turn was a clarification, the rewriter must produce a standalone question (best guess, flagged) rather than ask again.
- Ask only when the rewriter returns two named candidates present in recent history (validated by the invention check: both candidates must appear in the history window), so a vague "can you clarify?" is not accepted.
- Set `abstained: false`, `clarifying: true`; exclude clarify turns from abstention metrics and from "answer" scoring; score them separately (Pitfall 11).
- Pass the clarifying text through `filter_output` (Pitfall 9).
- Page: render it as an ordinary assistant turn (R9), with the original question remembered by the server, not re-sent by the client.

**Warning signs:** a golden item for the clarification reply does not exist; two consecutive clarify turns in a test conversation.

**Phase to address:** P2 (behaviour), P3 (scoring), P4 (display).

---

## Moderate Pitfalls

### Pitfall 15: Topic-switch detection by embedding similarity throws away the history it needs
**What goes wrong:** Short follow-ups ("and its population?") embed far from the previous question and are classified as topic switches, so history is dropped exactly when needed; "Now tell me about Berlin" embeds close to "capital of France" and is not.
**Prevention:** do not gate history on embedding (mpnet, 384-token limit) similarity. Let the skip gate and the rewriter's "unchanged" output handle standalone messages; add the leak check (Pitfall 2) as the safety net. Treat "topic switch" as an evaluation category with `must_not_contain` terms, and decide whether to implement explicit detection only if P3 shows leakage.
**Phase:** P2 design, P3 measure.

### Pitfall 16: The answer prompt's "Question" slot: rewritten or original?
**What goes wrong:** If the rewritten question replaces the user's message in the answer prompt, a wrong rewrite makes the answer confidently wrong with no trace of intent; if the original is used with a history block, the passages (retrieved on the rewrite) and the question can disagree.
**Prevention:** decide once and record it in `PROJECT.md` Key Decisions. My lean: the answer prompt shows the original message plus the history block, passages come from the rewrite, and both texts are in the trace and response so the page can display "Searching for: ...". Test both on the multi-turn set in P3 before locking it.
**Phase:** P2 decision, P3 verify.

### Pitfall 17: Other paths silently ignore or mishandle the conversation id
**What goes wrong:** `style=spotlight` or `naive` branches omit history; `/v1/ask-about` ignores `conversation_id` while the page's "about the documents" option appears to be inside the conversation; the non-stream and stream routes diverge (they share `_retrieve` today, but any history logic added to only one route breaks `test_the_streamed_response_equals_the_ordinary_one`).
**Prevention:** put all conversation logic in `DocumentService._retrieve` (the single shared point before generation); a parametrized test over all four ask routes and both configs; for `ask-about` reject a supplied `conversation_id` with 422 or document that it is stateless, and have the page start a separate state for that mode.
**Phase:** P1/P2, P4 page.

### Pitfall 18: Document names and metadata are untrusted input to the rewriter
**What goes wrong:** To resolve "the other book" the rewriter needs document names, which come from upload file names (attacker-controlled when a file arrives from elsewhere) and enter a prompt.
**Prevention:** pass short sanitised labels (D1, D2 plus a name truncated and passed through `scan_text`), as `rag/query/about.py` does with labels; map the label back server-side.
**Phase:** P2.

### Pitfall 19: Windows file-handling in the history store
**What goes wrong:** `os.replace` / rename on a file another thread has open raises `PermissionError`; a crash leaves a half-written last line; a trailing partial line breaks `json.loads` for the whole conversation, so the user loses a long conversation to one bad line.
**Prevention:** JSONL append under the conversation lock, reader skips an unparseable final line and logs a count (no content), tests that write a truncated line and read it back. If a rewrite-in-place is ever needed, use the same write-temp-then-replace helper `DocumentService` already uses for `status.json`, with its retry.
**Phase:** P1.

### Pitfall 20: The rewriter reply is trusted as a format
**What goes wrong:** A 7B model returns "Sure! Here is the rewritten question: ..." or two lines or a code fence, and the whole text is embedded and BM25-tokenised.
**Prevention:** a strict single-field parse with fallback (Pitfall 9); test with `FakeLLM` outputs for each malformed shape.
**Phase:** P2.

---

## Minor Pitfalls

### Pitfall 21: Trace changes break consumers
**What goes wrong:** adding keys is fine, but `trace.stage("context")` assumptions and any consumer iterating stages break on new shapes; `run_eval` reads a trace dir by glob.
**Prevention:** additive keys under `trace.config["rewrite"]` / `["history"]`; keep `chat/` free of non-trace JSON (Pitfall 6).
**Phase:** P1/P2.

### Pitfall 22: N=6 and the 70 percent compaction idea carried over unexamined
**What goes wrong:** the starting value of N is treated as a decision; compaction thresholds from the interview note are copied into code before there is any hard cap behaviour to measure.
**Prevention:** N is a config constant with the experiment that sets it recorded; compaction stays out of this milestone (stated out of scope).
**Phase:** P2/P3.

### Pitfall 23: Interview notes relabelled "built" before it is measured
**What goes wrong:** `interview/05_conversation_memory_and_cost.md` says "Be honest about status"; flipping labels with the code merge, before the multi-turn numbers exist, makes the notes overclaim.
**Prevention:** relabel only what is built **and** measured (R10); cite the real run folder and numbers, as the project rule requires.
**Phase:** P4.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Store the full previous answers and trim at prompt time | Simplest write path | Re-exposes poisoned text; large files; citation-label confusion | Never for the prompt form; storing the as-shown answer in the file is fine (it is what the user saw) |
| One JSON file per conversation, rewritten each turn | Easy to read | Lost updates, Windows `PermissionError`, whole-file corruption | Never; use JSONL append under a lock |
| Rewrite always on, no skip gate | No gate code to write | Extra call on every turn, over-rewriting of standalone questions, latency | Only in an experiment arm, never as the shipped default |
| Ship rewriter on by default "because it demos well" | Nicer demo | Breaks the project's rule (add a stage only on measured gain) | Never; ship off with numbers if the gain is inside the noise |
| Judge-only multi-turn evaluation | Reuses existing scripts | Judge noise swamps the effect at small n | Only as a secondary column |
| Live generated histories in the on/off experiment | Realistic | Arms differ in more than the rewrite; error cascades | Only in a separate small realism run |
| Skip the delete race test | Saves an `Event`-based test | A deleted document's folder resurrects with conversation text | Never |
| Store the history in the cross-document trace folder rule that does not yet exist | Avoids deciding | No retention or delete story | Never; refuse history for cross-document scope in the first phase |
| Reuse the answer LLM object for the rewrite | One model to configure | Reasoning-model latency and empty rewrites; shared cache behaviour | Only if measured to be fast enough; still needs `cache_dir=None` for uploads |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| vLLM generator (tunnel, reasoning) | Rewrite or clarify call with a small token limit gets only hidden thinking and an empty visible text; long history triggers a context-length error shown as 502 | Use the instruction model for the rewrite; budget tokens including 3000 thinking; test the overflow path; treat empty output as failure |
| Ollama `qwen2.5:7b` as rewriter | Assume it is always up and fast; cold model load seconds; same GPU as the embedder | Timeout, keep-alive, visible `rewrite: unavailable` fallback flag, trace timing |
| FastAPI request model | New `conversation_id` field added to `AskRequest` but not to `AskAcrossRequest` (they are separate models, `rag/api/main.py:123-135`) or length/format unchecked | Add to all four routes' models via the shared base; validate with a strict pattern; test all four |
| SSE `final` event | Conversation id only in `final`, so an aborted stream never tells the client the id of a new conversation (orphaned conversation next time) | Also return it in a response header set before the first byte (the id is created before streaming starts) |
| `StreamGuard` | Feeding the clarifying question or a stored answer through the stream path differently from model answers; adding history text to the URL allow-list | Same `filter_output` for every outgoing assistant text; allow-list = passages only |
| OpenSearch / `Scope` | Using the store to find "similar earlier turns" (vector memory) without the owner filter inside the query | Out of scope this milestone; if ever built, filter in the query by `Scope.owner` |
| `get_llm(..., cache_dir=None)` | Applied to the answer LLM only | Spy test over every LLM the service builds |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Rewrite on every turn, on the reasoning model | Blank page for 8-15 s on follow-ups | Skip gate; fast model; short max tokens | From turn 2 on every conversation |
| Whole conversation file read and parsed per request | Slows with conversation length | Window read from the file tail; conversation cap | A few hundred turns (hit by hand-testing only) |
| History grows the prompt, which grows thinking, which truncates answers and triggers the retry | Occasional doubled latency, "cut off" answers | Token budget with margin; measure `usage` | Around turn 5-8 with code-heavy answers (unmeasured) |
| Per-conversation lock dict never cleaned | Slow memory growth | Remove entries at release | Long-running server |
| Fixed sleeps in new concurrency tests | Flaky under parallel agents | `Event` or polling with 30 s ceiling (project rule) | Immediately on a busy machine |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Conversation lookup without owner in the key | Cross-owner read once real authentication exists | Owner in the path or the query; same 404 for every miss (Pitfall 5) |
| Different error text for foreign vs unknown id | Enumeration oracle | Identical status and body; ids 128-bit random; no list route |
| Client-chosen conversation id accepted if unknown | Squatting, probing | Only server-generated ids; unknown id is 404 |
| History inserted into the prompt without the "history is data" instruction | Persistent injection from an earlier poisoned answer (memory-poisoning class of attack) | Addendum only when history present; defang; scan; short excerpts (Pitfall 4) |
| Rewriter output trusted | Retrieval redirected by a poisoned turn | Gates, `scan_text`, invention check, strict parse (Pitfall 3) |
| Storing raw streamed text | Blocked or unreleased text kept and replayed | Store the checked, as-shown text only |
| Rendering history or the "Searching for" line with `innerHTML` | XSS from stored model text | `textContent` only (project rule), manual browser check since the page is untested |
| Logging prompts, rewrites or histories | Document text outside its folder, survives delete | No content in logs; counts and ids only |
| Owner value used raw in a path | Traversal or collision when Keycloak subjects arrive | Hash or encode the owner for any path component |
| Conversation in `runs/` or experiment output | Upload text leaves the document folder | Experiments use DDIA only; the experiment code refuses upload documents |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Stale conversation id after a delete or a server restart gives 404 and the page keeps retrying with it or silently starts a new one | User believes memory exists; answer ignores context without any sign | On 404 for a conversation id, clear the id, show a one-line notice ("that conversation no longer exists, started a new one"), and re-send only if the user confirms or clearly show the retry used no history |
| "New conversation" clicked while a stream is running; the old `final` event arrives and re-sets the id | The old conversation is silently resurrected | Tag each request with a token/AbortController; ignore events for a superseded request; abort the old stream |
| First request fails (502) after creating a conversation; page never learns the id | Orphan conversation; next question starts fresh | Return the id in a response header; keep the id on failure |
| Changing the document selection keeps the same conversation id | A's text goes into a prompt about B (Pitfall 5e) | Changing selection starts a new conversation (or asks) |
| Rewrite invisible | Wrong pronoun resolution looks like a wrong answer | Show "Searching for: ..." from the response |
| Clarifying question shown as an error or empty answer card | Looks like a failure | Ordinary assistant turn (R9), no passage panel |
| Silent truncation of history | Answers drift on long chats | Notice when older turns are not used; clear message at the cap |
| About-the-documents toggle inside a conversation | Looks conversational, is stateless | Label it or reset conversation state for that mode |
| Id kept only in a JS variable | Page reload loses the conversation though the server still has it | Decide: keep in `sessionStorage` per selection, or accept and say so; either way test reload after delete |

## "Looks Done But Isn't" Checklist

- [ ] **Byte-identical single turn:** snapshot test of `build_prompts` for `standard`, `spotlight`, `naive` with `history=None` and `[]` exists and was committed BEFORE the change; retrieval invariant 0.865 / 0.663 re-run.
- [ ] **Zero extra model calls on turn 1:** `FakeLLM` call-count test.
- [ ] **Owner isolation:** foreign id gives 404 on all four ask routes with a body identical to an unknown id; malformed ids give 404, not 500; wrong-scope id gives 404.
- [ ] **Delete:** after delete the tree is gone, including after a stream that was in flight; no `mkdir(parents=True)` in the history writer; cross-document conversations either refused or purged.
- [ ] **No upload-derived disk cache:** spy test over every `get_llm` the service builds; cache dir has no new files after an upload conversation.
- [ ] **Cache key:** same message with two histories produces different rewrite and answer entries.
- [ ] **Errors before bytes:** rewriter down, unknown conversation, busy conversation all return an HTTP status with no `text/event-stream` body.
- [ ] **Clarify path:** returns the normal event contract, passes `filter_output`, does not read `trace.stage("context")`, is not counted as an abstention, at most once in a row.
- [ ] **Persistence:** a disconnect, a model failure and a guard-blocked stream do not store a partial or unredacted answer.
- [ ] **Concurrency:** two requests on one conversation give 409 for the second, turn order stable, lock released on disconnect (Event-based test).
- [ ] **Budget:** worst-case history (max-length messages, code-like text) stays under the token budget in a prompt-capturing test; dropped turns are reported, not silent.
- [ ] **Citations:** history excerpts contain no `[S n]` markers.
- [ ] **Evaluation:** teacher-forced histories, oracle arm, paired win/loss list, per-category table, regression arm on the 37 existing questions, shipping rule written before the run.
- [ ] **Golden set:** each item has `standalone`, PDF gold pages, `category`, `expect`, and constraint/leak term lists; half the follow-ups are baseline misses; human reviewed.
- [ ] **Page:** textContent for every stored string; stale-id and superseded-stream handling checked by hand in a browser (the page has no automated test).
- [ ] **Docs:** `rag/README.md` Step 11, `docs/backlog.md`, `interview/05_...` relabelled only for built and measured items.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Prompt bytes drifted (1) | MEDIUM | `git bisect` with the snapshot test; golden run cache entries from the drifted period are invalid, rerun answers |
| Cache holds upload text (7) | LOW | Delete the cache directory; fix the construction site; add the spy test |
| Conversation text survived a delete (6) | MEDIUM | Find and remove orphan folders (`data/uploads/*` with no `status.json`, conversation dirs with no document); add the race test |
| Rewrite shipped on, later found harmful (10) | LOW | Flip the config default to off; keep stored histories (they stay valid); rerun P3 with the failing items added |
| Corrupted conversation file (8, 19) | LOW | Reader skips the bad line; if unreadable, the conversation 404s and the page starts a new one |
| Golden items found trivially easy (11) | MEDIUM | Re-label as control, author replacements, rerun both arms |
| Context overflow in production use (12) | LOW | Lower N and per-turn caps; add the token margin; no data migration |

## Pitfall-to-Phase Mapping

One proposed change to the expected roadmap: **start authoring the multi-turn golden items and the experiment harness skeleton at the beginning of P2** (and write down the shipping rule), then run the evaluation in P3. Reason: tuning the rewriter prompt before the test set exists means tuning to your own examples (Pitfall 11) and a rewriter that is already "on" in code before any measurement. Ship P2 with the rewrite behind a config flag, default off, and flip it only on the P3 result (this matches the project rule).

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1 Single-turn bytes drift | P1 (snapshot), P2 | Snapshot test, call-count test, retrieval invariant run |
| 2 Rewriter distortions | P2 (gates), P3 (measure) | `FakeLLM` bad-rewrite tests per failure mode; regression arm on the 37 questions |
| 3 Rewrite as injection channel | P2 | Poisoned-turn test with an obedient `FakeLLM`; `scan_text` on rewrite |
| 4 History re-exposes poisoned text; citation labels | P1 (what is stored), P2 (prompt form) | `python -m rag.security.indirect` with a second turn; grep prompt for `[S` in history block |
| 5 Owner and enumeration | P1 | Two-owner tests on all four routes, identical 404 bodies, malformed ids |
| 6 Delete leaves text / resurrects folder | P1; re-verify P2 | Delete test, in-flight stream delete race test (Event), cross-document policy test |
| 7 Cache leak and key collision | P2; P3 for experiment keys | `get_llm` spy; same message / different history test |
| 8 Concurrent requests | P1 (store, lock), P2 (held across streaming) | Event-based 409 test, disconnect releases lock |
| 9 Errors vs SSE contract; clarify response shape | P1 (exceptions), P2 | Status-code tests with no event-stream body; persisted-only-on-final test |
| 10 Evaluation noise | P3 | Written rule, three arms, paired list, repeat runs, per-category table |
| 11 Golden-set design | P3 (author from start of P2) | Review file; baseline-miss share; `must_contain` / `must_not_contain` checks |
| 12 Budget and silent truncation | P2 (P1 storage cap) | Worst-case prompt test; `history_turns_dropped` in trace; first live `usage` vs estimate |
| 13 Latency and GPU contention | P2, P4 | Trace `rewrite` timing; p50/p95 in P3 |
| 14 Clarify loops and scoring | P2, P3, P4 | One-per-message test; separate clarify metrics; page shows ordinary turn |
| 15-20 Moderate | as listed | per-item tests |
| 21-23 Minor | P1/P2/P4 | review |
| UI stale id / superseded stream | P4 (API contract in P1: header id, uniform 404) | Manual browser pass after delete, restart, new-conversation-during-stream |

## Sources

- Codebase (HIGH): `.planning/PROJECT.md`; `.planning/codebase/ARCHITECTURE.md`, `CONCERNS.md`, `TESTING.md`; `interview/05_conversation_memory_and_cost.md`; `rag/query/guard.py`; `rag/query/generate.py`; `rag/api/main.py` (lines 300-410: `guarded`, `stream_request`, ask routes); `rag/api/service.py` (lines 340-524: `delete`, `_retrieve`, `_describe`, `ask_documents_stream`); `docs/models.md` (4.4 s first token, reasoning model); `rag/observe/retrieval_quality/run_eval.py:65` (glob of `*.json` in a trace dir).
- [CORAL: Benchmarking Multi-turn Conversational Retrieval-Augmented Generation (NAACL 2025 Findings)](https://preview.aclanthology.org/new-sigs/2025.findings-naacl.72/) (MEDIUM; topic shifts and citation labelling as open problems)
- [CORAL arXiv 2410.23090](https://www.arxiv.org/pdf/2410.23090) (MEDIUM)
- [arXiv 2603.10524, conversational retrieval via question rewriting, topic switching and context drift](https://arxiv.org/pdf/2603.10524) (MEDIUM, secondary summary; check the paper before quoting)
- [Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection](https://arxiv.org/pdf/2302.12173) (MEDIUM; stored notes re-poison a reset model)
- [Memory Poisoning in AI Agents: Persistent Attacks and Detection](https://www.akto.io/blog/memory-poisoning-ai-agents) (LOW to MEDIUM; vendor blog)
- [Hidden in Memory: Sleeper Memory Poisoning in LLM Agents (ICML 2026)](https://icml.cc/virtual/2026/67842) (MEDIUM; persistence of poisoned memory; OWASP labels for this class disagree across secondary sources, check OWASP directly)
- No source found that scores over-rewriting directly; the checks in Pitfalls 2 and 10 are this document's design, not a published method (LOW; validate in P3).

---
*Pitfalls research for: conversational memory and query rewriting in a local guarded RAG system*
*Researched: 2026-10-21*
