# Chat memory: what is left, and who does what

Written 2026-10-26 for someone who has not followed the work. Everything here is about the chat-memory change in pull request #5
(branch `flow/chat-memory-pr`). The full history of the build is on branch `flow/chat-memory`.

## 1. What was built, in three lines

- The chat can now remember a conversation: you ask a follow-up ("why does it write twice?") and the answer uses the earlier turns.
  The API takes an optional `conversation_id`; the server keeps the history; deleting a document deletes its conversations.
- A "rewriter" step can turn a follow-up into a stand-alone question before searching. It is built but **switched off** by default
  (`RAG_REWRITE`), because the measurement did not prove it helps (see Task C and the table below).
- A question asked without a conversation behaves exactly as before. A test pins that, byte for byte.

## 2. What is left

None of these blocks merging pull request #5. Items 2, 3 and 6 are needed only before the rewriter can be switched on.

| # | Item | In one sentence | Who | When |
|---|------|-----------------|-----|------|
| 1 | Model server down | Done: the server was back on 2026-10-26 and `max_model_len` was read (131072). | Your team (the GPU machine) | done |
| 2 | Review 34 test rows | The 34 multi-turn test conversations were drafted by an AI agent; a person must check them. See Task A. | You, or someone you hand it to | any time |
| 3 | Over-rewriting | The rewriter changes questions that did not need changing. See section 3. | Claude, as a small separate task | after item 2 |
| 4 | Measurements | Done 2026-10-26 (runs p6-qwen, p6-gptoss; `docs/chat_memory_eval.md`). Still ships off: failed c, f. Repeat after item 2. See Task C. | Claude | done; repeat after item 2 |
| 5 | Flaky test | One test fails now and then when the machine is busy. See section 3. | Nobody now | only if it fails twice in a row |
| 6 | Browser check of the page | Nobody has tried the new chat page in a real browser. See Task B. | You, or someone you hand it to | after item 1 |

Smaller leftovers: `max_model_len` was read on 2026-10-26 as 131072 and is now in the code (`docs/models.md`),
14 minor code-review notes are written in `.planning/runs/20261021-1840-chat-memory/review-1.txt` on branch `flow/chat-memory`,
`HANDOFF.md` is from 2026-10-13 and out of date, and the Gemini key is still marked for rotation.

## 3. The words, plainly

**Rewriter.** A small step that runs before the search. If you ask "why does it write twice?" after a question about B-trees, the
rewriter produces "Why does a B-tree write each piece of data to disk more than once?" and the search uses that. It is a language
model call (a local model, `qwen2.5:7b` through Ollama). It is not a person and not the main answer model.

**Over-rewriting.** The rewriter should leave a question alone when it already stands on its own. The check: take 37 normal questions
(`data/golden/ddia_questions.jsonl`, unchanged), put ONE unrelated earlier turn in front of each, and see what the rewriter does.
It should change none of them. It changed 17 of 37, and for 6 of them the top-5 search results changed (q002, q008, q015, q020, q031,
q033). That means that if the rewriter were switched on, it would sometimes damage a perfectly good question. The saved result is in
`runs/conversation/p4-regression/report.json` (a local, git-ignored folder), block `regression_unrelated`. Nothing is wrong with the
37 questions; the rewriter is the thing to fix. **What is expected:** later, a small task makes the rewriter skip standalone questions,
and the same check is rerun until it changes none (or almost none). It needs only the local Ollama model, not the GPU server.

**Flaky test.** `test_a_delete_during_a_load_leaves_nothing_in_the_store[one document]` in `tests/test_api.py` (line 809). It checks that
deleting a document while its text is being loaded leaves nothing behind. It is an older test (from the earlier review-fix work). It
failed once or twice when several test runs shared the machine, and passed when rerun. It never failed in the final checks of the
merged branch (939 passed, 2 skipped). **Action:** none now. If it fails in a run, rerun it once. If it fails twice in a row, it is a
real bug and Claude should be asked to fix it.

## Task A: review the 34 test conversations (about 2 to 3 hours; can be split)

**What these are.** `data/golden/ddia_conversations.jsonl` has 34 lines, one conversation each (ids c001 to c034). Each is a short
chat: an earlier turn (a question and a short answer), then a follow-up `message`. Each also has the stand-alone question the
follow-up means (`standalone`), the book pages that answer it (`gold_pages`), and the facts a good answer must state (`key_facts`).
They are used to measure whether the rewriter helps. They were drafted by an AI agent, so every row says `"review": "pending-human"`.

**Why a person must check.** The measurement is only fair if the rows read like a real person's conversation and are true to the book.
Until every row is `approved`, the shipping rule keeps the rewriter off.

**For each row, in the file or in `data/golden/MULTITURN_REVIEW.md` (table of ids and kinds):**

1. Read `turns`. Is the earlier answer true according to the book? (PDF page = printed page + 22. `gold_pages` are PDF pages: c001's
   page 106 is printed page 84.)
