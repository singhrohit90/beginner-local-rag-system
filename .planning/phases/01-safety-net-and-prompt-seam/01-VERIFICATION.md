---
phase: 01-safety-net-and-prompt-seam
verified: 2026-10-25T00:00:00Z
status: human_needed
score: 3/4 must-haves verified
covered_files:
  - .planning/phases/01-safety-net-and-prompt-seam/01-01-PLAN.md
  - .planning/phases/01-safety-net-and-prompt-seam/01-01-SUMMARY.md
  - .planning/phases/01-safety-net-and-prompt-seam/01-02-PLAN.md
  - .planning/phases/01-safety-net-and-prompt-seam/01-02-SUMMARY.md
  - .planning/phases/01-safety-net-and-prompt-seam/01-03-PLAN.md
  - .planning/phases/01-safety-net-and-prompt-seam/01-03-SUMMARY.md
  - .planning/phases/01-safety-net-and-prompt-seam/01-04-PLAN.md
  - .planning/phases/01-safety-net-and-prompt-seam/01-04-SUMMARY.md
  - .planning/phases/01-safety-net-and-prompt-seam/01-05-PLAN.md
  - .planning/phases/01-safety-net-and-prompt-seam/01-05-SUMMARY.md
  - .planning/phases/01-safety-net-and-prompt-seam/01-06-PLAN.md
  - .planning/phases/01-safety-net-and-prompt-seam/01-06-SUMMARY.md
  - .planning/phases/01-safety-net-and-prompt-seam/01-07-PLAN.md
  - .planning/phases/01-safety-net-and-prompt-seam/01-07-SUMMARY.md
  - docs/models.md
  - rag/query/generate.py
  - rag/query/history.py
  - rag/query/pipeline.py
  - rag/query/prompt.py
  - rag/security/defenses.py
  - tests/snapshots/prompts/golden_user_prompt_digests.json
  - tests/test_history.py
  - tests/test_prompt_snapshot.py
covered_digest: "v3:sha256:f961878a09d136ef55ce0e5ca30e754d418e07c66e32708a40faa08a76f777c5"
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Reconnect the PuTTY tunnel to 127.22.10.1:30007, then run the one-off command recorded in docs/models.md (Context window) to read max_model_len, and write the number into docs/models.md and into MODEL_CONTEXT_TOKENS in rag/query/history.py (currently the 8192 floor)."
    expected: "The command prints (model id, max_model_len); docs/models.md names the number, the model id and the date; test_history.py's check of MODEL_CONTEXT_TOKENS against the Context window section still passes; the D-11 worst-case budget test still fits."
    why_human: "ROADMAP success criterion 4 says max_model_len is read and recorded. The tunnel was down on 2026-10-24 (plan 01-02) and is still down now (python -m rag.common.llm_check printed 'cannot reach the model server ... actively refused it'). Only the user can reconnect the tunnel. Plan 01-02 and D-13 allowed the dated 'not read' record as a fallback, so Phase 2 inherits an 8192 floor, not a measurement."
  - test: "Confirm the gitignored .env does not set RAG_NONCE_KEY (judgment-tier prohibition of plan 01-01, 'unverified-prohibition: human review recommended')."
    expected: "No RAG_NONCE_KEY line in .env. The verifier did not open .env (repo rule). In every committed file RAG_NONCE_KEY appears only in comments or docs, and every snapshot test fixes rag.security.defenses._NONCE_KEY with monkeypatch, so the tests pass whatever .env holds."
    why_human: "The verifier must not read .env; this is a non-authoritative verdict on a judgment-tier prohibition."
---

# Phase 1: Safety net and prompt seam Verification Report

**Phase Goal:** As a system owner, I want to pin single-turn prompts and retrieval numbers with a committed snapshot test and recorded invariants before any shared function is edited, so that every later change can prove a plain question still produces the same prompt bytes, the same hit@5 0.865 and the same mrr 0.663.
**Verified:** 2026-10-25
**Status:** human_needed
**Re-verification:** No, initial verification

## Goal Achievement

