# Conversation memory, compaction, and tracking cost

Three questions that come up often once a RAG chatbot works for a single question: how follow-up questions are understood, how a long conversation is kept inside the model's context, and how token cost and latency are tracked. All three were asked in a real interview.

**Be honest about status in the interview.** In this project the chat is **single-turn**: every question stands alone. Conversation memory and compaction are **not built**. Per-question token counts and stage timings are recorded; cost tracking and a tracing tool (Langfuse or LangSmith) are **not built** and are planned for the next project, after the chatbot works, followed by tool calling. The answers below are the design, with the repo pointers for the parts that exist.

Labels: **Built** (code and tests exist), **Not built** (the design only), **General** (interview knowledge with no code here).

---

## 1. A follow-up question: "What is the capital of France?" then "What is its population?"

**Question.** The user asks "What is the capital of France?", gets an answer, then asks "What is its population?" How does the model know "it" means Paris, or France? And what if the conversation visited other cities in between?

**Short answer.** The model does not know unless you tell it: a language model is stateless, and each call sees only what you send. So the app must send the conversation history. In RAG it matters in two places. The model needs the recent turns to answer. And the **search** needs a self-contained query: "its population" retrieves noise, so before retrieval you rewrite the follow-up using the history into "What is the population of Paris?" (query condensation), and search with that.

**Go deeper.**
- **Two uses of history:** (a) in the answer prompt, the last few turns, so the answer is coherent; (b) in a rewrite step before retrieval, which turns the latest message plus history into one standalone question. Most failures in conversational RAG are retrieval failures from skipping (b).
- **What "it" refers to when other cities came up in between:** the rewriter resolves it from the history, normally to the most recently discussed entity, but this is a guess. Make it safer by: giving the rewriter the last N turns and telling it to keep the user's constraints; instructing it to **ask a clarifying question** when two candidates are equally plausible ("Do you mean Paris or Lyon?") instead of guessing; tracking the current topic or entity explicitly; and detecting a **topic switch** ("Now tell me about Berlin" must not inherit France).
- **Do not rewrite when you do not need to:** if the message is already standalone, skip the rewrite (it costs a model call and can distort the question). A cheap check, or letting the rewriter return the message unchanged, handles this.
- **Failure modes to name:** the rewriter invents details; drops a constraint ("only before 2020"); resolves a pronoun to the wrong entity; or leaks an earlier topic into a new question.
- **Passages for the follow-up:** run retrieval fresh with the rewritten question. You may also keep the previous turn's passages in the prompt if the follow-up is about the same material, which saves a retrieval and keeps the answer consistent.
- **Security:** history is text the system did not write. An earlier answer may contain text copied from a poisoned document, and it comes back in every later prompt. Treat history as untrusted: pass it through the same scanner and defanging as passages, and prefer storing the user's questions and short summaries over full earlier answers.
- **Evaluation:** a multi-turn golden set (a first question, then a follow-up with a pronoun, one with a topic switch, one that is ambiguous). Score retrieval on the rewritten query and the answer on the final turn, and compare with and without rewriting. Add a rewriting step only if it shows a gain.

**In this repo.**
- **Not built.** The ask routes take only the question: `AskRequest` in `rag/api/main.py` has `question`, `config` and `style`. `RetrievalPipeline.run` in `rag/query/pipeline.py` embeds the question string it is given, and the answer prompt (`build_prompts` in `rag/query/generate.py`) holds the question and the passages, never earlier turns. The page keeps a visible log but sends only the new question. So "What is its population?" asked alone would search for those words and get nothing useful.
- Where it would plug in: a new step in `rag/query/` (for example `rewrite.py`) that runs before `RetrievalPipeline.run`, and a conversation id on the API with the history stored per owner so that the owner filter still applies.
- The backlog already says to add query rewriting only if the golden set shows a gain: `docs/backlog.md`, "Query rewriting and intent classification".

**Follow-ups.** Where do you store the history, on the server or in the client? (On the server, per owner; a client-sent history is user-controlled and cannot be trusted.) How does it change caching? (A rewritten standalone query can use the same cache as the same question asked cold.) What if the user changes topic? (Detect it and start with a clean history for the rewrite.)

---

## 2. How do you compact a long conversation?

**Question.** Today the app answers from the current question. When conversation history is added, how do you stop it growing past the model's context window, and what do you lose?

**Short answer.** Set a token budget for history, and when the conversation exceeds it, compact. Keep the most recent turns word for word, replace older turns with a running summary, keep the important facts (goals, constraints, decisions, named entities) in a small separate memory, and drop what can be fetched again, such as the retrieved passages. For very long conversations, retrieve the relevant earlier turns instead of carrying all of them.

**Go deeper.**
- **The budget:** history budget = the model's context window, minus the system prompt, minus the retrieved passages (this app caps them at 1500 words), minus the answer budget (including thinking tokens for a reasoning model). Compact when history passes a threshold, for example 70% of its budget, not at the limit.
- **Strategies, cheapest first:**
  1. **Truncate:** drop the oldest turns. Simple, loses information without warning.
  2. **Sliding window:** keep the last N turns verbatim. Predictable, forgets what was said early.
  3. **Rolling summary:** keep the last N turns plus a summary of everything older, updated as turns age out. The usual choice.
  4. **Structured memory:** keep a short list of facts, such as the user's goal, constraints, decisions and entities, updated each turn. Resists the drift of summaries.
  5. **Retrieval over history:** embed past turns and retrieve those relevant to the new question, as a vector memory. Scales to long sessions, can miss implicit context.
  6. **Drop what can be re-fetched:** old retrieved passages and tool results do not need to stay; keep the question, a short answer and the source references.
