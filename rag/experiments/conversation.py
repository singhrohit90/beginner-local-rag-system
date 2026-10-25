"""Measure query rewriting on the multi-turn golden set: retrieval with rewriting off, on, against an oracle
(the human-written standalone question) and against the cheap concat baseline, every arm on the same
teacher-forced history, scored by strict evidence-aware retrieval; answers are scored by the fact checklist.

    python -m rag.experiments.conversation --check-set
    python -m rag.experiments.conversation --repeats 3 --answers
    python -m rag.experiments.conversation --regression-only
    python -m rag.experiments.conversation --check-rule

Shipping rule (committed before the first run)

This section is committed on its own, before any run of `python -m rag.experiments.conversation` over
`data/golden/ddia_conversations.jsonl`, and is never edited afterwards. The experiment module
`rag/experiments/conversation.py` repeats this text in its docstring, and it refuses to run the `on` arm unless this
file is committed, clean, and this section is unchanged since the file's first commit.

Scored items. n is the number of items in `data/golden/ddia_conversations.jsonl` with `expect == "answer"`. Clarify
items (`expect == "clarify"`) are scored apart and are not in n.

Per item. For item i, `off_i` and `on_i` are strict, evidence-aware hit@5 (0 or 1) of the `context` stage with the
`semantic` chunks and the `weighted` config, on the teacher-forced history of the item (its fixed prior turns, never
model-generated answers). `off` retrieves on the raw message; `on` retrieves on the question the Phase 3 rewriter
returns. When the rewriter returns `clarify` for an answer-expected item, `on_i = 0` (a false clarify: the user got
no answer). When the rewriter falls back, retrieval runs on the raw message and the fallback is a counted failure in
(e), never "off".

Counts. wins = the number of items with `on_i = 1` and `off_i = 0`; losses = the number with `on_i = 0` and `off_i =
1`; net = wins - losses; gain = 100 * net / n points; band = max(8, 300 / n) points (three items' worth, never below
the project's 8-point band).

Rewriting ships default-on only if all of these hold:

- (a) gain > band, strictly. At n = 30 the band is 10.0 points and net = 3 gives exactly 10.0, which does not exceed
  it.
- (b) net >= 3. (b) is implied by (a) for every n and is recorded for the reader.
- (c) no item in `standalone_in_conversation` has `on_i < off_i`.
- (d) in the regression arm, all 37 answerable questions of `data/golden/ddia_questions.jsonl`, each asked as the
  first turn of a conversation with rewriting on, make zero rewriter calls and return the same context chunk ids as
  `off`.
- (e) fallbacks <= 10% of rewriter calls, both counted over the items on which the gate called the rewriter (answer
  and clarify items, the first call per item, repeat 1). With no gate call at all, (e) fails.
- (f) every item in `data/golden/ddia_conversations.jsonl` has `review == "approved"`.

Otherwise rewriting ships off and the numbers are recorded below this section.

Reported, not gating: the one-sided exact sign test p on (wins, losses) (when (a) holds but p >= 0.05 the results
say "clears the project band; weak evidence (sign test p = ...)"); the fraction of the oracle gap closed; the
`concat` baseline; per-category tables; the paired counts of the pronoun and constraint items alone; answer-level
results; instability across repeats. The rule is evaluated on repeat 1; later repeats are reported as instability
only.

Decisions taken by the same numbers, written before any run:

- Rewriter model (D-10). With a second rewriter measured on the same items, choose the second only if its `on` hit@5
  exceeds the first's by more than the band; keep the first if it exceeds the second's by more than the band;
  otherwise choose the rewriter with the lower p50 latency. The rule above is then evaluated on the chosen
  rewriter's run. Without a second run the results say "qwen by default, not compared".
- Question slot in the answer prompt (D-11). Keep the rewritten question unless the original-message slot's
  fact-checklist correct rate is higher by more than the band (computed as above from the number of judged items).
  Without answer scoring the slot stays the rewritten question and is recorded as unmeasured.
- Judge (D-12). Answers are scored only with the per-question fact checklist (`judge_facts`); an answer-level
  difference inside the band never changes a default, and the results say when the judge and the rewriter are the
  same model.

The results end with exactly one line that starts `Decision: ships on` or `Decision: ships off`.
"""

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from rag.common.config import GOLDEN_DIR, PROCESSED_DIR, RUNS_DIR
from rag.common.embed import get_embedder
from rag.common.log import setup_logging
from rag.common.secrets import setting
from rag.common.trace import Trace
from rag.ingestion.chunking.base import load_chunkset
from rag.ingestion.index import get_index
from rag.observe.golden_conversations import GoldConversation, load_conversations
from rag.observe.retrieval_quality.metrics import score_hits, strict_trace
from rag.query.configs import CONFIGS, RetrievalConfig
from rag.query.history import HistoryTurn, window
from rag.query.pipeline import RetrievalPipeline