### Observable Truths (ROADMAP success criteria)

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | A snapshot test, committed on the unedited prompt code before any prompt builder is touched, fixes the prompt bytes for 3 styles x 2 subjects x none / single-page / page-range (plus mix) passages, plus the golden-set questions | VERIFIED | `tests/test_prompt_snapshot.py` plus 25 files under `tests/snapshots/prompts/` (24 text cases + `golden_user_prompt_digests.json`, 45 digests) were committed alone in `4b73d94`. `git merge-base --is-ancestor 4b73d94 edd8b72` is true (edd8b72 is the first seam edit), and `git diff --stat 853f021 4b73d94 -- rag` is empty. `git log -- tests/snapshots` lists only `4b73d94`; no `.gitattributes`. The test only reads fixtures (no regenerate switch, no write) and fixes `_NONCE_KEY` in an autouse fixture. |
| 2 | After the seam edits, builders called with an explicit empty history return the same bytes as with no history argument, and both equal the snapshot; no header or blank line is added | VERIFIED | `git diff 853f021 -- rag/query/prompt.py rag/query/generate.py rag/security/defenses.py rag/query/pipeline.py` read in full: `history_block: str = ""` is a trailing keyword, and when it is empty each builder runs its old return expression unchanged (`build_user_prompt`, `spotlight_user_prompt` keep the original f-strings; naive and standard forward the same). A non-empty block goes only between the passages and `Question:`. Ran `python -m pytest tests/test_prompt_snapshot.py tests/test_history.py -q`: 111 passed (26 snapshot + 52 seam + 33 history). The system-prompt fingerprint recomputed as `b69624ed9d1a5781`, as planned. |
| 3 | `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` prints hit@5 0.865 and mrr 0.663, `python -m pytest tests -q` reports the baseline, and both are recorded | VERIFIED | Re-ran both. Retrieval: `semantic      weighted        0.568  0.865  0.797  0.663   0.677    0.919     62  lost_at_context:3, lost_at_fuse:1, retrieval_miss:1, unanswerable:8`. Full suite: `702 passed, 2 skipped in 197.93s (0:03:17)`. This is above the old 591 passed, 2 skipped because 111 tests were added (593 + 111 = 704 collected), with the 593 pre-phase tests still collected. The values are recorded in `01-07-SUMMARY.md` and the `.planning/STATE.md` standing-constraint line (`pytest baseline after Phase 1 is 702 passed, 2 skipped`). Note that the roadmap's literal "591 passed" is the pre-phase number; the new total is the correct baseline. |
| 4 | The model server's context window (`max_model_len`) is read once and written into `docs/models.md`, so Phase 2 caps rest on a recorded number | UNCERTAIN (human_needed) | `docs/models.md` has a `## Context window` section, but it records "`max_model_len` not read on 2026-10-24: tunnel down (connection refused on 127.22.10.1:30007 ...)", the 3600-token output limit and the 8192 floor, and it carries the re-read command. `rag/query/history.py` uses `MODEL_CONTEXT_TOKENS = 8192` with a floor comment, and `.planning/STATE.md` line 78 carries the Phase 2 blocker. This is exactly the D-13 fallback that plan 01-02 allowed, and the check run today (`python -m rag.common.llm_check`) still fails with connection refused. The roadmap wording (a recorded number) is not met until the tunnel is up; see the human verification items. |

**Score:** 3/4 truths verified (0 present-but-behavior-unverified)

### Plan-level must-haves (all seven plans)

| Plan | Truth | Status | Evidence |
| ---- | ----- | ------ | -------- |
| 01-01 | 24 case tests + 45 golden digests; D-03 no regenerate; D-05 nonce fixed; D-04 snapshot commit alone and before edits | VERIFIED | `4b73d94` holds 26 files (the test and 25 fixtures) and nothing else; `test_snapshot_directory_holds_exactly_the_committed_cases` asserts 24 cases. Retrieval run 1 recorded in the 01-07 section below. |
| 01-02 | `## Context window` section with the dated not-read record, 3600 output limit, 8192 floor; STATE.md blocker line | VERIFIED (as the D-13 fallback) | `docs/models.md` lines 22-24, `.planning/STATE.md` line 78. See truth 4 above for the unmet number. |
| 01-03 | `history_block` seam in the four builders and `RagPipeline.answer/stream`; empty is byte-identical; system prompts unchanged | VERIFIED | Diff read in full (above). `RagPipeline.run` and the constructor are untouched. Fingerprint matches. |
| 01-04 | Empty / None / omitted give identical bytes equal to the snapshot; block position; pipeline forwarding; 52 tests fail on pre-seam code | VERIFIED | Tests exist (`test_empty_history_equals_no_history_equals_snapshot`, `test_history_block_position`, `test_pipeline_answer_and_stream_forward_history_block`, `test_answer_from_context_forwards_history_block`) and pass. The SUMMARY records the fail-first lines (`24 failed`, `28 failed`, TypeError on `history_block`). |
| 01-05 | `rag/query/history.py` is pure, has `HistoryTurn`, `window`, `neutralize`, `render_block` and the D-10 constants; reuses `RULES`, `scan_text`, `filter_output`, `BLOCKED`, `_CITATION` | VERIFIED | Read the file in full: constants 6 / 400 / 40 / 60 / 50 / 1.5 / 8192; no I/O, owner or LLM; reuse imports as planned; `render_block([])` returns `""`. Not imported from `rag/api` (Phase 1 boundary). |
| 01-06 | History unit tests and the D-11 worst-case budget test | VERIFIED | `tests/test_history.py` passes (33 tests). |
| 01-07 | Retrieval run 2, full suite, phase checks, STATE.md baseline | VERIFIED | Independently reproduced (truth 3). |

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `tests/test_prompt_snapshot.py` | Snapshot, seam and pipeline tests | VERIFIED | Exists, substantive, passes. |
| `tests/snapshots/prompts/*` | 24 case files + digest manifest | VERIFIED | 25 files; last changed by `4b73d94`. |
| `rag/query/prompt.py`, `rag/query/generate.py`, `rag/security/defenses.py`, `rag/query/pipeline.py` | Seam | VERIFIED | Wired: `RagPipeline.answer` -> `answer_from_context` -> `build_prompts` -> builders; `stream` -> `build_prompts`. |
| `rag/query/history.py` | Pure helpers | VERIFIED (not yet called in production, by design) | Imported by `tests/test_history.py`; Phase 2 wires it. |
| `docs/models.md` `## Context window` | Recorded context window | PARTIAL | Contains the not-read record, not the number. |
| `.planning/STATE.md` | Baseline line | VERIFIED | Line 82. |

