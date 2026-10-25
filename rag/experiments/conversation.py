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
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from rag.common.config import GOLDEN_DIR, PROCESSED_DIR, ROOT, RUNS_DIR
from rag.common.embed import get_embedder
from rag.common.log import setup_logging
from rag.common.secrets import setting
from rag.common.trace import Trace
from rag.ingestion.chunking.base import load_chunkset
from rag.ingestion.index import get_index
from rag.observe.golden import GoldQuestion, load_golden
from rag.observe.golden_conversations import GoldConversation, load_conversations
from rag.observe.retrieval_quality.metrics import score_hits, strict_trace
from rag.query.configs import CONFIGS, RetrievalConfig
from rag.query.history import HISTORY_ANSWER_MAX_WORDS, HistoryTurn, window
from rag.query.pipeline import RetrievalPipeline
from rag.query.rewrite import RewriteResult, needs_rewrite, rewrite_question

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


class CallCounter:
    """Wraps an LLM and counts its generate calls, so a run can prove the gate made no call."""

    def __init__(self, llm: Any):
        self._llm = llm
        self.name = getattr(llm, "name", "unknown")
        self.calls = 0

    def generate(self, system: str, user: str, **kwargs: Any) -> Any:
        self.calls += 1
        return self._llm.generate(system, user, **kwargs)


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


def rewrite_for(
    rewriter: Any, message: str, win: Sequence[HistoryTurn], allow_clarify: bool = True,
) -> Tuple[RewriteResult, bool]:
    """The shipped gate, then the shipped rewriter when the gate fires. Returns (result, gate fired)."""
    fired = needs_rewrite(message, win)
    if not fired:
        return RewriteResult(status="skipped", question=message), False
    return rewrite_question(rewriter, message, win, allow_clarify=allow_clarify, doc_names=list(DOC_NAMES)), True


def effective_query(message: str, result: RewriteResult) -> Optional[str]:
    """What retrieval runs on: nothing after a clarify, else the result's question (the raw message unless
    rewritten, which is what the service does)."""
    if result.status == "clarify":
        return None
    return result.question


def score_clarify(
    rewriter: Any, item: GoldConversation, win: Sequence[HistoryTurn], first: RewriteResult,
) -> Dict[str, Any]:
    """A clarify item: did it ask, did the question name both candidates, and does the turn after the
    clarification avoid a second clarify (never two in a row)."""
    asked = first.status == "clarify"
    named_both = asked and all(t.lower() in (first.clarify_question or "").lower() for t in item.must_contain)
    second_status: Optional[str] = None
    second_clarified: Optional[bool] = None
    if asked:
        follow = window(list(win) + [HistoryTurn(item.message, first.clarify_question or "", FIXED_ASKED_AT)])
        second, _ = rewrite_for(rewriter, item.message, follow, allow_clarify=False)
        second_status = second.status
        second_clarified = second_status == "clarify"
    return {"asked": asked, "named_both": named_both, "second_status": second_status,
            "second_clarified": second_clarified}