- **What to keep and what to drop:** keep goals, constraints, decisions, named entities, open questions, and the sources cited; drop greetings, repeated explanations, and long answer text (keep a one-line version).
- **What you lose:** detail, and exact wording. Summaries drift when summarised repeatedly ("telephone game"), so keep the raw log for audit, summarise from the log and not from the previous summary where you can, and mark the summary with its version. A summary written by a weaker model can state something the user never said.
- **Cost angle (General):** a stable prefix (system prompt, then the summary, then the recent turns) works well with provider prompt caching, so putting the changing parts last cuts cost and latency.
- **Evaluation:** ask probe questions about early facts after compaction ("what budget did I give at the start?") and compare with the full history; measure the tokens saved and the answer quality at turn 5, 20 and 50.

**In this repo.**
- **Not built.** The nearest existing thing is a budget for passages, not for conversation: `ContextConfig.max_words` (1500) and `top_k` in `rag/query/select_context.py` cap how much retrieved text goes into the prompt.
- Because the app is stateless, it can never overflow the context from history; it is the first thing that would change when memory is added.

**Follow-ups.** When do you summarise: on a token threshold or every N turns? (A token threshold; N turns ignores long turns.) Who writes the summary? (A cheaper model, with the raw log kept.) Does a reasoning model change the budget? (Yes: its thinking tokens count against the output limit, see `docs/models.md`.)

---

## 3. How do you track token cost, latency and usage?

**Question.** How would you track token cost and other operational data for an LLM application?

**Short answer.** For every request record the model, the prompt, completion and reasoning tokens, the latency (and time to first token when streaming), the user or session, whether it succeeded, and whether a cache answered. Cost is tokens times the model's price, or for a self-hosted model the GPU time. Aggregate it per user, feature and day, put budgets and alerts on it, and use a tracing tool, Langfuse or LangSmith, that records each request as a trace with a span per step (retrieve, rerank, generate) and shows cost, latency and quality on a dashboard.

**Go deeper.**
- **What to record per request:** model name and version; prompt tokens; completion tokens; reasoning tokens (a reasoning model's hidden thinking is billed as output and is invisible in the text); latency, split by stage; time to first token and tokens per second when streaming; user or owner id and session id; status and error; cache hit; the prompt version.
- **Cost:** hosted models are priced per million input and output tokens, so cost = input tokens x input price + output tokens x output price. A **self-hosted** model has no per-token price: track tokens per second, GPU utilisation and queueing time, and compute an amortised cost per 1,000 tokens.
- **Aggregation and control:** cost per user, per day, per feature; a budget per user or tenant; alerts on spikes; rate limits. Percentiles for latency (p50, p95), not averages.
- **Cost levers:** fewer or shorter retrieved passages (`top_k`, `max_words`), a reranker so fewer passages are sent, a smaller model for easy steps, caching, a cap on output tokens, history compaction, provider prompt caching, batching.
- **Tracing tools (General, check current documentation before quoting):** Langfuse is open source and can be self-hosted; LangSmith is from the LangChain team; others include Helicone, Arize Phoenix, and OpenTelemetry with its generative-AI conventions. They all record nested traces, token and cost per span, prompt versions, datasets and evaluations, and user feedback.
- **Privacy:** a trace contains the prompt, which here contains the user's document text. Decide whether the tracing backend may hold it: self-host it, or redact the content and send only the counts. This matches the rule already used here, never to keep uploaded text outside the document's own folder.

**In this repo.**
- **Built, partial.**
  - Token counts per question: `trace.config["usage"]` holds `prompt_tokens` and `output_tokens` (for the on-prem reasoning model the count includes the thinking tokens), plus `abstained` and `blocked`, set in `RagPipeline._record` in `rag/query/pipeline.py`. Streaming asks the server to include usage in the stream (`generate_stream` in `rag/common/llm.py`), so a streamed answer records the same numbers.
  - Latency: every stage records `elapsed_ms` in the trace (`rag/common/trace.py`), the response has `seconds` and the stage list, and the page shows them under "What the pipeline saw".
  - Traces of single-document questions are saved in the document's own folder, `data/uploads/<doc_id>/chat/`, so deleting the document deletes them; questions over several documents are not saved.
- **Not built:** a price table and cost per question; totals per owner or per day; dashboards, budgets and alerts; time to first token as a metric (the streaming path does not record it); a generation span inside the trace (the stage timings cover retrieval; the model time is in `seconds`); the Langfuse or LangSmith integration. These are planned for the next chatbot project, which will add observability and then tool calling.
- Per-question evaluation cost (the judge calls) is also not tracked.

**Follow-ups.** How would you attribute cost to a user when one request makes several model calls (rewrite, answer, judge)? (Give each request a trace id and sum the spans.) How do you avoid logging secrets and personal data in traces? (Redact before sending, or self-host.) What do you alert on? (Spend per user, p95 latency, error rate, abstention rate, blocked-answer rate.) How would you compare two prompt versions? (Tag traces with the prompt version and compare quality, cost and latency on the same golden questions.)

---

## One-line revision

- *Follow-up question:* the model is stateless; send history, and rewrite the follow-up into a standalone question before searching; ask when it is ambiguous.
- *Compaction:* recent turns word for word, older turns as a summary, key facts kept separately, re-fetchable text dropped, raw log kept.
- *Cost:* tokens (including hidden reasoning tokens) times price, or GPU time if self-hosted, per request, aggregated per user, with budgets, in a tracing tool.
