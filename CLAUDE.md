# Project notes for Claude

Read `rag/README.md` ("Layout" and "Read in this order") before changing code.

## Commands
- Run the tests with `python -m pytest tests -q`; the OpenSearch tests skip when the database is down, and the full run takes about 2 minutes with it up.
- Start the app with `RAG_STORE=opensearch python -m uvicorn rag.api.main:app --port 18642`; port 8000 is taken by another service on this machine.
- Start OpenSearch with `cat docker-compose.yml | wsl -d Ubuntu-24.04 -- docker compose -f - up -d opensearch`; WSL cannot see the Windows drive, so pass the file on stdin.
- Keep WSL awake with a background `wsl -d Ubuntu-24.04 -- sleep 100000`; WSL stops when idle and takes the OpenSearch container with it.
- Check the model server with `python -m rag.common.llm_check`; "connection refused" on 127.22.10.1:30007 means the PuTTY tunnel is down and the user must reconnect it.
- Check retrieval is unchanged after a refactor with `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` (hit@5 0.865, mrr 0.663; update these numbers if the golden set or chunkers change).

## Secrets and files
- Keep `GEMINI_API_KEY` only in the gitignored `.env`; `.env.example` is the committed template with no values.
- Never read or print `.env`; the sensitive-canary hook blocks it.
- Treat `data/raw/`, `data/processed/`, `data/uploads/` and `runs/` as gitignored; `data/golden/` is committed.

## Behaviour that must not drift
- Keep `SYSTEM_PROMPT` in `rag/query/prompt.py` word for word; the golden-set results and LLM cache depend on it. Uploads use `DOCUMENT_SYSTEM_PROMPT`.
- Use PDF page numbers everywhere (for the DDIA book, printed page + 22).
- Treat gaps under about 8 points as noise on the 37 answerable golden questions (one question is 2.7 points).
- Do not retry the holistic correctness judge or page-overlap-only relevance; they were unreliable. Use the per-question fact checklist and strict evidence-aware relevance.
- Never use the LLM disk cache (`get_llm(spec, cache_dir=None)`) for uploaded documents; it would keep their text after a delete.

## Security conventions
- Take the caller only from `current_owner` in `rag/api/main.py`, never from a header or request field.
- Return 404, not 403, for another owner's document, and filter by `Scope.owner` inside the store, not after the search.
- Keep untrusted text in the DOM with `textContent`, never `innerHTML`, in `rag/api/static/index.html`.
- Qualify upload chunk ids as `<doc_id>:<chunk_id>`; ids must be unique within an owner.

## Working in this repo
- Do not push or open a pull request unless asked.
- Write commit messages to a file and run `git commit -F <file>`; the hook blocks any command containing an email address, and the trailer has one.
- Never name `rag/common/llm.py` or `tests/test_vllm.py` in a command or search; the hook flags them as secrets (a false positive), and only the user's `[allow-secret]` lifts it.
- Write multi-file patch scripts with the Write tool and run them; long shell heredocs get truncated, and the shell halves backslashes, so edit backslash-heavy text with the Edit tool.
- Prove a new regression test fails on the old code: `git stash push -q -- rag`, run the test, then `git stash pop -q`.
