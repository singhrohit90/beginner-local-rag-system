# Generation and evaluation: interview revision notes

How to use this file: read the **Short answer** aloud, then skim **Go deeper**, then check **In this repo** so you can name a file and a number. Labels used below:

- **General knowledge**: standard interview material, nothing in the repo proves it.
- **Built here / measured here**: a file or number you can point to.
- **Not built / not measured**: say so plainly in an interview; it is stronger than bluffing.

Setup facts you need in your head. The corpus is the book "Designing Data-Intensive Applications" (DDIA). The golden set is `data/golden/ddia_questions.jsonl`: 45 questions, of which 37 are answerable, 6 unanswerable, 2 attacks (counted from the file). The main generator is `gpt-oss-20b` (a reasoning model on an on-prem vLLM server). The usual judge is `ollama:qwen2.5:7b`, a small local model. The best retrieval config is semantic chunks + weighted fusion (hit@5 0.865, mrr 0.663, from `CLAUDE.md` and `rag/README.md` Step 9).

Sections:

1. How do you evaluate a RAG system end to end?
2. How do you build a golden set?
3. What metrics do you use for generation?
4. How do you use an LLM as a judge, and what goes wrong?
5. How does judge calibration work?
6. What is the noise band and how do you decide one config beats another?
7. What are your measured results and how do you read them honestly?
8. How do you design the RAG prompt?
9. How do citations and abstention work?
10. Reasoning models and token budgets
11. The LLM disk cache and the privacy rule
12. Finding a failure by using the product: questions about the documents
13. How would you extend evaluation (online, feedback, CI, sampling)?
14. How do you measure cost and latency?
15. "How do you know your RAG system is good?"
16. Contradictions and gaps in the repo

---

## 1. How do you evaluate a RAG system end to end?

**Question.** You built a RAG system. How do you evaluate it, and why not just score the final answers?

**Short answer.** I score retrieval and generation separately, then connect them with a per-question trace. Retrieval asks "was the evidence in the context the model saw?". Generation asks "given that context, was the answer right, grounded and well-behaved?". If I only scored final answers I could not tell a retrieval bug from a prompt or model bug, so I would fix the wrong stage.

**Go deeper.**

- General knowledge: a RAG answer is correct only if (a) retrieval surfaced the evidence and (b) the generator used it. Two stages, two failure modes, two different fixes.
- Retrieval metrics: hit@k, recall, MRR, nDCG against labelled gold evidence. Generation metrics: correctness, faithfulness (groundedness), answer relevance, citation validity, abstention.
- The glue is the trace: one object per question holding every stage's hits, the prompt, the answer, citations, timings and errors. Then every wrong answer gets a label that says which stage to fix.
- The attribution matrix used here (answers.py docstring):

| Evidence in context? | Answer correct? | Label | What to fix |
|---|---|---|---|
| yes | yes | `ok` | nothing |
| yes | no | `generation_fail` | prompt, model, context order |
| no | no | `retrieval_fail` | chunking, search, fusion, k |
| no | yes | `right_without_evidence` | suspicious: outside knowledge or luck |

- "Evidence in context" is strict: every gold page range must be covered (unless `any_range`), a chunk on the gold page must contain the evidence terms to count, and every evidence term must appear in the context text. Without that strictness, a half-supplied context gets blamed on the generator. This was a real bug found in a hand check (commit `5c5c56b`, `8efecf6`).

**In this repo.**

- Trace: `rag/common/trace.py`, classes `StageRecord` and `Trace`, method `Trace.record(name, kind, hits, **meta)` (stores `elapsed_ms` since the previous stage), `Trace.stage(name)`, `Trace.save`, `load_trace`. Fields include `prompt`, `answer`, `citations`, `error`, `config`.
- Stages written by `RetrievalPipeline.run` in `rag/query/pipeline.py`: `dense`, `bm25`, `fuse`, `rerank`, `context`. `RagPipeline.answer` adds `prompt`, `answer`, `citations` and `config["usage"]` (prompt tokens, output tokens, abstained, blocked).
- Retrieval scoring: `rag/observe/retrieval_quality/metrics.py` (`is_relevant`, `first_relevant_rank`, `strictify`), `run_eval.py`, `diagnose.py`. Failure labels `retrieval_miss`, `lost_at_<stage>`, `retrieval_ok` are described in `rag/README.md` Step 3.
- Generation scoring: `rag/observe/generation_quality/answers.py`, `score_answer` and `aggregate`. Driver: `rag/experiments/answer.py`. Output in `runs/<name>/`: `traces/`, `answers.jsonl`, `answer_report.json`.
- Measured: for gpt-oss-20b in memory, outcomes were `ok` 24, `retrieval_fail` 6, `generation_fail` 3, `right_without_evidence` 3, `unjudged` 1 (`runs/ans__semantic__weighted__gptoss/answer_report.json`). So 6 of the wrong answers are retrieval problems and only 3 are generator problems: improving the prompt would have helped at most 3 questions.

**Follow-ups.**

- Why does `right_without_evidence` matter? (The model may be answering from memory; the system would fail on a private document it has not seen.)
- If retrieval is perfect and the answer is still wrong, what do you check? (Context order, prompt, context length, the gold label itself: `rag/README.md` says `retrieval_ok` plus a wrong answer can mean a wrong label.)
- Where would you add a generation-time stage to the trace? (Not built: generation is not a recorded stage, see section 14.)

---

## 2. How do you build a golden set?

**Question.** How did you build your evaluation questions, and how do you stop the set from flattering your system?

**Short answer.** I wrote questions with page-level gold evidence, short reference answers and per-question key facts, and mixed types: factual, exact-term, paraphrase, multi-chunk, comparison, plus unanswerable and attack questions. Rules keep it honest: questions must not reuse the answer's words, evidence terms are checked against the page text by a script, and batches written by agents were cleaned and reviewed by hand. The set is small (37 answerable), so I treat it as a smoke detector with a noise band, not a benchmark.

**Go deeper.**

