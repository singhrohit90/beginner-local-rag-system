# Phase 4: Multi-turn evaluation and the default decision - Pattern Map

**Mapped:** 2026-10-22
**Files analyzed:** 8
**Analogs found:** 7 / 8

Caveat: `rag/query/rewrite.py`, `rag/query/history.py` and the `RAG_REWRITE` wiring in `rag/api/main.py` do not exist yet (Phase 3 is planned, not executed; grep for `RAG_REWRITE` in `rag/api/main.py` finds nothing). Phase 4 plans must depend on Phase 3 landing; signatures come from `03-01-PLAN.md`, not code.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `data/golden/ddia_conversations.jsonl` | data | batch | `data/golden/ddia_questions.jsonl`, `data/golden/conversations_draft.jsonl` | role |
| `rag/observe/golden_conversations.py` | model/loader | file-I/O | `rag/observe/golden.py` | exact |
| `rag/experiments/conversation.py` | experiment | batch | `rag/experiments/retrieval.py` (+ `answer.py`, `about.py`) | role |
| `docs/chat_memory_eval.md` | doc | n/a | none (see No Analog) | none |
| `tests/test_golden_conversations.py` | test | file-I/O | `tests/test_about_experiment.py` (golden-load test) | role |
| `tests/test_conversation_experiment.py` | test | batch | `tests/test_about_experiment.py` | role |
| `rag/api/main.py` (default flip only) | config | request-response | its own `build_default_service` | exact |
| `.env.example` | config | n/a | itself | exact |

## Pattern Assignments

### `rag/observe/golden_conversations.py` (loader, file-I/O)

**Analog:** `rag/observe/golden.py` lines 1-80. Do not edit it.

Copy: module docstring on PDF pages, a `CATEGORIES` set (like `QUESTION_TYPES`, lines 12-22), a dataclass with `field(default_factory=list)` and trailing-comment per field, `validate()` raising `ValueError(f"{self.id}: ...")`, and the loader loop (lines 65-80):

```python
def load_golden(path: Path) -> List[GoldQuestion]:
    questions = []
    seen = set()
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            raw = json.loads(line)
            raw["gold_pages"] = [tuple(r) for r in raw.get("gold_pages", [])]
            q = GoldQuestion(**raw)      # unknown keys -> TypeError from the constructor
            q.validate()
            if q.id in seen:
                raise ValueError(f"{path}:{line_no}: duplicate id {q.id}")
```

Deltas: use `@dataclass(frozen=True)` (project convention for value objects), so convert `turns` and `gold_pages` to tuples before construction. `GoldQuestion` is a plain `@dataclass`, so frozen needs list-to-tuple conversion in the loader. Wrap `TypeError` from unknown keys into `ValueError(f"{path}:{line_no}: ...")` since D-04 says reject unknown keys. Validate: category in the 5 names, `expect in ("answer","clarify")`, `message` non-empty, page ranges `start >= 1 and end >= start`, `gold_pages` required when `expect == "answer"`, `review in {"approved","pending-human"}`. Typing: `List`/`Tuple`/`Optional`, no `|`.

### `rag/experiments/conversation.py` (experiment, batch)

**Analog:** `rag/experiments/retrieval.py` (pipeline and table), `rag/experiments/about.py` (pure functions plus thin `main`, rows, summarise, print_table, runs output), `rag/experiments/answer.py` (`score_safely`, `RUNS_DIR`, `ThreadPoolExecutor`).

Structure to copy from `about.py` lines 1-10, 71-108: module docstring with usage lines and the scoring caveat (put the D-07 shipping rule here too); pure functions `run_*`, `summarise`, `print_table` importable by tests; `main()` with argparse + `setup_logging()`; heavy imports (`get_llm`) inside `main` (about.py line 85) so tests load without backends; `get_llm(spec, cache_dir=None)`; output to `RUNS_DIR / "conversation" / <timestamp>`, `json.dumps(..., indent=2)`; `if __name__ == "__main__": main()`.

Imports to reuse:
```python
from rag.common.config import GOLDEN_DIR, PROCESSED_DIR, RUNS_DIR
from rag.common.embed import get_embedder
from rag.common.log import setup_logging
from rag.common.secrets import setting
from rag.ingestion.chunking.base import load_chunkset
from rag.ingestion.index import get_index
from rag.query.configs import CONFIGS
from rag.query.pipeline import RetrievalPipeline
from rag.observe.generation_quality.judge import judge_facts
from rag.observe.retrieval_quality.metrics import hit_rate_at_k, recall_at_k, reciprocal_rank
```

Pipeline build (retrieval.py lines 110-118, 124-130), memory store only:
```python
chunkset = load_chunkset(args.chunks_dir, name)
index = get_index(chunkset, embedder, args.variant, args.rebuild)
pipeline = RetrievalPipeline.from_chunkset(chunkset, index, embedder, reranker, stem=args.bm25_stem)
... pipeline.run(q.id, q.question, config)   # returns a Trace
```
Pass `semantic` and `CONFIGS["weighted"]` by default. Argparse flags to mirror: `--chunkers`, `--configs`, `--embedder` (default `st:sentence-transformers/all-mpnet-base-v2`), `--chunks-dir`, `--golden` (default `GOLDEN_DIR / "ddia_conversations.jsonl"`), `--variant`. Add `--answers`, `--rewriter` (default `setting("RAG_REWRITER","ollama:qwen2.5:7b")`), `--judge` (as about.py line 78).