### Key Link Verification

| From | To | Via | Status |
| ---- | -- | --- | ------ |
| `tests/test_prompt_snapshot.py` | `rag/query/generate.py` | `build_prompts(...)` in `render_case` | WIRED |
| `rag/query/pipeline.py` | `rag/query/generate.py` | `answer_from_context(..., history_block=...)`, `build_prompts(..., history_block=...)` | WIRED |
| `rag/query/generate.py` | `rag/security/defenses.py` / `rag/query/prompt.py` | `history_block=history_block` forwarded in all three styles | WIRED |
| `rag/query/history.py` | `rag/query/guard.py`, `rag/query/generate.py` | `from rag.query.guard import BLOCKED, RULES, filter_output, scan_text`; `from rag.query.generate import _CITATION` | WIRED |
| `tests/test_history.py` | `docs/models.md` | `MODEL_CONTEXT_TOKENS` checked against the Context window section | WIRED |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Snapshot, seam and history tests | `python -m pytest tests/test_prompt_snapshot.py tests/test_history.py -q` | 111 passed in 0.46s | PASS |
| Retrieval unchanged | `python -m rag.experiments.retrieval --chunkers semantic --configs weighted` | hit@5 0.865, mrr 0.663 | PASS |
| Full suite | `python -m pytest tests -q` | 702 passed, 2 skipped in 197.93s | PASS |
| System prompts unchanged | sha256 of the four prompt strings, first 16 hex | `b69624ed9d1a5781` | PASS |
| Model server reachable | `python -m rag.common.llm_check` | connection refused (tunnel down) | SKIP (human) |

### Prohibition Checks

| Prohibition | Tier | Verdict |
| ----------- | ---- | ------- |
| No edit of the four seam files before the snapshot commit (01-01) | test | Held: no `rag` diff between `853f021` and `4b73d94`. |
| No regenerate switch; no `.gitattributes`; snapshot commit holds only test and fixtures (01-01) | test | Held. |
| No `RAG_NONCE_KEY` set in env or file (01-01) | judgment | Non-authoritative: not set in any committed file (comments and docs only); `.env` not opened. Flagged `unverified-prohibition: human review recommended`. |
| System prompt wording unchanged (01-03) | test | Held (fingerprint). |
| Nothing under `rag/api` or `rag/common` changed since `853f021` (01-03, 01-05, 01-07) | test | Held: `git diff --name-only 853f021 HEAD -- rag/api rag/common` is empty. Only the five expected files differ under `rag/`. |
| No CLAUDE.md edit (01-07) | test | Held per the SUMMARY check; `git status` shows only `.planning/config.json` and `.planning/state.json` uncommitted. |
| No new dependency; no keyword list or second marker regex in `neutralize` (01-05) | test | Held on reading `rag/query/history.py`. |

### Probe Execution

No probes declared. SKIPPED.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| PRMT-02 | 01-01 through 01-07 (all declare `requirements: [PRMT-02]`) | With no history the produced prompt is byte-identical to today's (snapshot committed before the first edit) | SATISFIED | Truths 1 and 2. REQUIREMENTS.md maps PRMT-02 to Phase 1 and no other requirement to Phase 1, so there are no orphaned IDs. (REQUIREMENTS.md still shows PRMT-02 as unchecked; the orchestrator should tick it.) |