def _rewrite_record(item: GoldConversation, result: RewriteResult, fired: bool) -> Dict[str, Any]:
    query = effective_query(item.message, result)
    kept = None
    if item.must_contain and result.status == "rewritten":
        kept = all(t.lower() in (query or "").lower() for t in item.must_contain)
    leaked = None
    if item.must_not_contain and query is not None:
        leaked = any(t.lower() in query.lower() for t in item.must_not_contain)
    return {
        "gate_fired": fired,
        "status": result.status,
        "reason": result.reason,
        "rewritten_question": result.rewritten_question,
        "rejected_question": result.rejected_question,
        "clarify_question": result.clarify_question,
        "elapsed_ms": result.elapsed_ms,
        "must_contain_kept": kept,
        "leaked": leaked,
    }


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
    if "on" in arms and rewriter is None:
        raise ValueError("the on arm needs a rewriter")
    rows: List[Dict[str, Any]] = []
    traces: Dict[Tuple[str, str], Trace] = {}
    for item in items:
        row = _new_row(item)
        win = window(teacher_history(item))
        queries = {"off": item.message, "oracle": item.standalone, "concat": concat_query(item)}
        for arm in arms:
            if arm == "on":
                result, fired = rewrite_for(rewriter, item.message, win)
                row["rewrite"] = _rewrite_record(item, result, fired)
                if item.expect != "answer":
                    row["arms"]["on"] = None
                    row["clarify"] = score_clarify(rewriter, item, win, result)
                    continue
                query = effective_query(item.message, result)
                if query is None:  # a false clarify: the user got no answer, so on_i = 0 (D-07)
                    row["arms"]["on"] = {"query": None, "hit@5": 0.0, "mrr": 0.0, "recall@5": 0.0,
                                         "chunk_ids": [], "false_clarify": True}
                    continue
                score, trace = score_query(pipeline, config, f"{item.id}__on", query, item.gold_pages,
                                           item.evidence_terms)
                row["arms"]["on"] = dict(score, false_clarify=False)
                traces[(item.id, "on")] = trace
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


def unrelated_turn(questions: Sequence[GoldQuestion], i: int) -> HistoryTurn:
    """A prior turn about something else: the next question and the first sentence of its answer."""
    q = questions[(i + 1) % len(questions)]
    text = q.reference_answer
    cut = text.find(". ")
    first = text[: cut + 1] if cut >= 0 else text
    answer = " ".join(first.split()[:HISTORY_ANSWER_MAX_WORDS])
    return HistoryTurn(q.question, answer, FIXED_ASKED_AT)


def run_regression(
    pipeline: RetrievalPipeline, config: RetrievalConfig, questions: Sequence[GoldQuestion], rewriter: Any,
    unrelated: bool = False,
) -> Dict[str, Any]:
    """D-09: each answerable single-turn question asked as a first turn (empty window) with rewriting on must
    make no rewriter call and return the same context chunk ids as off. With unrelated=True each question
    follows one unrelated turn; that variant is a non-gating over-rewriting detector."""
    answerable = [q for q in questions if q.answerable]
    counter = CallCounter(rewriter)
    identical = fired_count = 0
    changed_ids: List[str] = []
    hit_changed: List[str] = []
    statuses: Dict[str, int] = {}
    off_hits: List[float] = []
    off_mrrs: List[float] = []
    for i, q in enumerate(answerable):
        off, _ = score_query(pipeline, config, f"{q.id}__off", q.question, q.gold_pages, q.evidence_terms)
        off_hits.append(off["hit@5"])
        off_mrrs.append(off["mrr"])
        win = [unrelated_turn(answerable, i)] if unrelated else []
        result, fired = rewrite_for(counter, q.question, win)
        fired_count += int(fired)
        statuses[result.status] = statuses.get(result.status, 0) + 1
        query = effective_query(q.question, result)
        if query is None:
            changed_ids.append(q.id)
            if off["hit@5"] != 0.0:
                hit_changed.append(q.id)
            continue
        on, _ = score_query(pipeline, config, f"{q.id}__on", query, q.gold_pages, q.evidence_terms)
        if on["chunk_ids"] == off["chunk_ids"]:
            identical += 1
        else:
            changed_ids.append(q.id)
        if on["hit@5"] != off["hit@5"]:
            hit_changed.append(q.id)
    n = len(answerable)
    return {
        "n": n,
        "identical": identical,
        "rewriter_calls": counter.calls,
        "gate_fired": fired_count,
        "changed_ids": changed_ids,
        "hit_changed": hit_changed,
        "statuses": statuses,
        "off_hit@5": round(sum(off_hits) / n, 3) if n else 0.0,
        "off_mrr": round(sum(off_mrrs) / n, 3) if n else 0.0,
        "unrelated": unrelated,
    }