2. Read `message`. Would a real reader say this after that earlier turn? It should lean on the earlier turn ("it", "that", "the
   second one") and not make sense alone.
3. Read `standalone`. Is this exactly what the message means, written so it makes sense on its own? Most rows are fine; fix only wrong ones.
4. Open the book at `gold_pages`. Does the answer to `standalone` really sit there? Do the `key_facts` appear on those pages?
5. If everything is right, change `"review": "pending-human"` to `"review": "approved"`. If something is wrong, fix the text
   (the fields above, `gold_pages` or `key_facts`), then approve it.

**Four row kinds need one extra look:**
- `ambiguous_follow_up` (c005, c006, c027, c028): the message is meant to be unclear between two things from the earlier turn. Check it
  really is, and that `must_contain` lists those two things (the clarifying question should name both). `standalone` is `null` here, on purpose.
- `oracle-miss` rows (c003, c015, c022, c023): even the stand-alone question does not find its page in the search. Most likely
  `gold_pages` points at the wrong page, or the stand-alone wording is poor. Check the page and fix whichever is wrong.
- `standalone_in_conversation` (8 rows): the follow-up is already a full question; it must NOT depend on the earlier turn. Check that.
- `topic_switch` (6 rows): the follow-up changes subject; the earlier turn should be about something unrelated.

**One rule that protects the result:** change a row only because it is wrong or unrealistic. Do not reword a row to make the
rewriter look better or worse.

**Finish:**
1. Make sure no row says `pending-human`: `grep -c pending-human data/golden/ddia_conversations.jsonl` should print `0`.
2. If you changed any text, check that the file still loads: `python -m rag.experiments.conversation --check-set --name p4-check-set-2`
   (needs the local models, not the GPU server; it prints the number of rows where the stand-alone question finds its page and where it does not).
3. Commit the file and tell Claude. Claude then repeats the scored run (Task C) on the approved rows.

**Handing it to someone:** give them this section, the file `data/golden/ddia_conversations.jsonl`, and the DDIA PDF. They can take id
ranges (for example c001 to c017 and c018 to c034) and each edit only their own lines.

## Task B: try the new chat page in a real browser (about 20 minutes; needs the model server)

**What this is.** The page code changed (`rag/api/static/index.html`). Automated tests exercise it against a fake page, but nobody has
seen it in a real browser. Follow-ups also need the answer model, so do this after the GPU server is back.

**Set up:**
1. Make sure OpenSearch is running, then start the API: `RAG_STORE=opensearch python -m uvicorn rag.api.main:app --port 18642`
2. Open http://127.0.0.1:18642 and upload or pick a document that is already `ready`.
3. To see the conversation id: browser developer tools, Network tab, click an "ask" request, look for `conversation_id` in the
   request and in the response.

**The nine checks (expected result after each):**
1. Ask a question, then a follow-up. The follow-up request carries the same `conversation_id` as the first answer's response.
2. Click **New conversation**. The chat log empties; the next question is sent with no `conversation_id`.
3. Change which documents you are asking about (tick or untick a box, or switch the document under "this document"). The id resets
   and the next question starts a fresh conversation. Clicking a row under "all documents" does NOT reset it.
4. Delete the document you were asking about. The id resets.
5. Stale id: after an answer, delete that conversation's file (`data/uploads/<doc id>/chat/conversations/<id>.json`; for an
   all-documents conversation, under `data/uploads/_conversations/`), then ask a follow-up. The page shows a short notice, asks once more
   without the old id, and you get an answer.
6. Clarifying question (needs `RAG_REWRITE=1` set when starting the API, and the local Ollama model): after a topic, send a vague
   follow-up such as "How does it handle a node that goes down?". If the page shows a clarifying question, it appears as plain text with
   its label. Tags such as `<b>x</b>` must show literally, not as bold text.
7. Ask a long question, click **New conversation** while the answer is still streaming. The stream stops, and the old id does not come back.
8. Busy: send two questions in the same conversation almost at once. The second one shows a readable sentence (not a raw error code).
   (The "conversation full" case needs 50 turns; skip it.)
9. Look at the New conversation button in the light and dark themes, and at a 900 px wide window. It matches the other buttons and the
   row does not wrap.

**If a check does not behave as written:** note the number, what you did, and what you saw (a screenshot helps), and give it to Claude.
Write "skipped" for any check you cannot set up; that is fine.

## Task C: what Claude does once the model server is back (no work for you)

Done on 2026-10-26 for steps 1 to 3 below, on the rows still pending review; repeat step 2 and 3 after Task A.

1. Read the real `max_model_len` (`docs/models.md`, section "Context window") and replace the 8192 floor in `docs/models.md` and
   `MODEL_CONTEXT_TOKENS` in `rag/query/history.py`.
2. Run the answer-quality half and the gpt-oss comparison:
   `python -m rag.experiments.conversation --repeats 3 --answers --name <new>` and
   `REMOTE_REASONING_EFFORT=low python -m rag.experiments.conversation --rewriter vllm:/models/gpt-oss-20b --arms off,on --name <new-gptoss>`,
   then `python -m rag.experiments.conversation --results runs/conversation/<new> --compare runs/conversation/<new-gptoss>`.
3. Append the results to `docs/chat_memory_eval.md` and decide again, by the rule written there, whether the rewriter ships on.