- General knowledge: a golden set needs (a) realistic questions, (b) labelled evidence independent of any chunker, (c) coverage of failure types, (d) negatives (should-refuse) and adversarial cases.
- Keyword leakage is the classic trap: a question generated from a chunk reuses its vocabulary and flatters BM25. Rule 1 of the writer rules forbids reusing the answer's distinctive words.
- Gold evidence is stored as inclusive PDF page ranges, not chunk ids, so the same labels score every chunking strategy fairly (`rag/observe/golden.py` docstring).
- Page numbers: always PDF page numbers (for DDIA, printed page + 22). Batch 1 had three wrong gold pages from using the printed page or a neighbouring passage (`data/golden/BATCHES.md`).
- Answerable vs unanswerable vs attack:
  - answerable: has `gold_pages`, `reference_answer`, `key_facts`, `evidence_terms`. Passes if the answer states all key facts.
  - unanswerable: `answerable: false`, no gold pages. Passes only if the model abstains. Best ones are near misses (a topic named in passing, a later version).
  - attack: prompt injection or extraction. Passes only if no string in `must_not_contain` appears and the canary never leaks.
- Key facts: short, atomic statements derived from the reference answer. They exist because a small judge checks them far more reliably than it judges a whole answer (section 4).
- Review: `data/golden/KEY_FACTS_REVIEW.md` is a readable sheet (generated by `python -m rag.observe.golden_tools.export_review`) so a human can read every question with its facts. `data/golden/ABOUT_REVIEW.md` is the same for the about-the-documents set.

**In this repo.**

- Files: `data/golden/ddia_questions.jsonl` (45 lines), loader and schema `rag/observe/golden.py` (`GoldQuestion`, `QUESTION_TYPES`, `load_golden`, `GoldQuestion.validate`).
- Writing rules: `data/golden/question_writer_rules.md` (rule 1 no keyword reuse; rule 6 multi_chunk means one answer needing two places at least 5 pages apart; rule 7 unanswerable prefers near misses). Prompt: `data/golden/question_writer_prompt.md`.
- Provenance: `data/golden/BATCHES.md`. Batch counts in the file: batch 1 = 8, batch 2 = 17, batch 3 = 10, batch 4 = 10 questions. Batch 1 was written with an AI assistant and checked by hand; batch 2 came from an agent file that was invalid JSON with row numbers instead of pages (17 kept, 4 rewritten, 7 duplicates dropped); batches 3 and 4 came from NotebookLM. Known defects recorded there: q032 and q033 are "stapled" (two questions joined by "and"); q037 and q040 have redundant evidence (so they set `any_range`).
- Tools: `rag/observe/golden_tools/find_pages.py`, `clean_paste.py`, `verify_golden.py` (checks evidence terms appear on the gold pages, which catches wrong page numbers), `export_review.py`.
- Type counts (counted from the file): paraphrase 12, exact_term 6, factual 6, multi_chunk 6, comparison 5, table 1, ambiguous 1, unanswerable 6, attack 2. All 37 answerable questions have `key_facts`.
- Not built: `rag/README.md` Step 2 suggests 60 questions and holding out about 20 for final comparisons. The file has 45, and I found no held-out split recorded in the repo. Say "I did not keep a hold-out set" if asked.

**Follow-ups.**

- Why page ranges instead of chunk ids? (Chunker changes would invalidate chunk-id labels.)
- How many questions do you need? (General: enough that the gap you care about exceeds the noise; here 37 gives a 2.7-point step.)
- What is wrong with LLM-generated questions? (They copy source vocabulary; mitigated by rule 1 and by writing at least a third by hand, per `rag/README.md` Step 2.)

---

## 3. What metrics do you use for generation?

**Question.** Walk me through the generation metrics: faithfulness, correctness, relevance, citations, abstention. How is each computed?

**Short answer.** Correctness is "does the answer state every key fact", checked by a judge one fact at a time. Faithfulness is "is every claim supported by the retrieved passages", judged without seeing the reference answer. Citation validity is a regex check that cited `[S#]` labels exist; abstention and attacks are rule-based string checks. Answer relevance and citation support (does the cited passage back the claim) are not built.

**Go deeper.**

- General knowledge definitions:
  - Faithfulness / groundedness: claims entailed by the provided context, regardless of real-world truth.
  - Correctness: matches the reference answer. Can be true by luck (outside knowledge).
  - Answer relevance: does the answer address the question (an answer can be faithful and off-topic).
  - Citation validity: cited ids exist. Citation support: the cited passage actually supports the sentence. These are different; validity is cheap, support needs an entailment judge.
  - Abstention: correct refusal on unanswerable questions, and no over-refusal on answerable ones.
- Why faithfulness and correctness are separate calls: faithfulness never sees the reference answer, so an answer right by outside knowledge shows up as correct-but-unfaithful. That gap separates retrieval from generation problems (`judge.py` docstring).
- Over-refusal is counted as a failure: an answer that abstains on an answerable question gets `correct=False` and, if the gold evidence was in context, `generation_fail` (`answers.py`).

**In this repo.**

| Metric | Where | How |
|---|---|---|
| correctness | `judge_facts` in `rag/observe/generation_quality/judge.py`, called by `score_answer` | all `key_facts` must be stated; extra content ignored; missing facts recorded in `why_correct` |
| faithfulness | `judge_faithfulness` (`FAITHFULNESS_SYSTEM`) | lists claims, checks each against the passages only; `[S1]` labels are not claims |
| citation validity | `citation_is_valid`, `parse_citations` in `rag/query/generate.py` | every cited number must be between 1 and the number of context passages; the report counts `invalid_citations` |
| cites gold | `row["cites_gold"]` in `score_answer` | some cited passage is relevant to the gold pages (strict, evidence-aware) |
| abstention | `looks_like_abstention` in `generate.py` | exact refusal phrase, or looser wording only when the answer cites nothing |
| attack pass | `score_answer` | no `must_not_contain` string in the answer, and canary not present |
| canary leak | `CANARY` in `rag/query/prompt.py` | `CANARY-7f3a91` must never appear in any answer |

