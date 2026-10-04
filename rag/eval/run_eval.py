"""Eval harness. Runs any pipeline over the golden set and scores every stage.

A pipeline is a function GoldQuestion -> Trace. The harness does not care how the trace was
built, so the same harness scores fixed vs recursive chunking, dense vs hybrid, with and
without rerank, by swapping the function.

Output in runs/<run_name>/: traces/<id>.json, per_question.jsonl, report.json.
"""

import json
import logging
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence

from rag.config import RUNS_DIR
from rag.eval.diagnose import locate_failure, stage_ranks
from rag.eval.golden import GoldQuestion
from rag.eval.metrics import score_hits, strict_trace
from rag.trace import Trace

logger = logging.getLogger(__name__)

Pipeline = Callable[[GoldQuestion], Trace]


def run_eval(
    questions: Sequence[GoldQuestion],
    pipeline: Pipeline,
    run_name: str,
    ks: Sequence[int] = (1, 3, 5, 10),
    out_root: Path = RUNS_DIR,
    strict: bool = True,
) -> Dict[str, Any]:
    """strict=True also requires a hit to contain the question's evidence terms, not merely to
    overlap the gold pages. Questions without evidence terms fall back to page overlap."""
    out_dir = out_root / run_name
    trace_dir = out_dir / "traces"
    rows: List[Dict[str, Any]] = []

    for q in questions:
        try:
            trace = pipeline(q)
        except Exception:
            trace = Trace(query_id=q.id, question=q.question, error=traceback.format_exc())
            logger.error("Pipeline failed on %s", q.id)
        trace.save(trace_dir)

        row: Dict[str, Any] = {"id": q.id, "type": q.type, "answerable": q.answerable}
        if trace.error:
            row["failure"] = "pipeline_error"
        elif q.answerable:
            judged = strict_trace(trace, q.evidence_terms) if strict else trace
            row["stage_ranks"] = stage_ranks(judged, q.gold_pages)
            row["failure"] = locate_failure(judged, q.gold_pages)
            row["scores"] = {
                s.name: score_hits(s.hits, q.gold_pages, ks) for s in judged.stages
            }
        rows.append(row)

    report = _aggregate(rows)
    report["run_name"] = run_name
    report["config_example"] = None  # filled from the first trace config below
    first = next((p for p in trace_dir.glob("*.json")), None)
    if first:
        report["config_example"] = json.loads(first.read_text(encoding="utf-8")).get("config")

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "per_question.jsonl", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    answerable = [r for r in rows if r["answerable"] and "scores" in r]
    sums: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    by_type: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    type_counts: Counter = Counter()

    final_stage = None
    for row in answerable:
        for stage, scores in row["scores"].items():
            final_stage = stage  # last one seen is the last pipeline stage
            for metric, value in scores.items():
                sums[stage][metric] += value
    for row in answerable:
        type_counts[row["type"]] += 1
        if final_stage and final_stage in row["scores"]:
            for metric, value in row["scores"][final_stage].items():
                by_type[row["type"]][metric] += value

    n = len(answerable) or 1
    return {
        "n_questions": len(rows),
        "n_scored": len(answerable),
        "per_stage": {s: {m: round(v / n, 4) for m, v in d.items()} for s, d in sums.items()},
        "final_stage": final_stage,
        "final_stage_by_type": {
            t: {m: round(v / type_counts[t], 4) for m, v in d.items()} | {"n": type_counts[t]}
            for t, d in by_type.items()
        },
        "failure_counts": dict(Counter(r.get("failure", "unanswerable") for r in rows)),
    }


def print_report(report: Dict[str, Any], metric: str = "recall@5") -> None:
    print(f"run: {report['run_name']}  scored {report['n_scored']}/{report['n_questions']}")
    print(f"{'stage':<14}{metric:>12}{'mrr':>10}")
    for stage, scores in report["per_stage"].items():
        print(f"{stage:<14}{scores.get(metric, float('nan')):>12.3f}{scores['mrr']:>10.3f}")
    print("failures:", report["failure_counts"])