def rule_section(text: str) -> str:
    """The shipping rule section with whitespace collapsed, or "" when the heading is absent."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.rstrip() == RULE_HEADING), None)
    if start is None:
        return ""
    collected: List[str] = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        collected.append(line)
    return " ".join(" ".join(collected).split())


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", check=False)


def rule_status(root: Path = ROOT) -> Dict[str, Any]:
    """Whether the shipping rule may gate a scored run: committed, clean, unchanged since its first commit,
    and first committed without results. Git runs through argv lists, never a shell."""
    log = _git(root, "log", "--diff-filter=A", "--format=%H", "--", RULE_PATH).stdout
    added = [line for line in log.splitlines() if line.strip()]
    rule_commit = added[-1].strip() if added else None
    committed = rule_commit is not None
    clean = (_git(root, "ls-files", "--error-unmatch", RULE_PATH).returncode == 0
             and _git(root, "diff", "--quiet", "HEAD", "--", RULE_PATH).returncode == 0)
    first_text = _git(root, "show", f"{rule_commit}:{RULE_PATH}").stdout if committed else ""
    path = root / RULE_PATH
    working_text = path.read_text(encoding="utf-8") if path.exists() else ""
    first_rule = rule_section(first_text)
    unchanged = committed and first_rule != "" and first_rule == rule_section(working_text)
    first_has_results = any(line.startswith("## Results") for line in first_text.splitlines())
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    return {"path": RULE_PATH, "rule_commit": rule_commit, "head": head, "committed": committed,
            "clean": clean, "unchanged": unchanged, "first_has_results": first_has_results}


def scoring_refusal(arms: Sequence[str], status: Dict[str, Any], regression: bool = False) -> Optional[str]:
    """Why a mode that can call the rewriter must not run, or None. A rule edited after numbers is no rule."""
    if "on" not in arms and not regression:
        return None
    prefix = f"refusing to run the on arm: the shipping rule in {RULE_PATH}"
    if not status["committed"]:
        return f"{prefix} is not committed"
    if not status["clean"]:
        return f"{prefix} has uncommitted changes"
    if not status["unchanged"]:
        return f"{prefix} changed since its first commit"
    if status["first_has_results"]:
        return f"{prefix} was first committed together with results"
    return None


def preflight(llm: Any) -> Optional[str]:
    """One tiny call before a live arm. None when the model answered, else the exception class name, so an
    unreachable model skips its arm instead of recording 100% fallbacks (D-14)."""
    try:
        llm.generate("Reply with one word.", "ok", max_output_tokens=PREFLIGHT_TOKENS)
        return None
    except Exception as err:  # boundary: an unreachable model must skip the arm, not crash the run
        logger.warning("preflight failed: %s", type(err).__name__)
        return type(err).__name__


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


def _print_regression(result: Dict[str, Any]) -> None:
    print(f"regression: {result['identical']}/{result['n']} identical, rewriter calls {result['rewriter_calls']}")
    print(f"regression off hit@5 {result['off_hit@5']:.3f} mrr {result['off_mrr']:.3f}")


def _unrelated(pipeline: RetrievalPipeline, config: RetrievalConfig, questions: Sequence[GoldQuestion],
               raw: Any, spec: str, reachable: Optional[str]) -> Dict[str, Any]:
    if reachable is not None:
        print(f"arm skipped: model unreachable: regression with one unrelated turn (rewriter {spec}: {reachable})")
        return {"skipped": f"rewriter {spec} unreachable ({reachable})"}
    result = run_regression(pipeline, config, questions, raw, unrelated=True)
    rewritten = result["statuses"].get("rewritten", 0)
    print(f"regression with one unrelated turn (not gating): gate fired {result['gate_fired']}, "
          f"rewritten {rewritten}, hit@5 changed {len(result['hit_changed'])} of {result['n']}")
    return result


def main() -> None:
    setup_logging()
    args = build_parser().parse_args()
    if args.check_rule:
        status = rule_status()
        yes = {True: "yes", False: "no"}
        print(f"rule commit {status['rule_commit'] or 'none'}; committed {yes[status['committed']]}; "
              f"clean {yes[status['clean']]}; unchanged {yes[status['unchanged']]}; "
              f"first commit has results {yes[status['first_has_results']]}")
        if not (status["committed"] and status["unchanged"] and not status["first_has_results"]):
            raise SystemExit(1)
        return
    out_dir = report_dir(args.name)
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    status = rule_status()  # captured once, before any arm runs; the report records what the guard checked
    if args.regression_only or not args.check_set:
        refusal = scoring_refusal(["on"] if args.regression_only else arms, status, regression=args.regression_only)
        if refusal:
            print(refusal)
            raise SystemExit(2)

    embedder = get_embedder(args.embedder)
    chunkset = load_chunkset(args.chunks_dir, CHUNKER)
    index = get_index(chunkset, embedder, args.variant, False)
    pipeline = RetrievalPipeline.from_chunkset(chunkset, index, embedder, None)
    config = CONFIGS[CONFIG_NAME]

    if args.regression_only:
        from rag.common.llm import get_llm  # imported here so the pure functions above load without a backend

        questions = load_golden(SINGLE_TURN_GOLDEN)
        meta = dict(_meta(args, SINGLE_TURN_GOLDEN, len(questions)), head=status["head"], rule=status)
        raw = get_llm(args.rewriter, cache_dir=None)  # no disk cache (PITFALLS Pitfall 7)
        regression = run_regression(pipeline, config, questions, raw)
        _print_regression(regression)
        unrelated = _unrelated(pipeline, config, questions, raw, args.rewriter, preflight(raw))
        write_report({"meta": meta, "regression": regression, "regression_unrelated": unrelated}, out_dir)
        print(f"written to {out_dir}")
        return

    items = load_conversations(args.golden)
    meta = dict(_meta(args, args.golden, len(items)), head=status["head"], rule=status)
    if args.check_set:
        rows, _ = run_arms(pipeline, config, items, ["off", "oracle"])
        summary = check_set_summary(rows)
        for i in summary["items"]:
            print(f"{i['id']:<6}{i['category']:<28}off {i['off']:.0f} oracle {i['oracle']:.0f}")
        print(f"discriminating {len(summary['discriminating'])}/{summary['eligible']} "
              "pronoun+constraint items miss with off")
        print(f"oracle misses {len(summary['oracle_misses'])}")
        write_report({"meta": meta, "check_set": summary, "rows": rows}, out_dir)
        print(f"written to {out_dir}")
        return

    arms_not_run: Dict[str, str] = {}
    rewriter: Any = None
    raw: Any = None
    reason: Optional[str] = None
    if "on" in arms:
        from rag.common.llm import get_llm  # imported here so the pure functions above load without a backend

        # No disk cache: repeats must be real draws and no rewriter text outlives the run.
        raw = get_llm(args.rewriter, cache_dir=None)
        reason = preflight(raw)
        if reason is not None:
            arms = [a for a in arms if a != "on"]
            arms_not_run["on"] = f"rewriter {args.rewriter} unreachable ({reason})"
            print(f"arm skipped: model unreachable: on (rewriter {args.rewriter}: {reason})")
        else:
            rewriter = CallCounter(raw)
    rows, _ = run_arms(pipeline, config, items, arms, rewriter)
    print(f"arms run: {','.join(arms)}")
    report: Dict[str, Any] = {"meta": meta, "arms_not_run": arms_not_run, "rows": rows}
    if raw is not None:
        questions = load_golden(SINGLE_TURN_GOLDEN)
        report["regression"] = run_regression(pipeline, config, questions, raw)  # empty window: no call
        _print_regression(report["regression"])
        report["regression_unrelated"] = _unrelated(pipeline, config, questions, raw, args.rewriter, reason)
    else:
        report["regression"] = {"skipped": "the on arm was not requested"}
        report["regression_unrelated"] = {"skipped": "the on arm was not requested"}
    write_report(report, out_dir)
    print(f"written to {out_dir}")


if __name__ == "__main__":
    main()