- Aggregation: `aggregate` in `answers.py`. `_rate` returns `None` (shown as "n/a") when more than a quarter of the answerable rows are unjudged, so a rate over a few rows is never presented as a score (commit `8efecf6`, `dabdd88`).
- Measured, gpt-oss-20b, semantic + weighted, in memory (`runs/ans__semantic__weighted__gptoss/answer_report.json`): correct 0.750, faithful 0.838, cites gold 0.784, 6 of 6 unanswerable refused, 2 of 2 attacks passed, 0 canary leaks, 0 invalid citations.
- Not built: answer relevance scoring and citation support scoring. Both are listed under "Retrieval and evaluation" in `docs/backlog.md`. Say "citation validity is checked, citation support is not".

**Follow-ups.**

- Can an answer be unfaithful but correct? (Yes, outside knowledge; that is the `right_without_evidence` warning.)
- Why is the refusal check a string match and not a judge? (Cheap and deterministic, but brittle if the model rephrases; the looser regex and the "no citations" condition reduce false positives.)
- How would you score citation support? (General: NLI or LLM judge per sentence-citation pair. Not built.)

---

## 4. How do you use an LLM as a judge, and what goes wrong?

**Question.** You use an LLM to grade answers. What are the risks, and what did you do about them?

**Short answer.** I use a per-question fact checklist: the judge gets the answer and a numbered list of facts and answers "stated or not" for each, with a quote. A holistic "is this answer correct?" judge was unreliable with a small local model, so I dropped it. I also keep the judge different from the generator, store the judge's reasons for spot checks, and calibrate the judge on cases with known answers.

**Go deeper.**

- General knowledge, judge biases:
  - Self-preference: a model rates its own style higher.
  - Position bias in pairwise comparisons: tends to prefer the first (or last) option.
  - Verbosity bias: longer answers score higher.
  - Small judges: miss subtle errors, wobble between prompt versions, fail JSON formatting.
  - Mitigations: decompose into atomic checks, require evidence quotes, use a different or stronger judge, calibrate on known cases, human spot checks, report unparseable replies instead of guessing.
- Here, the verbosity risk is handled directly: the facts prompt says extra sentences "never make a fact false", and the calibration includes a "reference plus extra detail" case that must still be judged correct.
- Parse failures are explicit: `judge_facts` returns `None` entries if the reply is unparseable or has the wrong number of results, and the row becomes `unjudged`. One of 37 answerable questions was `unjudged` in every gpt-oss run.
- Dead end 1, holistic correctness judge (`CLAUDE.md`: do not retry). Evidence from commit `eb79e1b`: after tightening the holistic prompt, the 7B judge got worse: right on only 43 percent of "correct plus extra detail" answers, and the correct count swung by two to three questions between prompt versions. It also marked answers wrong for extra correct detail (commit `5c5c56b`). Fix: key facts, one call, per-fact flag.
- Dead end 2, page-overlap-only relevance (`CLAUDE.md`: do not retry). A chunk counted as relevant if its page range overlapped a gold page. That is generous: a 200-word chunk on the gold page counts even when the answer sentence is in the neighbouring chunk, and a big chunk overlaps gold by accident (`strictify` docstring in `metrics.py`, `rag/README.md` Step 3 metric notes). Fix: `strictify` moves hits that lack the evidence terms off the gold page, and attribution also requires every evidence term in the context.
- Self-preference evidence, built here: the about-the-documents run was judged twice (section 12). The small judge gave 1 of 5; the generator grading itself gave 5 of 6. Reading answers by hand showed the small judge was too harsh and the self-judge lenient. Neither is the truth.
- The code states the rule: "Use a different model from the generator, since models tend to rate their own style highly" (`judge.py` docstring). The main answer runs follow it (generator gpt-oss-20b, judge qwen2.5:7b). One caveat: gemini generator runs were also judged by the same qwen judge, so judge error is shared across all compared runs. That makes comparisons between runs fairer but absolute numbers less trustworthy.
- Not built: pairwise judging, so position bias is general knowledge only, not a thing I measured.

**In this repo.**

- `rag/observe/generation_quality/judge.py`: `FACTS_SYSTEM`, `judge_facts` (returns `FactVerdict` with `stated`, `missing`, `.correct`), `judge_faithfulness`, `FAITHFULNESS_SYSTEM`, `parse_json` (tolerates code fences). The older `judge_correctness` and `CORRECTNESS_SYSTEM` remain only as a fallback for questions without `key_facts`; all 37 have facts, so the fallback is unused on the golden set.
- `score_answer` in `answers.py` stores `facts_stated`, `why_correct`, `why_unfaithful` per row in `answers.jsonl` so a human can read the judge's reasons.
- The judge is chosen by `--judge` in `rag/experiments/answer.py` (default `ollama:qwen2.5:7b`, `--judge none` to skip). A free-tier limit of 20 Gemini requests per day per model motivated `--judge none` (commit `dabdd88`).

**Follow-ups.**

- Why not just use a stronger judge? (General: better, but cost, privacy and availability. Here a local 7B was a deliberate choice; its limits are why calibration and fact decomposition exist.)
- How do you detect that the judge is the problem and not the system? (Calibration set, reading stored reasons, comparing two different judges as in section 12.)
- Why is the faithfulness number only a lower bound? (`rag/README.md` Step 6: the 7B judge sometimes marks supported answers unfaithful.)

---

## 5. How does judge calibration work?

**Question.** How do you know your judge is any good?

**Short answer.** I feed it cases where I already know the right verdict: a reference answer judged against its own question must be correct, the same plus an unrelated sentence must still be correct, another question's reference must be incorrect, and faithfulness with gold pages must pass while unrelated pages must fail. If it fails these easy cases it cannot be trusted. Passing them does not prove it handles subtle errors.

**Go deeper.**

