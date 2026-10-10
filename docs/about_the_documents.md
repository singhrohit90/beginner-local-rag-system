# Questions about the documents themselves

Decided 2026-10-10, built the same day. Code: `rag/ingestion/profile.py`, `rag/query/about.py`,
`DocumentService.profile` and `ask_about` in `rag/api/service.py`, `POST /v1/ask-about`, and the mode choice
on the page. Tests: `tests/test_about.py`.

## The problem

Asked across the two HBase books, "explain me when one should use definitive guide and when to use
reference guide" gave "I cannot answer this from the provided document", with passages about typographical
conventions and transactions. The refusal was honest. How two books differ is a fact about the books, and
neither book states it, so no chunk of text answers it. The same holds for "what is this document for?",
"who is it written for?" and "which of these covers X?".

## The decision

Keep the query pipeline as it is, and give such questions their own data and their own path.

1. **A profile per document**, written next to its other files (`data/uploads/<doc_id>/profile.json`, so it is
   deleted with the document). It holds the name, the page count, the contents list (levels 1 and 2, up to 80
   entries) and the opening text: the pages where the preface or introduction starts, found through the
   contents list, else by the heading, skipping the contents page; else the first pages after the title page.
   It is built from text that extraction already produced, so it needs no model, works when the model tunnel is
   down, and cannot contain anything the document does not say.
2. **A separate answer step** (`rag/query/about.py`) that shows the model the profiles of the chosen documents
   and asks it to describe or compare them, citing `[D1]`, `[D2]`. It has its own prompt. `SYSTEM_PROMPT` in
   `rag/query/prompt.py` is untouched, so the golden-set results stay comparable.
3. **A separate route**, `POST /v1/ask-about` with `{"question", "doc_ids": [...] | null}`. The page offers it
   as a mode next to the scope: "about their content" or "about the documents themselves". The caller chooses;
   nothing guesses.

## Why not the alternatives

- **Route automatically (intent classification).** It adds a classifier that can be wrong and must be measured
  first. It is a good later step once the golden questions below exist; the LangGraph case in `rag/README.md`.
- **Put the profile in the search index as a chunk.** It would change what content questions retrieve, and the
  retrieval numbers (hit@5 0.865, mrr 0.663) would move. A separate path leaves them alone.
- **Ask the model to write a summary at upload.** It needs the tunnel at upload time, can state things the
  document does not say, and a summary stored once cannot be corrected by a better prompt. Possible later as an
  addition: profile `version` makes a rebuild automatic.
- **Compare by retrieving per document and answering from each side.** Heavier, and still limited to what the
  passages happen to say about purpose. Worth trying after profiles if the answers are too thin.

## Safety

A profile is text taken from the document, so it is as untrusted as any passage. Before the model sees it:

- the keyword scanner removes parts that look like instructions (the opening text, the title page, each contents
  entry) and the page lists what was left out and why ("left out as instruction-like");
- a profile cannot close its own `<profile>` tag;
- the system prompt says the profile text is data and to ignore instructions inside it;
- the answer goes through the same output filter as every other answer;
- the route takes the owner from `current_owner`, another owner's document is a 404, and nothing is saved, since
  a question over several documents has no single document folder to delete it from.

## Measured

On the two HBase books the original question, which abstained before, now gets a comparison: the Definitive
Guide as the learning book for developers, the Reference Guide as the manual for operators, with page counts
(554 and 904). This was one real question, not a measurement; see below.

## Limits and next steps

- The profile holds only what the first pages and the contents list say. A document with no bookmarks and no
  preface gets a thin profile, and the answer will say what it cannot tell.
- Answers can contain markdown (a table, bold). The page shows them as plain text, on purpose
  (`docs/mcp_risks.md`, section 2).
- Not yet measured: write 4 to 6 golden questions of this kind (compare two documents, purpose, audience, which
  covers X) over two uploaded documents, with the facts each answer must contain, and score them like the
  others. Only then decide on automatic routing.
- Uploads made before profiles existed get theirs the first time they are asked about.