Scoring: use `metrics.hit_rate_at_k/recall_at_k/reciprocal_rank` on the final-stage hits (verify how `run_eval` extracts final hits and applies `strict_trace`, `run_eval.py`, so the arms use strict evidence-aware relevance like the invariant; `strictify` needs `evidence_terms`, which conversations lack, so decide whether to reuse the single-turn question's terms or use page overlap with that caveat and record it). Per-row error handling: `try/except Exception as err` at the row level that records `error=f"{type(err).__name__}: {err}"` (about.py lines 32-38), because a rewriter fallback must count as a failure, not "off".

Answer scoring: `score_safely` pattern from `answer.py` line 37-46 (falls back to `score_answer(q, trace, None)` when the judge errors); the about.py judge branch (lines 40-45) shows `judge_facts(judge, answer, key_facts)` returning `.correct/.stated/.missing`.

Regression arm (D-09): iterate `load_golden(GOLDEN_DIR / "ddia_questions.jsonl")` filtered to `answerable`, assert gate skips and hit lists equal `off` exactly (compare chunk ids lists).

Rewrite call: signature from `03-01-PLAN.md` (`rewrite_question`, `needs_rewrite`, `RewriteResult`); read it before planning. Never import `rag.api`.

### `tests/test_conversation_experiment.py` (test, batch)

**Analog:** `tests/test_about_experiment.py` lines 1-70. Copy: one-line module docstring, `fake_judge(stated_for)` helper (lines 13-18, or import it: `from tests.test_about_experiment import fake_judge`), `FakeLLM(reply)` for rewriter and judge, small offline fixtures (`HashingEmbedder`, tiny chunkset; see `tests/test_retrieval.py` for a chunkset builder, not read here). Tests to mirror: golden file loads and `n` thresholds; smoke run on 3-item fixture asserting all four arms (`off`, `on`, `oracle`, `concat`) and paired counts; fallback counted as failure; table prints via `capsys` (lines 63-70); regression arm equals `off`; summarise with no judge gives `None` not zero (lines 51-60). Per CLAUDE.md, the timing/tunnel-dependent paths must not run in tests.

### `tests/test_golden_conversations.py` (test, file-I/O)

**Analog:** `tests/test_about_experiment.py` lines 21-25 (loads the committed file, checks count, unique ids, key facts) plus `tests/test_golden_verify.py` (not read; check it for how gold pages are verified against page text and reuse for `gold_pages`). Use `tmp_path` JSONL files to assert the rejects: unknown key, bad range, unknown category, duplicate id. Assert the committed set: every category >= 4, each row has `review`, `load_golden` still loads `ddia_questions.jsonl` unchanged.

### `data/golden/ddia_conversations.jsonl`

Schema from CONTEXT D-01. Reuse `gold_pages`/`key_facts` from `data/golden/ddia_questions.jsonl` where the standalone form matches; seed from `data/golden/conversations_draft.jsonl` (Phase 3 output, may not exist yet). Keep `"review": "pending-human"` on authored rows.

### `rag/api/main.py` (default flip, only if the rule passes)

Edit only the `RAG_REWRITE` read in `build_default_service` (added by Phase 3 plan 03-04; not present now). Change the unset default from off to on; own commit after the results commit. `.env.example` gets the matching documented line, no values for secrets.

## Shared Patterns

- Logging: `setup_logging()` from `rag.common.log`; library code uses `logging.getLogger("rag.experiments")`; `print()` only for tables.
- Settings: `setting("NAME", default)` from `rag.common.secrets`; never read `.env` directly.
- No LLM disk cache: `get_llm(spec, cache_dir=None)` for rewriter, judge, generator (about.py line 88).
- Typing: `typing` generics only; double quotes; lines <= 120; no `from __future__`.
- Imports fully qualified from `rag`; heavy/backends imported inside `main`.
- Report output under gitignored `RUNS_DIR`; only `docs/chat_memory_eval.md` is committed.

## No Analog Found

| File | Reason |
|---|---|
| `docs/chat_memory_eval.md` | No existing results doc; check `docs/models.md` for tone and table style. First heading must be "Shipping rule (committed before the first run)" in its own earlier commit. |
| Paired win/tie/loss, noise band `max(8, 300/n)`, oracle-gap-closed, gate precision/recall, p50/p95 latency | No existing code; write as pure functions in `conversation.py` and unit-test them. |

## Metadata

**Analog search scope:** `rag/observe/`, `rag/experiments/`, `tests/test_about_experiment.py`, `rag/api/main.py` (grep).
**Files read:** golden.py, about.py, test_about_experiment.py, retrieval.py (part); grep of answer.py, metrics.py.
**Not read:** tests/test_retrieval.py, tests/test_golden_verify.py, run_eval.py, judge.py.
**Pattern extraction date:** 2026-10-22
