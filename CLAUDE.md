# Project notes for Claude

Read `rag/README.md` ("Layout" and "Read in this order") before changing code.

## Commands
- Run the tests with `python -m pytest tests -q`; the OpenSearch tests skip when the database is down, and the full run takes about 3 minutes on a quiet machine and 10 when other test runs share it. List them without running with `python -m pytest tests --collect-only -q`.
- Run `/code-review ultra <base commit>` on a diff under 500 files and 8,000 changed lines; a bigger history is refused, so make local branches at the ends of windows (`git branch review/<name> <commit>`) and pass each window's starting commit.
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
- Stream answers only through `StreamGuard` in `rag/query/guard.py` and show them as text; text already sent cannot be recalled, and the output filter is a pattern list that review has bypassed repeatedly.

## Working in this repo
- Do not push or open a pull request unless asked.
- Write commit messages to a file and run `git commit -F <file>`; the hook blocks any command containing an email address, and the trailer has one.
- Never name `rag/common/llm.py` or `tests/test_vllm.py` in a command or search, and never glob `tests/` or `rag/common/`; the hook flags them as secrets (a false positive), and only a prompt that STARTS with `[allow-secret]` and names the file lifts it (it did not work for files under `.claude/worktrees/`, even with `[allow-all]`; the user then disabled the plugin with `/plugin` and `/reload-plugins`).
- Do not read `HANDOFF.md` with the Read tool (the commit trailer's address trips the PII hook); change it with `sed -i`, or `rm` it and write a new one with the Write tool, without the literal address.
- Write multi-file patch scripts with the Write tool and run them; long shell heredocs get truncated, and the shell halves backslashes, so edit backslash-heavy text with the Edit tool.
- Prove a new regression test fails on the old code: `git stash push -q -m <unique-tag> -- rag`, run the test, then `git stash pop -q` (the stash stack is shared by every worktree, so always give it a unique message).
- Create worktrees for parallel agents yourself, from the feature branch: `git worktree add -b work/<name> .claude/worktrees/<name> <branch>`; the harness default cuts them from `main`, which may lack the code. Merge them with `git merge --no-ff -F <file>`, then `git worktree remove --force` and `git branch -D` only after `git merge-base --is-ancestor <branch> <target>` (`git branch -d` checks the checked-out branch, not the target).
- Put code-review fixes on a new branch cut from `main` and open a separate PR, so the diff shows what the review caught.
- Run a script that uses `multiprocessing` (the extraction sandbox spawns children) from a file with `if __name__ == "__main__"`, never from stdin; spawn fails on Windows with `<stdin>`.
- Make a timing-sensitive test wait for the state it checks (an Event, or polling a condition with a 30 s ceiling), not a fixed sleep; parallel agents load this machine and fixed waits were flaky.
- Test "connection refused" by patching `urllib.request.urlopen` to raise `URLError(ConnectionRefusedError())`; a closed local port times out on this machine instead of being refused.
- Keep `interview/` notes honest: label each point built, designed, general or not measured, and cite only real file paths and numbers recorded in the repo.

## flow runs
- GSD (`/gsd-*`) owns structure, planning and execution; superpowers owns brainstorming for gaps, TDD and verification; `flow` owns the two gates and calls both explicitly.
- A `/flow` run pushes `flow/<slug>` after each merged wave and opens the PR at the merge gate; `main` is never pushed by a run.
- Verification gate for this repo: `python -m pytest tests -q` (baseline 591 passed, 2 skipped); `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` (hit@5 0.865, mrr 0.663); `python -m rag.common.llm_check` (needs tunnel: yes; tunnel session: set on first use); output saved under `.planning/runs/<id>/`.