- General knowledge: judge calibration = measure agreement against labelled examples (ideally human-labelled, including hard, near-miss examples), report per-class accuracy, and rerun when the judge model or prompt changes.
- The limit is stated in the file: these cases are easy (identical or unrelated text). A nearly right answer is the case that matters most and it is not covered. Say this out loud.
- Groups run, per question: "correct: own reference", "correct: another question's reference", "correct: reference plus extra detail", the same three for "facts", and "faithful: gold pages as context", "faithful: unrelated pages as context".
- Measured (as written in `rag/README.md` Step 6): the 7B judge scored 95 to 100 percent on correctness and 89 percent on faithfulness. The README does not say which method (holistic or facts) those numbers came from, and the result file `judge_calibration.json` is written under `data/processed/` (gitignored); I did not read it. Treat the figures as the README's claim, not something I re-verified.

**In this repo.**

- `rag/observe/generation_quality/calibrate_judge.py`: `main`, `page_hit` (builds a `Hit` from page text, capped at `WORD_LIMIT = 700` words). Run: `python -m rag.observe.generation_quality.calibrate_judge --judge ollama:qwen2.5:7b`. Output: `data/processed/judge_calibration.json`.
- Not built: a human-labelled set of subtle wrong answers; a calibration run for `gpt-oss-20b` as judge. Calibrating the about-the-documents judge was not done (`docs/about_the_documents.md`).

**Follow-ups.**

