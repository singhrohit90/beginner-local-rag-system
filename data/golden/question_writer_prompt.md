# Asking NotebookLM for golden questions

NotebookLM limits the length of a chat message, so the long instructions live in a source file and
the chat message is short.

## One-time setup in the notebook

Upload both as sources:

1. `data/processed/ddia_for_agent.txt` (the book, made by `python -m rag.ingest.export_text`)
2. `data/golden/question_writer_rules.md` (the rules, 4.7 KB)

If the notebook has a place for custom chat instructions, you can paste the rules there instead,
but the source file is the safer route.

## Chat message for each batch

Paste this, changing only the last two lines for the batch you want:

    Follow the rules in the source question_writer_rules.md exactly. Use only the source
    ddia_for_agent.txt for book content. Reply with one code block of JSON lines. No double
    quotes inside any string value. PDF page numbers only, from the === PDF PAGE n === markers.
    Start ids at n401.
    Batch 4: 10 questions from chapters 1 to 4 and 10 to 12 (data models, encoding, batch
    processing, stream processing, future of data systems): 5 multi_chunk, 3 unanswerable, 2 paraphrase.

If it ignores a rule, repeat just that rule in a follow-up message, for example "multi_chunk must
be one question, not two joined with and".

## After each batch

1. Copy the output into a plain-text editor and save it as `data/golden/batchN.jsonl`.
2. `python -m rag.eval.clean_paste data/golden/batchN.jsonl data/golden/batchN.clean.jsonl`
3. `python -m rag.eval.verify_golden data/golden/batchN.clean.jsonl data/processed/ddia.pages.jsonl`
4. Log it in `BATCHES.md`.

## Ideas for later batches

- Batch 5: chapters 5 to 9, true multi_chunk questions built on cross-references, plus
  paraphrases of material that batch 3 covered only once.
- Batch 6: more exact_term questions on code and syntax, and ambiguous short queries.
