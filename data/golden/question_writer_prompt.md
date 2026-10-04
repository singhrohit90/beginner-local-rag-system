# Prompt for a question-writing assistant (NotebookLM or similar)

Source to upload: `data/processed/ddia_for_agent.txt` (made by `python -m rag.ingest.export_text`).
Paste everything below the line as the chat message. Ask for 10 questions per request, because
long answers get cut off. After each batch, save the JSON lines and run `verify_golden`.

---

Write golden evaluation questions for a RAG system, using ONLY the uploaded book text. Each page
starts with a marker like `=== PDF PAGE 33 (printed 11) ===`. Always use the PDF page number from
that marker, never the printed number and never your own citation numbers.

Output one JSON object per line, no other text, with these fields:
id, question, type, answerable, reference_answer, gold_pages, evidence_terms, notes

- id: string, "n001", "n002", ...
- gold_pages: list of [start, end] PDF page ranges, copied from the markers of the pages where
  the answer is stated. Use separate ranges for evidence in separate places.
- evidence_terms: 1 to 3 short strings copied EXACTLY, character for character, from those pages
  (code and punctuation included). Prefer rare terms. Never use a common word.
- reference_answer: one or two sentences copied or tightly paraphrased from the gold pages. Add
  nothing from outside the text.
- notes: the exact sentence you based the answer on, in quotes, and its PDF page marker.

Rules:
1. The question must NOT reuse the distinctive words or phrases of the answer. A keyword search on
   the question text should not land on the gold page. Describe the situation instead of naming
   the term. Comparison questions may name the two things being compared.
2. Only ask what the text states. Do not ask about connections or analogies the book does not make.
3. Never use a figure, a table, the table of contents, the preface or the index as the only source.
4. Each answerable question must be answerable from the gold pages alone.
5. Types: factual (one passage), exact_term (hinges on a rare term, command or code),
   paraphrase (wording differs from the text), multi_chunk (needs two or more passages at least
   5 pages apart, each its own range), comparison (two things contrasted), ambiguous (a terse
   query such as "2PC vs 3PC"), unanswerable (not in the text).
6. For unanswerable questions: use topics the book names only in passing or that postdate it, set
   answerable to false and gold_pages to [], and put the term you checked in evidence_terms.
7. Do not repeat these existing topics: Twitter timeline fan-out, SSTable sparse index, Bloom
   filter, B-tree write-ahead log, fencing tokens, linearizability, schema-on-read, sloppy quorum,
   LSM-tree vs B-tree, document vs term partitioned indexes, broadcast hash vs sort-merge join,
   stream joins, 2PC vs 3PC, WITH RECURSIVE, Cypher WITHIN, MongoDB mapReduce, Thrift IDL.

Batch 1 request: 10 questions on chapters 5 to 9 (replication, partitioning, transactions,
distributed systems, consistency): 3 factual, 3 paraphrase, 2 multi_chunk, 1 comparison,
1 unanswerable.