- What metric would you report? (General: accuracy per class, Cohen's kappa against humans.)
- When do you rerun it? (When the judge model or prompt changes: `rag/README.md` Step 6.)
- What cases are missing? (Near-miss answers, answers with one wrong number, long answers with one wrong claim.)

---

## 6. The noise band: when does one config beat another?

**Question.** Config A scores 3 points above config B on your golden set. Is A better?

**Short answer.** Not on this set. There are 37 answerable questions, so one question is 2.7 points, and I treat gaps under about 8 points as noise. I only trust gaps that are large and appear across several chunkers or runs, and I read means over chunkers rather than single cells.

**Go deeper.**

- Arithmetic: 1/37 = 2.7 points. A gap of 8 points is three questions. On a binomial near 0.75 with n = 37 the standard error is about 7 points (general knowledge: sqrt(0.75 x 0.25 / 37) = 0.071), which is why "under about 8" is the right order of magnitude. That calculation is mine, not from the repo.
- Paired comparison is better than comparing totals (same questions in both runs, look at which questions flipped), but the repo does not do significance tests. Not built.
- Run-to-run variation: single cells swing by up to 8 points either way (`rag/README.md` Step 9: semantic + weighted falls 0.865 to 0.811 in one stemming comparison, heading + weighted rises 0.865 to 0.892). Only means over five chunkers are meaningful.
- Generation adds another noise source: LLM sampling. Answers "differ from run to run" (`docs/about_the_documents.md`). The disk cache makes reruns identical, which hides sampling noise instead of measuring it. Say so.
- Per-type cells are even smaller: 1 to 12 questions each. Treat the by-type table as a pointer to read answers, not as a result.

**In this repo.**

- Noise rule in `CLAUDE.md` ("Behaviour that must not drift") and `rag/README.md` Step 5 and Step 9.
- Worked example: BM25 stemming gave +5.4 points hit@5 mean over five chunkers (0.741 to 0.795), which is two questions, yet was judged real because the MRR gain moved the same direction on all configs and OpenSearch showed the same effect; the hybrid configs improved only +1.6 to +2.7, so stemming stays off (`rag/README.md` Step 9 tables). The README calls the remaining 2.7-point gap "inside the noise".
- Retrieval invariant used as a regression check: `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` must give hit@5 0.865 and mrr 0.663 (`CLAUDE.md`).
- Not built: bootstrap confidence intervals, multiple seeds for the generator.

**Follow-ups.**

- How would you shrink the noise? (More questions, repeated generations, paired tests; general knowledge.)
- Would you ship a change with +3 points? (Only if it is cheap, safe and has another reason, e.g. fixes a known failure mode.)
- Why does cache reuse matter here? (Identical reruns are not independent samples.)

---

## 7. What are your measured results and how do you read them honestly?

**Question.** What numbers did you get, and what do they tell you?

**Short answer.** With gpt-oss-20b on semantic chunks and weighted fusion, in memory I got correct 0.750 and faithful 0.838; through OpenSearch correct 0.722 and faithful 0.865. That is one question apart each way, so the two are the same within noise. The more useful reading is the outcome split: most failures are retrieval failures, not generation failures.

**Go deeper.**

All from `answer_report.json` files in `runs/`, judge `ollama:qwen2.5:7b`, semantic chunker, weighted config, 37 answerable questions (1 unjudged), 6 unanswerable, 2 attacks:

| Run (`runs/...`) | Generator | correct | faithful | cites gold | outcomes (ok / retr_fail / gen_fail / right_wo_evid / unjudged) |
|---|---|---|---|---|---|
| `ans__semantic__weighted__gptoss` | gpt-oss-20b | 0.750 | 0.838 | 0.784 | 24 / 6 / 3 / 3 / 1 |
| `ans__semantic__weighted__gptoss__opensearch` | gpt-oss-20b | 0.722 | 0.865 | 0.811 | 23 / 6 / 4 / 3 / 1 |
| `ans__semantic__weighted` | gemini-3.5-flash-lite | 0.611 | 0.946 | 0.838 | 22 / 9 / 5 / 0 / 1 |
| `ans__semantic__weighted__gptoss__spotlight` | gpt-oss-20b, spotlight prompt | 0.611 | 0.946 | 0.730 | 20 / 7 / 7 / 2 / 1 |

All four runs: 6 of 6 unanswerable refused, 2 of 2 attacks passed, 0 canary leaks, 0 invalid citations.

How to read them:

- The two gpt-oss rows are one question apart (2.7 points) in correct and in faithful. `rag/README.md` Step 9 says exactly this. The parity claim is "same within noise", not "identical".
- Correct and faithful are rates over judged rows, so the denominator is about 36, not 37.
- Retrieval is the bigger lever: 6 of 37 are `retrieval_fail` versus 3 `generation_fail` in memory.
- By type (gpt-oss in memory): paraphrase correct 0.455 on 12 questions (the weakest), exact_term 1.0 on 6, factual 1.0 on 6, multi_chunk 0.667 on 6, comparison 0.8 on 5. Paraphrase is where the question's wording differs from the book, so this points at retrieval, but cells this small are hints only.
- Gemini and spotlight both read 0.611 correct. That is a coincidence of two different runs, not a link between them. The README records the spotlight cost as "24 to 20 grounded-ok answers", which is why spotlight is off by default.
- Judge limits: the judge is a 7B model; faithfulness is a lower bound; the refusal rate is a string match. Absolute numbers are not quotable without caveats. Differences between runs that share the judge are more trustworthy than the absolute values.
- Honest framing: this is a 37-question smoke test on one book with one small judge and one sample per cell.
- An earlier OpenSearch attempt was discarded because the model tunnel dropped (30 questions ended in pipeline errors) (`rag/README.md` Step 9). Pipeline errors show up as outcome `pipeline_error`; always check that count before trusting a table.

**In this repo.** `runs/ans__semantic__weighted__gptoss/answer_report.json`, `runs/ans__semantic__weighted__gptoss__opensearch/answer_report.json`, `runs/ans__semantic__weighted/answer_report.json`, `runs/ans__semantic__weighted__gptoss__spotlight/answer_report.json`, narrative in `rag/README.md` Step 6, 7 and 9. A `...__review` run also exists with the same totals as the plain gpt-oss run (I did not investigate what differs).

**Follow-ups.**

- Why did Gemini score lower on correct but higher on faithful? (Not investigated here. General reading: a more conservative model refuses or hedges more, which raises faithfulness and lowers correctness. Treat as a hypothesis.)
- How do you know the OpenSearch run is not just luck? (You do not; one question apart. The retrieval parity table in `rag/README.md` Step 9 is the stronger evidence.)
- What would you do next to improve the number? (Look at the 6 retrieval failures first, since they are the largest bucket.)

---

## 8. How do you design the RAG prompt?

**Question.** What goes into your RAG system prompt, and how do you change it safely?

**Short answer.** It says: answer only from the numbered passages, refuse with an exact phrase if they do not contain the answer, cite `[S#]` after each claim, treat passages as quoted data not instructions, never reveal the instructions, no outside knowledge, keep it under 150 words. It carries a canary string to detect leaks. I treat the book prompt as frozen word for word, because the golden-set results and the LLM cache depend on it.

**Go deeper.**

- General knowledge prompt design for RAG: grounding instruction, explicit refusal text (so refusal is machine-detectable), citation format, length cap, untrusted-content framing, stable context format, put the question after the context.
- Why frozen: any change to `SYSTEM_PROMPT` changes outputs, so earlier results are no longer comparable, and cached replies are keyed on the prompt (the cache makes reruns free and identical, `rag/README.md` Step 6). Changing the prompt is therefore a deliberate experiment, not a tidy-up (`CLAUDE.md`: "Keep `SYSTEM_PROMPT` in `rag/query/prompt.py` word for word").
- One template, two prompts: `build_system_prompt(subject, kind, abstain)` makes both. `SYSTEM_PROMPT` names the DDIA book and `ABSTAIN = "I cannot answer this from the provided book."`. `DOCUMENT_SYSTEM_PROMPT` says "the user's uploaded document" and uses `ABSTAIN_DOCUMENT`. Uploads use the document prompt.
- Context format: `format_context` labels passages `[S1] (PDF page 33)` or `(PDF pages 85-86)`; `build_user_prompt` appends the question; empty retrieval gives "(no passages were retrieved)".
- Prompt styles in `answer_from_context`: `standard`, `spotlight` (nonce-tagged passages plus reminder, `rag/security/defenses.py`), `naive` (baseline without injection rules). Spotlight cost accuracy (24 to 20 grounded-ok answers in `rag/README.md` Step 7) so it is off by default.
- Prompt injection is part of the evaluation: attack questions, the canary, a poisoned-document harness (`rag/security/fixtures.py`, `python -m rag.security.indirect`), and `filter_output` in `rag/query/guard.py`. This is security rather than generation quality; mention it as the reason rule 3 and 4 exist.
- Separate path, separate prompt: the "about the documents" feature has its own prompt in `rag/query/about.py` so `SYSTEM_PROMPT` stays untouched.

**In this repo.** `rag/query/prompt.py` (`build_system_prompt`, `SYSTEM_PROMPT`, `DOCUMENT_SYSTEM_PROMPT`, `ABSTAIN`, `ABSTAIN_DOCUMENT`, `CANARY`, `format_context`, `build_user_prompt`), `rag/query/generate.py` (`answer_from_context`, `subject="book"|"document"`), `rag/api/service.py` for the upload path.

**Follow-ups.**

- How would you test a prompt change? (Run the golden set before and after, compare outcome buckets, expect noise of about 8 points, and keep a held-out set. Hold-out not built here.)
- Why an exact refusal phrase? (So abstention can be detected by string match and the UI can show it.)
- Why does the 150-word rule exist? (Cost, latency, less room for unsupported claims; general reasoning.)

---

## 9. How do citations and abstention work?

**Question.** How do you make the model cite its sources, and how do you handle questions it cannot answer?

**Short answer.** The prompt asks for `[S#]` labels after each claim and an exact refusal sentence when the passages lack the answer. Code parses the labels with a regex, checks that each number maps to a real passage, and detects refusals by the exact phrase or by looser wording when no citation is present. Then evaluation checks that unanswerable questions are refused and counts invalid citations.

**Go deeper.**

- `parse_citations` returns passage numbers in order without repeats; `citation_is_valid(cited, n)` is true only if all are in 1..n. A hallucinated `[S9]` with five passages is invalid. Result so far: 0 invalid citations in all four runs in section 7.
- `looks_like_abstention`: the exact phrases always count. Looser patterns ("the passages do not contain...", "no information about...") count only when the answer cites nothing, because "The text does not include the exact figure, but it says X [S2]" is a real answer, not a refusal.
- Validity is not support. A valid `[S2]` may not back the claim. `cites_gold` is a partial proxy (does any cited passage hit the gold evidence). Real citation-support scoring is on the backlog and not built.
- Over-refusal is a generation failure when the evidence was in context. Under-refusal on unanswerable questions is `hallucinated` in `score_answer`.
- In the `trace`, citations are stored as `S<n>` strings (`RagPipeline.answer`), and the UI shows the cited passages with page, score and chunk id (`rag/README.md` Step 8).
- Uploads: chunk ids are qualified `<doc_id>:<chunk_id>` (`CLAUDE.md`) so citations stay unambiguous across documents.
- The about-the-documents path cites `[D1]`, `[D2]`, and the parser was fixed to read `[D1]`, `(D1)` and `D1` (`docs/about_the_documents.md`, Measured).

**In this repo.** `rag/query/generate.py` (`_CITATION`, `_ABSTAIN_PATTERN`, `looks_like_abstention`, `parse_citations`, `citation_is_valid`, `Answer`), `rag/observe/generation_quality/answers.py` (`score_answer`, `aggregate`). Measured: 6 of 6 unanswerable refused in every run (`runs/ans__*/answer_report.json`). Only 6 unanswerable questions exist, so this is weak evidence about abstention in general.

**Follow-ups.**

- What if the model refuses with different words? (Regex misses it; then it is scored `hallucinated`. A judge-based refusal check is not built.)
- How do you reduce hallucinated citations? (General: constrain the format, validate and drop invalid ones, or ask for quotes.)
- What does a valid but wrong citation look like, and how would you catch it? (Entailment check per claim; not built.)

---

## 10. Reasoning models and token budgets

**Question.** Your generator is a reasoning model. What changes in how you call it?

**Short answer.** A reasoning model spends output tokens on hidden thinking before the visible answer, so the token limit has to cover both or the answer is cut off, and the thinking must not be shown to the user. The client sets that budget and separates the thinking from the answer. I did not read the client code for this note, so I cannot cite its exact numbers.

**Go deeper.**

- General knowledge: with reasoning models, `max_tokens` counts thinking plus answer. A budget that is too small gives an empty or truncated answer; too large costs latency. Thinking text is separate output (often a different field) and may contain unsupported or sensitive content, so it is not shown.
- What the repo does say: calls pass an output cap: `answer_from_context` uses `max_output_tokens=600`; each judge call uses `max_output_tokens=1500` (`judge.py`). `docs/backlog.md` says the reasoning model "sends its thinking separately, which must not be shown" and that `OpenAICompatLLM` in `rag/common/llm.py` waits for the whole reply today (no streaming). The extra token budget added by the client is described by the task owner but I did not verify it in code. Check `rag/common/llm.py` yourself before claiming specifics.
- Judge calls also use `json_mode=True` and a tolerant `parse_json`, because reasoning or chatty models may wrap JSON in code fences.
- Usage is recorded: `trace.config["usage"]` holds prompt and output tokens per answer (`RagPipeline.answer`).
- Streaming is built (2026-10-10): it conflicts with `filter_output`, which judges the whole answer and can withhold it, so a streaming version, `StreamGuard`, holds back risky pieces (`04_system_design_and_streaming.md`, section 8). Streamed answers are scored like any other: the final text is the same object the non-streaming path records.

**In this repo.** `rag/query/generate.py` (`answer_from_context`), `rag/observe/generation_quality/judge.py`, `rag/query/pipeline.py` (`RagPipeline.answer`), `docs/backlog.md` (UI and API section). Model client: `rag/common/llm.py` (not read for this document).

**Follow-ups.**

- How do you know a truncated answer happened? (Check empty or cut output and token counts; in `score_answer` an exception becomes `pipeline_error`.)
- How do you validate a streamed answer? (Hold-back guard online, the whole-answer check at the end, and the same judges offline on the final text; see `04_system_design_and_streaming.md`, section 8.)
- Does the thinking affect cost? (Yes, output tokens; the usage numbers in the trace would show it. I did not aggregate them.)

---

## 11. The LLM disk cache and the privacy rule

**Question.** You cache LLM replies on disk. Why, and what is the risk?

**Short answer.** The cache makes reruns of an experiment free and identical because the same prompt returns the same stored reply. The risk is privacy: a cache would keep the text of uploaded documents after the user deletes them. So uploads and the document-facing API never use the cache.

**Go deeper.**

- General knowledge: caching LLM calls by prompt hash gives reproducibility and saves cost, but (a) hides sampling variance, (b) stores user content, (c) goes stale when the prompt or model changes.
- Here the cache is `data/processed/llm_cache/` (`rag/README.md` Step 6), used by experiments on the book. Book text is public and owned by the project, so caching it is fine.
- The rule (`CLAUDE.md`): never use the cache for uploaded documents, i.e. call `get_llm(spec, cache_dir=None)`.
- Enforced at: `rag/api/main.py` line 96, `llm=get_llm(setting("RAG_LLM", "vllm:/models/gpt-oss-20b"), cache_dir=None)`. And `rag/experiments/about.py` lines 88 and 89 pass `cache_dir=None` for both generator and judge, with the comment that the cache would keep the profile text of documents after a delete.
- Related: the API saves each question's trace inside the document folder (`data/uploads/<doc_id>/chat/`), so deleting a document deletes everything kept about it (`rag/README.md` Step 8). Cross-document questions are not saved as traces for the same reason (`docs/backlog.md`).
- The cache hides prompt changes only if the key ignores them; since the prompt is part of the key, changing `SYSTEM_PROMPT` misses the cache. That is why a frozen prompt keeps old results valid.

**In this repo.** `rag/api/main.py`, `rag/experiments/about.py`, `rag/README.md` Step 6 and 8, `CLAUDE.md`. The cache implementation is inside `rag/common/llm.py`, not read for this note.

**Follow-ups.**

- How would you prove deletion works? (A test that deletes a document and checks nothing remains; I did not verify such a test here.)
- Could you cache safely with per-owner keys and delete on document removal? (Possible, more complex; the rule here is the simple one.)
- Does the cache affect your noise estimate? (Yes, section 6.)

---

## 12. Finding a failure by using the product: questions about the documents

**Question.** Tell me about a bug or gap you found after the metrics looked fine.

**Short answer.** In the chat UI I asked two HBase books "when should I use the Definitive Guide and when the Reference Guide?" and got "I cannot answer this from the provided document". The refusal was honest: no passage says how the books differ, because that fact is about the books, not in them. So I added a per-document profile and a separate route for questions about documents, kept out of the search index so the retrieval numbers do not move.

**Go deeper.**

- Lesson: the golden set only covered questions about the book's content, so the metrics said nothing about this class. Real use found it in minutes. General point: eval sets reflect what you thought of, production reflects what users ask.
- Design (`docs/about_the_documents.md`): a profile per document (name, page count, contents list, opening text), built from extracted text with no model call, a separate answer step with its own prompt, a separate route `POST /v1/ask-about` the user picks on the page. The caller chooses; nothing guesses. Alternatives rejected: automatic intent routing (a classifier that can be wrong and must be measured first), profile as an indexed chunk (would change the 0.865 / 0.663 retrieval numbers), model-written summary at upload (needs the tunnel, can invent), per-document retrieval and comparison (heavier).
- Safety: the profile is untrusted text, so the keyword scanner removes instruction-like parts, the profile cannot close its own tag, the prompt says profile text is data, the output filter still runs, owner comes from `current_owner`.
- Evaluation of it: six golden questions in `data/golden/about_questions.jsonl` (facts written by an agent, not yet reviewed: see `data/golden/ABOUT_REVIEW.md`), run with `python -m rag.experiments.about` using `judge_facts`. Smoke test on 2026-10-10, generator gpt-oss-20b, over both HBase books:

| Judge | Fully correct | Facts stated | Run folder |
|---|---|---|---|
| `ollama:qwen2.5:7b` | 1 of 5 judged (one answer could not be judged) | 5 of 12 | `runs/about_gptoss/about_report.json` |
| `gpt-oss-20b` grading itself | 5 of 6 | 12 of 14 | `runs/about_gptoss_selfjudge/about_report.json` |

- Why the number is unreliable (all from `docs/about_the_documents.md`): six questions make one question 16.7 points; facts not yet reviewed; answers differ run to run; the small judge marked right answers down (it scored the Ganglia/JMX/Nagios answer 0 of 2 although it names the right book and chapter); the self-judge is lenient by construction. The one question that failed under both judges (a001, the comparison) is a real defect: the answer omits the page counts and that the Reference Guide is the official guide unless asked. Whether those facts belong in the expected answer is for the reviewer to decide. The doc's conclusion: "Use a judge that is not the generator before quoting a number."
- Honest way to say it: "The truth is somewhere between 1/5 and 5/6, and I can only say it works on the headline example."
- The two judges also disagree on denominators (5 judged vs 6), which is another reason not to compare the rates directly.
- Not built: automatic routing between content and about mode. Not measured: more than these six questions, and any third judge.

**In this repo.** `rag/ingestion/profile.py`, `rag/query/about.py` (`prepare`, `build_about_prompt`, `answer_about`), `DocumentService.ask_about` and `profile` in `rag/api/service.py`, `rag/experiments/about.py` (`run_questions`, `summarise`), `data/golden/about_questions.jsonl`, `docs/about_the_documents.md`, `docs/backlog.md` (last section), tests `tests/test_about.py`.

**Follow-ups.**

- Why not detect the question type automatically? (Needs a classifier that must itself be measured; the golden questions first, then routing.)
- Why not index the profile as a chunk? (Moves retrieval metrics and changes what content questions retrieve.)
- How would you resolve the judge disagreement? (Hand-label the 6 answers, then score each judge against the labels, like calibration.)

---

## 13. How would you extend evaluation: online, feedback, CI, sampling?

**Question.** Offline evaluation is done. What would you add for production?

**Short answer.** Right now everything is offline on a fixed set. I would add regression gating in CI on a cheap subset, log traces with a retention rule and sample them for human review, capture user feedback tied to trace ids, and track production metrics like refusal rate, citation validity and latency. None of the online parts exist in this repo.

**Go deeper.**

- General knowledge:
  - Regression gating: run a small deterministic suite on each change (retrieval metrics are cheap and need no LLM). Gate on a threshold wider than the noise band, not on 1-question flips.
  - Online evaluation: log every request; monitor refusal rate, empty-context rate, invalid-citation rate, latency and cost; run the judge on a sampled fraction.
  - User feedback: thumbs up/down plus reason, joined to the trace by id; feeds new golden questions.
  - Sampling for review: stratify by low confidence, refusals, long latency and random; convert failures to golden questions. This is how the HBase failure (section 12) would be caught systematically.
  - A/B tests with enough traffic to beat noise.
- What exists: the retrieval invariant check (`CLAUDE.md`, `python -m rag.experiments.retrieval --chunkers semantic --configs weighted`, hit@5 0.865, mrr 0.663) is a manual regression check; the test suite is run by `python -m pytest tests -q` (about 2 minutes with OpenSearch up, per `CLAUDE.md`); uploaded-document chat traces are saved per document in `data/uploads/<doc_id>/chat/`.
- Not built: CI gating (I found no CI config; I did not search for one thoroughly, so say "not built" only after checking), online metrics, user-feedback capture, trace sampling, any retention rule (listed in `docs/backlog.md` Security: "Retention for traces ... of documents that are not deleted").
- Privacy tension: sampling production traces means storing user text. Here the policy is traces live in the document folder and die with the document; cross-document questions are not saved. A review pipeline needs consent and retention rules first.
- Cost of judge runs matters for gating: a full judged run needs about 37 generation calls plus about 74 judge calls (facts + faithfulness); the Gemini free tier of 20 requests a day per model could not support it (commit `dabdd88`). The 74 is my arithmetic from the code, not a measured count.

**In this repo.** `CLAUDE.md` (Commands), `rag/experiments/retrieval.py`, `rag/experiments/answer.py` (`--judge none` is the cheap mode: abstention, attack, canary and citation checks only), `docs/backlog.md`.

**Follow-ups.**

- What would you gate on? (Retrieval metrics and the no-judge generation checks: deterministic and cheap.)
- How do you avoid overfitting to the golden set? (Hold-out and new questions from production; hold-out not built here.)
- What would you alert on in production? (Refusal rate shift, invalid citation rate, latency tail, error rate.)

---

## 14. How do you measure cost and latency?

**Question.** How do you know how fast and how expensive your pipeline is, and where the time goes?

**Short answer.** Each trace records the time of every retrieval stage and the token counts of the generation call. That tells me where retrieval time goes. Generation time is not recorded as its own stage and I did not aggregate token cost, so I can say what is measured and what is not.

**Go deeper.**

- General knowledge: measure p50 and p95 per stage, not only the mean; cost = prompt tokens x price + output tokens x price (reasoning models bill thinking tokens as output); watch context size, because it drives prompt tokens.
- `Trace.record` stores `elapsed_ms` as the time since the previous stage (or since the trace was created for the first stage). So `dense`, `bm25`, `fuse`, `rerank`, `context` each carry a duration. Because the first stage's time is measured from trace creation, it includes setup; read it with that in mind.
- `RagPipeline.answer` does not call `trace.record` for generation, so the generation duration is not in the stage list. The usage block (`trace.config["usage"]`) has `prompt_tokens` and `output_tokens` only. Not measured: end-to-end latency per question and cost per question. I could not safely read an individual trace file (the secret-scan hook flagged `runs/ans__semantic__weighted__gptoss/traces/q001.json` as containing a credit-card-like number, a false positive; I did not work around it).
- Measured retrieval-side latency (`rag/README.md` Step 9): OpenSearch costs 0.1 to 0.5 seconds per question including evaluation work, against 0.02 to 0.2 in memory. By config, OpenSearch was about 7x slower for dense, 11x for bm25, 6x for rrf and weighted. HNSW approximate search was not measured (`docs/backlog.md`).
- The chat page shows the stages that ran and how long each took (`rag/README.md` Step 8), which uses the same trace data.
- Rerank is optional and costs a cross-encoder pass; `RetrievalConfig` switches stages off and a disabled stage leaves no trace entry (`rag/query/pipeline.py` docstring).

**In this repo.** `rag/common/trace.py` (`StageRecord.elapsed_ms`), `rag/query/pipeline.py`, `rag/api/static/index.html` (UI), `rag/README.md` Step 9.

**Follow-ups.**

- How would you add generation time? (Record a `generate` stage around `answer_from_context`.)
- Where would you cut latency first? (Likely the model call, but I have not measured it; verify before saying.)
- How do you control cost? (Context word budget in `select_context`, the 150-word answer rule, `max_output_tokens`, the cache for experiments.)

---

## 15. "How do you know your RAG system is good?" (the honest answer)

**Question.** How do you know your RAG system is good?

**Say this (about 45 seconds).**

"I don't claim it's good in general. I can say what I measured and how far to trust it. I have a 45-question golden set on one book: 37 answerable, 6 unanswerable, 2 attack. I score retrieval and generation separately and label every wrong answer as a retrieval failure or a generation failure from the trace. With gpt-oss-20b on semantic chunks and weighted fusion, retrieval hit@5 is 0.865, answers are about 72 to 75 percent correct and 84 to 87 percent faithful, and every unanswerable question was refused with no injection leaks. Most failures are retrieval, not generation. The limits are real: one question is 2.7 points so gaps under about 8 are noise; the judge is a 7B local model that I calibrated only on easy cases; I have no hold-out set, no online evaluation, no citation-support or answer-relevance scoring; and when I tried a self-judge on a separate feature it disagreed wildly with the small judge. So it's good enough to compare changes and find failures, not good enough to promise a production accuracy."

Numbers in that answer come from `runs/ans__semantic__weighted__gptoss*/answer_report.json`, `CLAUDE.md` (hit@5 0.865, mrr 0.663) and `docs/about_the_documents.md`.

**Follow-ups.**

- What would convince you more? (More questions, a stronger or human-checked judge, a hold-out set, production sampling.)
- What is the biggest weakness? (Small set plus small judge, so absolute scores are soft; the 6 retrieval failures and weak paraphrase results are the actionable part.)
- What would you do with one more week? (Hand-label a judge calibration set with near-miss answers, add citation support scoring, add a hold-out set.)

---

## 16. Contradictions and gaps in the repo

Things that do not line up, so you are not caught out:

1. **Noise band wording.** `CLAUDE.md` says gaps under about 8 points are noise. `rag/README.md` Step 5 says "differences of a few points are noise". Step 9 says "Individual cells swing by up to 8 points either way". These are consistent in direction but the number differs; use "about 8 points" and "one question = 2.7".
2. **Golden set size.** `rag/README.md` Step 2 suggests 60 questions with about 20 held out. The file has 45 and no hold-out is recorded. The README is a plan, not a description.
3. **Judge calibration figures.** `rag/README.md` Step 6 quotes 95 to 100 percent (correctness) and 89 percent (faithfulness). The calibration file now also tests the fact-checklist method, but the README does not say which method the quoted numbers came from, and the result file is gitignored (`data/processed/judge_calibration.json`). Treat these as unverified.
4. **Step order.** In `rag/README.md`, Step 3 (evaluate any pipeline) appears after Step 7 and Step 2 comes before Step 4. Build order, not reading order. The first lines of the README say to read in a given order.
5. **Fallback judge.** `judge_correctness` (the holistic judge `CLAUDE.md` says not to retry) still exists in `judge.py` as a fallback and in the calibration. All 37 answerable questions have `key_facts`, so the fallback does not run on the golden set; it matters only if someone adds a question without facts.
6. **Dedicated about-judge disagreement.** `docs/about_the_documents.md` reports 1 of 5 and 5 of 6 for the same answers; the repo itself says the truth lies between and gives no better number.
7. **Not built (confirmed in `docs/backlog.md` or by reading the code):** answer relevance scoring, citation support scoring, generation latency as a trace stage, per-question cost, CI gating, online evaluation, user feedback capture, a hold-out split, significance tests, automatic routing for about questions.

Claims I could not verify while writing this file: the internals of `rag/common/llm.py` (token budget, thinking separation, cache key), the contents of `data/processed/judge_calibration.json`, per-stage timings in any individual trace file, and whether any CI configuration exists.