### Anti-Patterns Found

None. No TBD / FIXME / XXX / TODO in `rag/query/history.py`, `tests/test_history.py` or `tests/test_prompt_snapshot.py`. No stubs: the empty-history branches are real byte-identical paths, not placeholders.

### Human Verification Required

1. **Read max_model_len through the tunnel.** Test: reconnect the PuTTY tunnel to 127.22.10.1:30007, run the one-off command in `docs/models.md` (Context window), and record the number in `docs/models.md` and in `MODEL_CONTEXT_TOKENS` (`rag/query/history.py`). Expected: the command prints (model id, max_model_len); the docs name the number, model id and date; `tests/test_history.py` still passes. Why human: the tunnel is down; only the user can reconnect it. This can also be done at the start of Phase 2, where the plan already schedules it.
2. **Judgment-tier prohibition (01-01): `.env` must not set `RAG_NONCE_KEY`.** Why human: the verifier does not read `.env`; non-authoritative verdict above.

### Gaps Summary

No failing must-have. The one open item is ROADMAP success criterion 4: the context window number was not recorded because the model server tunnel is down. Plan 01-02 sanctioned the dated "not read" record with an 8192-token floor, and the floor is recorded in the docs, in `MODEL_CONTEXT_TOKENS` and in STATE.md, so Phase 2 can proceed once the number is read and D3 pinned. All other criteria were independently reproduced.

## Invariant record

Phase verifier: copy this "Invariant record" section verbatim into `01-VERIFICATION.md` (D-14).

### Retrieval invariant (D-15)

Command: `python -m rag.experiments.retrieval --chunkers semantic --configs weighted`. This command never builds a prompt or calls an LLM, so it proves retrieval (and that the edited `rag.query.pipeline` imports) only; the prompt proof is the snapshot test (RESEARCH Pitfall 7).

Run 1 of 2 (before the seam), 2026-10-25, HEAD `4b73d94`:

```
chunker       config          hit@1  hit@5  rec@5    mrr  ndcg@5  cand@30   ms/q  failures
semantic      weighted        0.568  0.865  0.797  0.663   0.677    0.919     59  lost_at_context:3, lost_at_fuse:1, retrieval_miss:1, unanswerable:8
```

Run 2 of 2 (after the seam), 2026-10-25, HEAD `c82b0a3`:

```
chunker       config          hit@1  hit@5  rec@5    mrr  ndcg@5  cand@30   ms/q  failures
semantic      weighted        0.568  0.865  0.797  0.663   0.677    0.919     76  lost_at_context:3, lost_at_fuse:1, retrieval_miss:1, unanswerable:8
```

Every column except ms/q (timing) is identical.

### Pytest (D-14)

OpenSearch: up (`urllib.request.urlopen('http://127.0.0.1:9200', timeout=3)` printed `opensearch up`), 2026-10-25, HEAD `c82b0a3`.

- Before Phase 1: `591 passed, 2 skipped` (593 collected)
- After Phase 1: `python -m pytest tests -q` -> `702 passed, 2 skipped in 207.83s (0:03:27)`
- `python -m pytest tests --collect-only -q --ignore=tests/test_prompt_snapshot.py --ignore=tests/test_history.py` -> `593 tests collected in 1.05s`
- `python -m pytest tests --collect-only -q` -> `704 tests collected in 1.12s`

### Phase checks

```
$ python -c "...sha256(SYSTEM_PROMPT+DOCUMENT_SYSTEM_PROMPT+SPOTLIGHT_ADDENDUM+NAIVE_SYSTEM_PROMPT)[:16]"
b69624ed9d1a5781

$ git diff --name-only 853f021 -- rag
rag/query/generate.py
rag/query/history.py
rag/query/pipeline.py
rag/query/prompt.py
rag/security/defenses.py

$ test ! -e .gitattributes && echo "no .gitattributes"
no .gitattributes

$ git log --format='%h %s' -1 -- tests/snapshots
4b73d94 test(01-01): pin single-turn prompt bytes before the prompt seam

$ git diff --quiet 853f021 -- CLAUDE.md .claude/CLAUDE.md; echo $?
0

$ grep -cE 'pytest baseline after Phase 1 is [0-9]+ passed' .planning/STATE.md
1
```

Nothing under `rag/api` or `rag/common` changed since `853f021`; the fingerprint matches; the fixtures were last changed by the 01-01 commit.


---

_Verified: 2026-10-25_
_Verifier: Claude (gsd-verifier)_