logger = logging.getLogger("rag.experiments.conversation")

CHUNKER = "semantic"  # the chunker and config of the single-turn invariant
CONFIG_NAME = "weighted"
KS = (1, 3, 5, 10, 30)
ARMS = ("off", "on", "oracle", "concat")
FIXED_ASKED_AT = "1970-01-01T00:00:00+00:00"  # teacher-forced turns carry no real time
DOC_NAMES = ("ddia.pdf",)  # the one book the rewriter may name (RESEARCH A3)
DEFAULT_GOLDEN = GOLDEN_DIR / "ddia_conversations.jsonl"
SINGLE_TURN_GOLDEN = GOLDEN_DIR / "ddia_questions.jsonl"
RULE_PATH = "docs/chat_memory_eval.md"
RULE_HEADING = "## Shipping rule (committed before the first run)"
BAND_FLOOR_POINTS = 8.0  # the project's noise band
BAND_ITEM_POINTS = 300.0  # three items' worth of hit@5 points
MIN_NET_WINS = 3
MAX_FALLBACK_RATE = 0.10
PREFLIGHT_TOKENS = 1
NAME_PATTERN = re.compile(r"[A-Za-z0-9_.-]+")


def teacher_history(item: GoldConversation) -> List[HistoryTurn]:
    return [HistoryTurn(t.question, t.answer, FIXED_ASKED_AT) for t in item.turns]


def concat_query(item: GoldConversation) -> str:
    """The cheap baseline: the previous user question, one space, then the message."""
    return item.turns[-1].question + " " + item.message


def score_query(
    pipeline: RetrievalPipeline, config: RetrievalConfig, run_id: str, query: str,
    gold_pages: Sequence[Tuple[int, int]], evidence_terms: Sequence[str],
) -> Tuple[Dict[str, Any], Trace]:
    """Strict evidence-aware hit@5, mrr and recall@5 of the context stage; never page overlap alone."""
    if not evidence_terms:
        raise ValueError(f"{run_id}: no evidence terms; strict relevance needs them")
    trace = pipeline.run(run_id, query, config)
    judged = strict_trace(trace, evidence_terms)
    scores = score_hits(judged.stage("context").hits, gold_pages, KS)
    return (
        {
            "query": query,
            "hit@5": scores["hit@5"],
            "mrr": scores["mrr"],
            "recall@5": scores["recall@5"],
            "chunk_ids": [h.chunk_id for h in trace.stage("context").hits],
        },
        trace,
    )


def _new_row(item: GoldConversation) -> Dict[str, Any]:
    return {
        "id": item.id,
        "category": item.category,
        "expect": item.expect,
        "review": item.review,
        "source_id": item.source_id,
        "expects_rewrite": item.expects_rewrite,
        "arms": {},
        "rewrite": None,
        "clarify": None,
    }


def run_arms(
    pipeline: RetrievalPipeline, config: RetrievalConfig, items: Sequence[GoldConversation],
    arms: Sequence[str], rewriter: Any = None,
) -> Tuple[List[Dict[str, Any]], Dict[Tuple[str, str], Trace]]:
    """One row per item. Every arm sees the same teacher-forced history; only the query string differs."""
    for arm in arms:
        if arm not in ARMS:
            raise ValueError(f"unknown arm {arm!r}")
    rows: List[Dict[str, Any]] = []
    traces: Dict[Tuple[str, str], Trace] = {}
    for item in items:
        row = _new_row(item)
        queries = {"off": item.message, "oracle": item.standalone, "concat": concat_query(item)}
        for arm in arms:
            if arm == "on":
                continue
            if item.expect != "answer":
                row["arms"][arm] = None  # clarify items have no gold pages and never enter a hit@5 mean
                continue
            score, trace = score_query(pipeline, config, f"{item.id}__{arm}", queries[arm], item.gold_pages,
                                       item.evidence_terms)
            row["arms"][arm] = score
            traces[(item.id, arm)] = trace
        rows.append(row)
    return rows, traces


