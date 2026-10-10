# About-the-documents questions: review needed

`about_questions.jsonl` holds 6 questions for the "about the documents themselves" path (`POST /v1/ask-about`).
The questions and every key fact were written by the agent, not by you. Please review them, as with `KEY_FACTS_REVIEW.md`:
an answer counts as correct only if it states every fact listed for its question.

They are asked over two uploads together (the HBase Reference Guide, 904 pages, and HBase: The Definitive Guide, 554 pages),
and each fact was checked by hand against those uploads' `profile.json` (name, page count, first 80 contents entries,
2,500 characters of opening text). The model never sees more than that, so a fact must be in it.

| id | kind | what to check |
|----|------|---------------|
| a001 | compare | page counts 904 / 554; "official" wording; the contents lists |
| a002 | purpose | Reference Guide preface, PDF p9 |
| a003 | audience | the "Heads-up if this is your first foray into distributed computing" paragraph; second fact is an inference from the parts, judge it |
| a004 | which covers a topic | Definitive Guide, Chapter 10 Cluster Monitoring p417 |
| a005 | unanswerable from profiles | must say the profiles do not show price or reviews |
| a006 | document name is the trap | "Definitive" does not mean official |

Things to know when judging:

- `gold_pages` are filled only because the loader requires them for answerable questions. They are profile pages and are not
  used for scoring here (there is no retrieval).
- Each profile lists only the first 80 contents entries, so the Reference Guide shows nothing after Chapter 67. A question about
  a topic late in either book would be unfair; a004 sits inside the shown entries.
- a005 and a006 have `answerable` false and true. The runner does not use the abstain flag (the about path never sets it);
  it scores the facts only.
- Small sample (6): one question is 16.7 points. Treat results as a smoke test, not a measurement.
