# Prompt for a question-writing assistant (NotebookLM or similar)

Source to upload: `data/processed/ddia_for_agent.txt` (made by `python -m rag.ingest.export_text`).
Paste everything below the line as the chat message. Ask for about 10 questions per request,
because long answers get cut off. Each batch is logged in `BATCHES.md`.

After each batch, in order:

1. Copy the output into a plain-text editor and save it as `data/golden/batchN.jsonl`.
2. `python -m rag.eval.clean_paste data/golden/batchN.jsonl data/golden/batchN.clean.jsonl`
3. `python -m rag.eval.verify_golden data/golden/batchN.clean.jsonl data/processed/ddia.pages.jsonl`

What changed since batch 3: strings must not contain double quotes, which broke the last file;
multi_chunk is defined much more strictly (batch 3 produced two "stapled" questions); the topic
list covers batch 3; and the request below is for batch 4.

---

Write golden evaluation questions for a RAG system, using ONLY the uploaded book text. Each page
starts with a marker like `=== PDF PAGE 33 (printed 11) ===`. Always use the PDF page number from
that marker, never the printed number and never your own citation numbers.

Output one JSON object per line inside a single code block, with no other text and no blank lines.
Fields: id, question, type, answerable, reference_answer, gold_pages, evidence_terms, notes

- id: string, "n401", "n402", and so on.
- gold_pages: list of [start, end] PDF page ranges, copied from the markers of the pages where
  the answer is stated. Use a separate range for each separate place.
- evidence_terms: 1 to 3 short strings copied EXACTLY, character for character, from those pages
  (code and punctuation included). Prefer rare terms. Never use a common word.
- reference_answer: one or two sentences copied or tightly paraphrased from the gold pages. Add
  nothing from outside the text.
- notes: the source sentence or sentences and their PDF page markers. IMPORTANT: inside any string
  value never use the double quote character. Use single quotes when quoting the book, and write
  apostrophes normally. A double quote inside a value makes the file invalid.

Rules:
1. The question must NOT reuse the distinctive words or phrases of the answer. A keyword search on
   the question text should not land on the gold page. Describe the situation instead of naming
   the term. Comparison questions may name the two things being compared.
2. Only ask what the text states. Do not invent connections, analogies or relationships that the
   book does not itself make.
3. Never use a figure, a table, the table of contents, the preface or the index as the only source.
4. Each answerable question must be answerable from its gold pages alone.
5. Types: factual (one passage), exact_term (hinges on a rare term, command or code),
   paraphrase (wording differs from the text), multi_chunk (see rule 6), comparison (two things
   contrasted), ambiguous (a terse query such as '2PC vs 3PC'), unanswerable (see rule 7).
6. multi_chunk means ONE question with ONE coherent answer that cannot be written without facts
   from two places at least 5 pages apart. It must not be two questions joined with 'and', and
   the answer must not be two independent facts. The best source is a cross-reference the book
   itself makes, such as 'see Title on page N' or 'we will revisit this in Chapter N': the two
   passages are linked by the author. Typical shapes: a problem in one place and the mechanism
   that solves it in another, or a concept and its stated consequence elsewhere. In notes, name
   the cross-reference or sentence that links the two places.
7. unanswerable means answerable is false and gold_pages is []. Prefer near misses: a topic the
   book names only in passing, a product or version that postdates the book, or a detail the book
   deliberately leaves out. Put the key term you checked in evidence_terms and confirm it does not
   appear in the text. Do not ask about anything that is plainly unrelated to databases.
8. Do not repeat these existing topics: Twitter timeline fan-out, SSTable sparse index, Bloom
   filter, B-tree write-ahead log, fencing tokens, linearizability, schema-on-read, sloppy quorum,
   LSM-tree vs B-tree, document vs term partitioned indexes, broadcast hash vs sort-merge join,
   stream joins, 2PC vs 3PC, WITH RECURSIVE, Cypher WITHIN, MongoDB mapReduce, Thrift IDL,
   monotonic reads, hot keys with a random prefix, row-level locks and dirty writes, timeouts and
   unbounded network delay, honest but unreliable nodes, read repair and anti-entropy, multi-leader
   write latency, the quorum condition w + r > n, read-after-write consistency, last write wins,
   pessimistic vs optimistic concurrency control, CockroachDB, idempotent request IDs, the
   database inside-out idea.

Batch 4 request: 10 questions, drawing on chapters 1 to 4 and 10 to 12 (data models, encoding,
batch processing, stream processing, the future of data systems): 5 multi_chunk, 3 unanswerable,
2 paraphrase.