def check_set_summary(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """For authoring (D-02): which pronoun and constraint items the raw message misses."""
    answer = [r for r in rows if r["expect"] == "answer"]
    items = [{"id": r["id"], "category": r["category"], "off": r["arms"]["off"]["hit@5"],
              "oracle": r["arms"]["oracle"]["hit@5"]} for r in answer]
    eligible = [i for i in items if i["category"] in ("pronoun_follow_up", "constraint_follow_up")]
    return {
        "items": items,
        "eligible": len(eligible),
        "discriminating": [i["id"] for i in eligible if i["off"] == 0],
        "oracle_misses": [i["id"] for i in items if i["oracle"] == 0],
        "controls": [i["id"] for i in items if i["off"] == i["oracle"]],
    }


def report_dir(name: Optional[str]) -> Path:
    name = name or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if not NAME_PATTERN.fullmatch(name) or ".." in name:
        raise ValueError(f"bad run name {name!r}")
    return RUNS_DIR / "conversation" / name


def write_report(report: Dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "report.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--chunks-dir", type=Path, default=PROCESSED_DIR / "chunks")
    parser.add_argument("--embedder", default="st:sentence-transformers/all-mpnet-base-v2")
    parser.add_argument("--variant", choices=["plain", "heading"], default="plain")
    parser.add_argument("--rewriter", default=setting("RAG_REWRITER", "ollama:qwen2.5:7b"))
    parser.add_argument("--arms", default="off,on,oracle,concat")
    parser.add_argument("--check-set", action="store_true",
                        help="authoring: run off and oracle only and list the items the raw message misses")
    parser.add_argument("--regression-only", action="store_true",
                        help="ask the 37 answerable single-turn questions as first turns with rewriting on")
    parser.add_argument("--check-rule", action="store_true",
                        help="report whether the shipping rule is committed, clean and unchanged")
    parser.add_argument("--name", default=None, help="run folder under runs/conversation/ (default: UTC time)")
    return parser


def _meta(args: argparse.Namespace, golden: Path, items: int) -> Dict[str, Any]:
    return {
        "command": "python -m rag.experiments.conversation " + " ".join(sys.argv[1:]),
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rewriter": args.rewriter,
        "chunker": CHUNKER,
        "config": CONFIG_NAME,
        "embedder": args.embedder,
        "golden": str(golden),
        "items": items,
        "reasoning_effort": setting("REMOTE_REASONING_EFFORT", "unset"),
    }


def main() -> None:
    setup_logging()
    args = build_parser().parse_args()
    out_dir = report_dir(args.name)
    embedder = get_embedder(args.embedder)
    chunkset = load_chunkset(args.chunks_dir, CHUNKER)
    index = get_index(chunkset, embedder, args.variant, False)
    pipeline = RetrievalPipeline.from_chunkset(chunkset, index, embedder, None)
    config = CONFIGS[CONFIG_NAME]

    items = load_conversations(args.golden)
    meta = _meta(args, args.golden, len(items))
    if args.check_set:
        rows, _ = run_arms(pipeline, config, items, ["off", "oracle"])
        summary = check_set_summary(rows)
        for i in summary["items"]:
            print(f"{i['id']:<6}{i['category']:<28}off {i['off']:.0f} oracle {i['oracle']:.0f}")
        print(f"discriminating {len(summary['discriminating'])}/{summary['eligible']} "
              "pronoun+constraint items miss with off")
        print(f"oracle misses {len(summary['oracle_misses'])}")
        write_report({"meta": meta, "check_set": summary, "rows": rows}, out_dir)
    else:
        arms = [a.strip() for a in args.arms.split(",") if a.strip() and a.strip() != "on"]
        rows, _ = run_arms(pipeline, config, items, arms)
        print(f"arms run: {','.join(arms)}")
        write_report({"meta": meta, "arms_not_run": {}, "rows": rows}, out_dir)
    print(f"written to {out_dir}")


if __name__ == "__main__":
    main()
