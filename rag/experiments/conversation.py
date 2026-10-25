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
import copy
import json
import logging
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from math import ceil, comb
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from rag.common.config import GOLDEN_DIR, PROCESSED_DIR, ROOT, RUNS_DIR
from rag.common.embed import get_embedder
from rag.common.log import setup_logging
from rag.common.secrets import setting
from rag.common.trace import Trace
from rag.ingestion.chunking.base import load_chunkset
from rag.ingestion.index import get_index
from rag.observe.generation_quality.judge import judge_facts
from rag.observe.golden import GoldQuestion, load_golden
from rag.observe.golden_conversations import CATEGORIES, GoldConversation, load_conversations
from rag.observe.retrieval_quality.metrics import score_hits, strict_trace
from rag.query.configs import CONFIGS, RetrievalConfig
from rag.query.generate import looks_like_abstention
from rag.query.history import HISTORY_ANSWER_MAX_WORDS, HistoryTurn, render_block, window
from rag.query.pipeline import RagPipeline, RetrievalPipeline
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
MIN_GAP_ITEMS = 3  # an oracle gap under three items is too small to report a fraction of
ANSWER_ARMS = ("off", "on", "on_original", "oracle")
RESULT_LABELS = (
    "Command:", "Date:", "Git commit:", "Rule commit:", "Rewriter:", "Rewriter chosen:", "Rewriter latency:",
    "Question slot:", "Judge and rewriter are the same model:", "Regression arm:", "Owner review:", "Decision:",
)


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
    parser.add_argument("--repeats", type=int, default=1,
                        help="repeat the on arm; the rule uses repeat 1, later repeats are instability only")
    parser.add_argument("--answers", action="store_true",
                        help="also answer the last turn (generator) and score it with the fact checklist (judge)")
    parser.add_argument("--llm", default=setting("RAG_LLM", "vllm:/models/gpt-oss-20b"), help="generator spec")
    parser.add_argument("--judge", default=setting("RAG_JUDGE", "ollama:qwen2.5:7b"), help="fact-checklist judge spec")
    parser.add_argument("--workers", type=int, default=4, help="items answered in parallel")
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


def noise_band(n: int) -> float:
    """The committed band in hit@5 points: max(8, 300 / n); infinite with no item."""
    if n <= 0:
        return float("inf")
    return max(BAND_FLOOR_POINTS, BAND_ITEM_POINTS / n)


def _answer_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in rows if r["expect"] == "answer"]


def paired(
    rows: Sequence[Dict[str, Any]], a: str = "on", b: str = "off", metric: str = "hit@5",
    categories: Optional[Sequence[str]] = None,
) -> Dict[str, int]:
    """Per-item win, tie and loss of arm a against arm b over the answer items where both ran."""
    counts = {"win": 0, "tie": 0, "loss": 0, "n": 0}
    for row in _answer_rows(rows):
        if categories is not None and row["category"] not in categories:
            continue
        left, right = row["arms"].get(a), row["arms"].get(b)
        if left is None or right is None:
            continue
        key = "win" if left[metric] > right[metric] else "loss" if left[metric] < right[metric] else "tie"
        counts[key] += 1
        counts["n"] += 1
    return counts


def sign_test_p(wins: int, losses: int) -> float:
    """One-sided exact sign test on the discordant pairs; 1.0 when there is none."""
    d = wins + losses
    if d == 0:
        return 1.0
    return sum(comb(d, k) for k in range(wins, d + 1)) / 2 ** d


def oracle_gap_closed(off_hits: int, on_hits: int, oracle_hits: int) -> Optional[float]:
    """Share of the off-to-oracle gap the on arm closed; None when the gap is under MIN_GAP_ITEMS items."""
    if oracle_hits - off_hits < MIN_GAP_ITEMS:
        return None
    return round((on_hits - off_hits) / (oracle_hits - off_hits), 3)


def nearest_rank(values: Sequence[float], pct: float) -> Optional[float]:
    """The nearest-rank percentile; None for no values."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, ceil(pct / 100 * len(ordered)) - 1)]


def status_counts(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Rewrite status counts, fallback reason counts and the fallback ids (the rejected text stays in rows)."""
    statuses: Dict[str, int] = {}
    reasons: Dict[str, int] = {}
    fallbacks: List[Dict[str, Any]] = []
    for row in rows:
        rewrite = row.get("rewrite")
        if not rewrite:
            continue
        statuses[rewrite["status"]] = statuses.get(rewrite["status"], 0) + 1
        if rewrite["status"] == "fallback":
            reasons[rewrite["reason"]] = reasons.get(rewrite["reason"], 0) + 1
            fallbacks.append({"id": row["id"], "reason": rewrite["reason"]})
    return {"statuses": statuses, "reasons": reasons, "fallbacks": fallbacks}


def _rate(part: int, whole: int) -> Optional[float]:
    return round(part / whole, 3) if whole else None


def gate_quality(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Gate precision and recall against expects_rewrite, and the answer items it skipped although the raw
    message missed and the standalone question hit."""
    judged = [r for r in rows if r.get("rewrite")]
    true_pos = sum(1 for r in judged if r["expects_rewrite"] and r["rewrite"]["gate_fired"])
    fired = sum(1 for r in judged if r["rewrite"]["gate_fired"])
    positives = sum(1 for r in judged if r["expects_rewrite"])
    misses = [
        r["id"] for r in _answer_rows(judged)
        if not r["rewrite"]["gate_fired"] and r["arms"].get("off") and r["arms"].get("oracle")
        and r["arms"]["off"]["hit@5"] == 0 and r["arms"]["oracle"]["hit@5"] == 1
    ]
    return {"precision": _rate(true_pos, fired), "recall": _rate(true_pos, positives), "fired": fired,
            "positives": positives, "misses": misses}


def _mean(values: Sequence[float]) -> Optional[float]:
    return round(sum(values) / len(values), 3) if values else None


def _arm_means(rows: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    means: Dict[str, Dict[str, Any]] = {}
    for arm in ARMS:
        scored = [r["arms"][arm] for r in _answer_rows(rows) if r["arms"].get(arm) is not None]
        if scored:
            means[arm] = {"hit@5": _mean([s["hit@5"] for s in scored]), "mrr": _mean([s["mrr"] for s in scored]),
                          "recall@5": _mean([s["recall@5"] for s in scored]), "n": len(scored)}
    return means


def category_table(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One entry per category in CATEGORIES order."""
    table: List[Dict[str, Any]] = []
    for name in CATEGORIES:
        mine = [r for r in rows if r["category"] == name]
        entry: Dict[str, Any] = {
            "category": name,
            "n": len(mine),
            "gate_fired": sum(1 for r in mine if r.get("rewrite") and r["rewrite"]["gate_fired"]),
        }
        if name == "ambiguous_follow_up":
            clarify = [r["clarify"] for r in mine if r.get("clarify")]
            entry.update(asked=sum(1 for c in clarify if c["asked"]),
                         named_both=sum(1 for c in clarify if c["named_both"]),
                         second_clarified=sum(1 for c in clarify if c["second_clarified"]))
        else:
            entry["hit@5"] = {arm: m["hit@5"] for arm, m in _arm_means(mine).items()}
            entry["paired"] = paired(rows, categories=[name])
        table.append(entry)
    return table


def summarise(
    rows: Sequence[Dict[str, Any]], regression: Dict[str, Any], regression_unrelated: Dict[str, Any],
) -> Dict[str, Any]:
    """Every number of D-06 from one repeat's rows, the regression arm and its unrelated-turn variant."""
    answer = _answer_rows(rows)
    n = len(answer)
    pair = paired(rows)
    net = pair["win"] - pair["loss"]

    def hits(arm: str) -> int:
        return int(sum(r["arms"][arm]["hit@5"] for r in answer if r["arms"].get(arm) is not None))

    fired = [r for r in rows if r.get("rewrite") and r["rewrite"]["gate_fired"]]
    timed = [r["rewrite"]["elapsed_ms"] for r in fired
             if not (r["rewrite"]["status"] == "fallback" and r["rewrite"]["reason"] == "input_too_long")]
    kept = [r["rewrite"]["must_contain_kept"] for r in rows
            if r.get("rewrite") and r["rewrite"]["must_contain_kept"] is not None]
    leaks = [r["rewrite"]["leaked"] for r in rows if r.get("rewrite") and r["rewrite"]["leaked"] is not None]
    clarify = [r["clarify"] for r in rows if r["expect"] == "clarify" and r.get("clarify")]
    pending = sum(1 for r in rows if r["review"] == "pending-human")
    return {
        "n": n,
        "items": len(rows),
        "arms": _arm_means(rows),
        "wins": pair["win"],
        "ties": pair["tie"],
        "losses": pair["loss"],
        "net": net,
        "gain": round(100.0 * net / n, 2) if n else 0.0,
        "band": noise_band(n),
        "sign_p": round(sign_test_p(pair["win"], pair["loss"]), 4),
        "subset": paired(rows, categories=["pronoun_follow_up", "constraint_follow_up"]),
        "oracle_gap_closed": oracle_gap_closed(hits("off"), hits("on"), hits("oracle")) if n else None,
        "categories": category_table(rows),
        "statuses": status_counts(rows),
        "gate": gate_quality(rows),
        "gate_calls": len(fired),
        "fallbacks": sum(1 for r in fired if r["rewrite"]["status"] == "fallback"),
        "false_clarify": sum(1 for r in answer if (r["arms"].get("on") or {}).get("false_clarify")),
        "latency": {"p50": nearest_rank(timed, 50), "p95": nearest_rank(timed, 95), "count": len(timed)},
        "must_contain_kept": _rate(sum(1 for k in kept if k), len(kept)),
        "leak_rate": _rate(sum(1 for k in leaks if k), len(leaks)),
        "clarify": {"n": sum(1 for r in rows if r["expect"] == "clarify"),
                    "asked": sum(1 for c in clarify if c["asked"]),
                    "named_both": sum(1 for c in clarify if c["named_both"]),
                    "second_clarified": sum(1 for c in clarify if c["second_clarified"])},
        "standalone_losses": sum(
            1 for r in answer if r["category"] == "standalone_in_conversation"
            and r["arms"].get("on") is not None and r["arms"].get("off") is not None
            and r["arms"]["on"]["hit@5"] < r["arms"]["off"]["hit@5"]),
        "pending": pending,
        "all_approved": bool(rows) and pending == 0 and all(r["review"] == "approved" for r in rows),
        "regression": regression,
        "regression_unrelated": regression_unrelated,
    }


def evaluate_rule(
    n: int, wins: int, losses: int, standalone_losses: int, regression_identical: bool, regression_calls: int,
    fallbacks: int, gate_calls: int, all_approved: bool, on_run: bool = True,
) -> Dict[str, Any]:
    """The committed shipping rule, (a) to (f); rewriting ships on only when all six pass."""
    if not on_run:
        return {"evaluated": False, "ship_on": False, "checks": [], "reason": "on arm not run: no rewriter numbers"}
    if n <= 0:
        return {"evaluated": False, "ship_on": False, "checks": [], "reason": "no answer items"}
    net = wins - losses
    gain = 100.0 * net / n
    band = noise_band(n)
    sign_p = sign_test_p(wins, losses)
    checks = [
        {"label": "a", "text": "gain > band, strictly", "passed": gain > band,
         "detail": f"gain {gain:.1f} points, band {band:.1f} points (n = {n})"},
        {"label": "b", "text": "net >= 3", "passed": net >= MIN_NET_WINS,
         "detail": f"net {net} (wins {wins}, losses {losses})"},
        {"label": "c", "text": "no standalone_in_conversation loss", "passed": standalone_losses == 0,
         "detail": f"{standalone_losses} standalone items lost"},
        {"label": "d", "text": "regression arm identical with zero rewriter calls",
         "passed": bool(regression_identical) and regression_calls == 0,
         "detail": f"identical {'yes' if regression_identical else 'no'}, rewriter calls {regression_calls}"},
        {"label": "e", "text": "fallbacks <= 10% of rewriter calls",
         "passed": gate_calls > 0 and fallbacks <= MAX_FALLBACK_RATE * gate_calls,
         "detail": f"{fallbacks} fallbacks of {gate_calls} rewriter calls"},
        {"label": "f", "text": "every item approved", "passed": bool(all_approved),
         "detail": "all items approved" if all_approved else "some items are not approved"},
    ]
    passed_a = checks[0]["passed"]
    return {
        "evaluated": True,
        "ship_on": all(c["passed"] for c in checks),
        "checks": checks,
        "gain": round(gain, 2),
        "band": band,
        "net": net,
        "sign_p": round(sign_p, 4),
        "weak_evidence": bool(passed_a and sign_p >= 0.05),
    }


def decision_line(rule: Dict[str, Any], pending: int) -> str:
    if rule["ship_on"]:
        return "Decision: ships on"
    if not rule["evaluated"]:
        why = rule["reason"]
    else:
        why = "failed: " + ", ".join(c["label"] for c in rule["checks"] if not c["passed"])
    if pending > 0:
        why += "; provisional: items pending human review"
    return f"Decision: ships off ({why})"


def instability(repeat_rows: Sequence[Sequence[Dict[str, Any]]]) -> Dict[str, Any]:
    """Per repeat: on hit@5 mean, status counts and the ids whose on hit@5 differs from repeat 1. Reported only."""
    def on_hits(rows: Sequence[Dict[str, Any]]) -> Dict[str, float]:
        return {r["id"]: r["arms"]["on"]["hit@5"] for r in _answer_rows(rows) if r["arms"].get("on") is not None}

    first = on_hits(repeat_rows[0]) if repeat_rows else {}
    per_repeat: List[Dict[str, Any]] = []
    unstable: List[str] = []
    for rows in repeat_rows:
        hits = on_hits(rows)
        changed = [i for i in first if i in hits and hits[i] != first[i]]
        unstable += [i for i in changed if i not in unstable]
        per_repeat.append({"on_hit@5": _mean(list(hits.values())), "statuses": status_counts(rows)["statuses"],
                           "changed": changed})
    return {"per_repeat": per_repeat, "unstable_ids": unstable}


def _answer_item(
    rag: RagPipeline, judge: Any, item: GoldConversation, row: Dict[str, Any],
    traces: Dict[Tuple[str, str], Trace],
) -> Dict[str, Any]:
    win = window(teacher_history(item))
    block = render_block(win)
    rewrite = row.get("rewrite") or {}
    on_block = render_block([]) if rewrite.get("status") == "new_topic" else block
    on_score = row["arms"].get("on")
    variants: List[Tuple[str, Optional[Trace], str, str]] = [
        ("off", traces.get((item.id, "off")), item.message, block),
        ("oracle", traces.get((item.id, "oracle")), item.standalone or item.message, block),
    ]
    if on_score is not None:
        on_trace = traces.get((item.id, "on"))
        variants += [("on", on_trace, on_score["query"] or item.message, on_block),
                     ("on_original", on_trace, item.message, on_block)]
    result: Dict[str, Any] = {"id": item.id, "category": item.category, "off": None, "on": None,
                              "on_original": None, "oracle": None}
    memo: Dict[Tuple[str, Tuple[str, ...], str], str] = {}
    for name, trace, slot, history in variants:
        if name in ("on", "on_original") and on_score.get("false_clarify"):
            result[name] = {"answer": None, "correct": False, "abstained": False, "reused": False}
            continue
        if trace is None:
            continue
        ids = tuple(h.chunk_id for h in trace.stage("context").hits)
        key = (slot, ids, history)
        reused = key in memo
        if not reused:
            t = copy.deepcopy(trace)  # answer() writes into the trace; the two slot variants share one retrieval
            t.question = slot
            memo[key] = rag.answer(t, history_block=history).answer
        answer = memo[key]
        abstained = looks_like_abstention(answer)
        if abstained:
            correct: Optional[bool] = False
        elif judge is None:
            correct = None
        else:
            correct = judge_facts(judge, answer, list(item.key_facts)).correct
        result[name] = {"answer": answer, "correct": correct, "abstained": abstained, "reused": reused}
    return result


def run_answers(
    rag: RagPipeline, judge: Any, items: Sequence[GoldConversation], rows: Sequence[Dict[str, Any]],
    traces: Dict[Tuple[str, str], Trace], workers: int = 1,
) -> List[Dict[str, Any]]:
    """Answer the last turn of each answer item for off, oracle, on and on_original, scored by the fact
    checklist only (an abstention is wrong). Rows come back in item order."""
    by_id = {r["id"]: r for r in rows}
    todo = [item for item in items if item.expect == "answer" and item.id in by_id]
    if workers > 1:
        with ThreadPoolExecutor(workers) as pool:
            return list(pool.map(lambda item: _answer_item(rag, judge, item, by_id[item.id], traces), todo))
    return [_answer_item(rag, judge, item, by_id[item.id], traces) for item in todo]


def answers_summary(answer_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    for variant in ANSWER_ARMS:
        scored = [r[variant] for r in answer_rows if r.get(variant) is not None]
        judged = [s for s in scored if s["correct"] is not None]
        correct = sum(1 for s in judged if s["correct"])
        summary[variant] = {"correct": correct, "judged": len(judged), "rate": _rate(correct, len(judged))}
    return summary


def slot_decision(summary: Optional[Dict[str, Any]], band: float) -> str:
    """D-11: keep the rewritten question unless the original-message slot is better by more than the band."""
    if summary is None:
        return "unmeasured"
    on_rate = (summary.get("on") or {}).get("rate")
    original_rate = (summary.get("on_original") or {}).get("rate")
    if on_rate is not None and original_rate is not None and 100.0 * (original_rate - on_rate) > band:
        return "original message"
    return "rewritten question"


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _regression_line(summary: Dict[str, Any]) -> str:
    reg = summary.get("regression") or {}
    if "identical" not in reg:
        return f"not run ({reg.get('skipped', 'no rewriter')})"
    line = (f"{reg['identical']}/{reg['n']} identical, rewriter calls {reg['rewriter_calls']} "
            f"(off hit@5 {reg['off_hit@5']:.3f}, mrr {reg['off_mrr']:.3f})")
    unrelated = summary.get("regression_unrelated") or {}
    if "gate_fired" in unrelated:
        line += (f"; after one unrelated turn (not gating): gate fired {unrelated['gate_fired']}, rewritten "
                 f"{unrelated['statuses'].get('rewritten', 0)}, hit@5 changed {len(unrelated['hit_changed'])} "
                 f"of {unrelated['n']}")
    else:
        line += f"; unrelated-turn variant not run ({unrelated.get('skipped', 'no rewriter')})"
    return line


def _slot_line(report: Dict[str, Any]) -> str:
    slot = report.get("slot", "unmeasured")
    if slot == "unmeasured":
        return "rewritten question (unmeasured: answers not run)"
    rates = report.get("answers_summary") or {}
    return (f"{slot} (on rate {_fmt((rates.get('on') or {}).get('rate'))}, on_original rate "
            f"{_fmt((rates.get('on_original') or {}).get('rate'))})")


def _judge_line(report: Dict[str, Any]) -> str:
    if not report.get("answers"):
        return "not applicable (answers not run)"
    if report.get("judge_same_as_rewriter"):
        return f"yes ({report.get('judge_spec', report['meta']['rewriter'])})"
    return "no"


def _choice(report: Dict[str, Any], compare: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    spec = report["meta"]["rewriter"]
    reason = "qwen by default, not compared" if "qwen" in spec else f"{spec} by default, not compared"
    return {"chosen": spec, "reason": reason}


def render_results(report: Dict[str, Any], compare: Optional[Dict[str, Any]] = None) -> str:
    """The section plan 04-08 appends below the rule: counts, rates, reason codes and ids only, never model
    text, so nothing a model wrote reaches the committed file."""
    meta, summary = report["meta"], report["summary"]
    choice = _choice(report, compare)
    rule = report["rule"]
    chosen = summary
    lines: List[str] = ["## Results", ""]
    command = meta["command"] + (f"; compare: {compare['meta']['command']}" if compare else "")
    rewriters = meta["rewriter"] + (f"; compare: {compare['meta']['rewriter']}" if compare else "")
    lat = chosen["latency"]
    latency = (f"p50 {_fmt(lat['p50'], 1)} ms, p95 {_fmt(lat['p95'], 1)} ms over {lat['count']} calls"
               if lat["count"] else "not measured (on arm not run)")
    pending, total = summary["pending"], summary["items"]
    review = (f"{pending} of {total} items pending-human; the numbers are provisional until every item is "
              "approved and the run is repeated") if pending else f"all {total} items approved"
    values = (command, meta["date"], meta["head"], meta["rule"]["rule_commit"], rewriters,
              f"{choice['chosen']} ({choice['reason']})", latency, _slot_line(report), _judge_line(report),
              _regression_line(summary), review)
    for label, value in zip(RESULT_LABELS[:-1], values):
        lines.append(f"{label} {value}")
        lines.append("")
    lines += ["### Arms (answer items, strict evidence-aware retrieval)", "",
              "| arm | n | hit@5 | mrr | recall@5 |", "|-----|---|-------|-----|----------|"]
    for arm, m in chosen["arms"].items():
        lines.append(f"| {arm} | {m['n']} | {_fmt(m['hit@5'])} | {_fmt(m['mrr'])} | {_fmt(m['recall@5'])} |")
    lines += ["", f"Oracle gap closed by on: {_fmt(chosen['oracle_gap_closed'])}. "
              f"False clarifies on answer items: {chosen['false_clarify']}.", ""]
    lines += ["### Paired on vs off (hit@5)", "",
              "| items | win | tie | loss | n |", "|-------|-----|-----|------|---|",
              f"| all answer items | {chosen['wins']} | {chosen['ties']} | {chosen['losses']} | {chosen['n']} |"]
    sub = chosen["subset"]
    lines.append(f"| pronoun and constraint | {sub['win']} | {sub['tie']} | {sub['loss']} | {sub['n']} |")
    lines += ["", f"Net {chosen['net']}, gain {chosen['gain']} points, band {_fmt(chosen['band'], 1)} points, "
              f"sign test p = {_fmt(chosen['sign_p'], 4)}."]
    if rule.get("weak_evidence"):
        lines.append(f"clears the project band; weak evidence (sign test p = {_fmt(rule['sign_p'], 4)})")
    lines += ["", "### Per category", "", "| category | n | gate fired | off | on | oracle | concat | win/tie/loss |",
              "|----------|---|------------|-----|----|--------|--------|--------------|"]
    for entry in chosen["categories"]:
        if "hit@5" in entry:
            h, p = entry["hit@5"], entry["paired"]
            lines.append(f"| {entry['category']} | {entry['n']} | {entry['gate_fired']} | {_fmt(h.get('off'))} | "
                         f"{_fmt(h.get('on'))} | {_fmt(h.get('oracle'))} | {_fmt(h.get('concat'))} | "
                         f"{p['win']}/{p['tie']}/{p['loss']} |")
        else:
            lines.append(f"| {entry['category']} | {entry['n']} | {entry['gate_fired']} | clarify: asked "
                         f"{entry['asked']}, named both {entry['named_both']}, second clarify "
                         f"{entry['second_clarified']} | | | | |")
    st = chosen["statuses"]
    gate = chosen["gate"]
    lines += ["", "### Rewrite statuses and gate", "",
              "Statuses: " + (", ".join(f"{k} {v}" for k, v in sorted(st["statuses"].items())) or "none") + ".",
              "Fallback reasons: " + (", ".join(f"{k} {v}" for k, v in sorted(st["reasons"].items())) or "none")
              + ".",
              f"Gate: precision {_fmt(gate['precision'])}, recall {_fmt(gate['recall'])}, fired {gate['fired']}, "
              f"misses {', '.join(gate['misses']) or 'none'}. Rewriter calls counted for (e): "
              f"{chosen['gate_calls']}, fallbacks {chosen['fallbacks']}.",
              f"must_contain kept rate {_fmt(chosen['must_contain_kept'])}; must_not_contain leak rate "
              f"{_fmt(chosen['leak_rate'])}.",
              f"Clarify items: {chosen['clarify']['n']}, asked {chosen['clarify']['asked']}, named both "
              f"{chosen['clarify']['named_both']}, second clarification {chosen['clarify']['second_clarified']}."]
    repeats = report.get("repeats") or {}
    lines += ["", "### Instability across repeats (reported, not gating)", ""]
    if len(repeats.get("per_repeat", [])) > 1:
        for i, rep in enumerate(repeats["per_repeat"], start=1):
            lines.append(f"- repeat {i}: on hit@5 {_fmt(rep['on_hit@5'])}, changed vs repeat 1: "
                         f"{', '.join(rep['changed']) or 'none'}")
    else:
        lines.append("One repeat only.")
    lines += ["", "### Answers (fact checklist, last turn)", ""]
    answers = report.get("answers_summary")
    if answers:
        lines += ["| variant | correct | judged | rate |", "|---------|---------|--------|------|"]
        for variant in ANSWER_ARMS:
            a = answers.get(variant) or {}
            lines.append(f"| {variant} | {a.get('correct', 0)} | {a.get('judged', 0)} | {_fmt(a.get('rate'))} |")
    else:
        why = "; ".join(f"{k}: {v}" for k, v in (report.get("answers_not_run") or {}).items())
        lines.append(f"unmeasured ({why or 'answers not run'})")
    lines += ["", "### Shipping rule conditions", ""]
    if rule["evaluated"]:
        for check in rule["checks"]:
            lines.append(f"- ({check['label']}) {check['text']}: {'passed' if check['passed'] else 'failed'}; "
                         f"{check['detail']}")
    else:
        lines.append(f"- not evaluated: {rule['reason']}")
    lines += ["", decision_line(rule, summary["pending"])]
    return "\n".join(lines) + "\n"


def print_tables(report: Dict[str, Any]) -> None:
    summary, rule = report["summary"], report["rule"]
    print(f"{'arm':<10}{'n':>4}{'hit@5':>8}{'mrr':>8}{'rec@5':>8}")
    for arm, m in summary["arms"].items():
        print(f"{arm:<10}{m['n']:>4}{m['hit@5']:>8.3f}{m['mrr']:>8.3f}{m['recall@5']:>8.3f}")
    print(f"paired on vs off: win {summary['wins']} tie {summary['ties']} loss {summary['losses']} "
          f"(n {summary['n']}, gain {summary['gain']}, band {_fmt(summary['band'], 1)}, "
          f"sign test p {_fmt(summary['sign_p'], 4)})")
    for entry in summary["categories"]:
        if "hit@5" in entry:
            print(f"  {entry['category']:<28} n {entry['n']:>3}  " +
                  "  ".join(f"{arm} {_fmt(v)}" for arm, v in entry["hit@5"].items()))
        else:
            print(f"  {entry['category']:<28} n {entry['n']:>3}  asked {entry['asked']} named both "
                  f"{entry['named_both']} second clarify {entry['second_clarified']}")
    st = summary["statuses"]
    print("statuses: " + (", ".join(f"{k} {v}" for k, v in sorted(st["statuses"].items())) or "none")
          + "; fallback reasons: " + (", ".join(f"{k} {v}" for k, v in sorted(st["reasons"].items())) or "none"))
    gate, lat = summary["gate"], summary["latency"]
    print(f"gate precision {_fmt(gate['precision'])} recall {_fmt(gate['recall'])}; latency p50 "
          f"{_fmt(lat['p50'], 1)} ms p95 {_fmt(lat['p95'], 1)} ms over {lat['count']}")
    print("regression: " + _regression_line(summary))
    for i, rep in enumerate((report.get("repeats") or {}).get("per_repeat", [])[1:], start=2):
        changed = ", ".join(rep["changed"]) or "none"
        print(f"repeat {i}: on hit@5 {_fmt(rep['on_hit@5'])}, changed vs repeat 1: {changed}")
    answers = report.get("answers_summary")
    if answers:
        print("answers (fact checklist): " + ", ".join(
            f"{v} {a['correct']}/{a['judged']}" for v, a in answers.items()) + f"; slot: {report.get('slot')}")
    else:
        print("answers: unmeasured")
    for check in rule.get("checks", []):
        print(f"({check['label']}) {'passed' if check['passed'] else 'failed'}: {check['detail']}")
    print(decision_line(rule, summary["pending"]))


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
    rows, traces = run_arms(pipeline, config, items, arms, rewriter)
    repeat_rows = [rows]
    if rewriter is not None:
        for _ in range(2, max(1, args.repeats) + 1):  # repeats re-draw only the on arm; the others are deterministic
            again, _ = run_arms(pipeline, config, items, ["on"], rewriter)
            repeat_rows.append(again)
    report: Dict[str, Any] = {"meta": meta, "arms_not_run": arms_not_run, "rows": rows,
                              "repeats": instability(repeat_rows)}
    if raw is not None:
        questions = load_golden(SINGLE_TURN_GOLDEN)
        report["regression"] = run_regression(pipeline, config, questions, raw)  # empty window: no call
        _print_regression(report["regression"])
        report["regression_unrelated"] = _unrelated(pipeline, config, questions, raw, args.rewriter, reason)
    else:
        report["regression"] = {"skipped": "the on arm was not requested"}
        report["regression_unrelated"] = {"skipped": "the on arm was not requested"}
    _decide(report, arms)
    report["slot"] = "unmeasured"
    if args.answers and rewriter is None:
        report["answers_not_run"] = {"answers": "the on arm did not run"}
        print("arm skipped: answers (the on arm did not run)")
    elif args.answers:
        generator = get_llm(args.llm, cache_dir=None)
        judge = get_llm(args.judge, cache_dir=None)
        not_run: Dict[str, str] = {}
        for role, spec, llm in (("generator", args.llm, generator), ("judge", args.judge, judge)):
            failed = preflight(llm)
            if failed is not None:
                not_run[role] = f"{spec} unreachable ({failed})"
                print(f"arm skipped: model unreachable: answers ({role} {spec}: {failed})")
        if not_run:
            report["answers_not_run"] = not_run
        else:
            rag = RagPipeline(pipeline, generator, style="standard", subject="book")
            report["answers"] = run_answers(rag, judge, items, rows, traces, workers=args.workers)
            report["answers_summary"] = answers_summary(report["answers"])
            report["slot"] = slot_decision(report["answers_summary"], report["summary"]["band"])
            report["judge_same_as_rewriter"] = args.judge == args.rewriter
            report["judge_spec"] = args.judge
    write_report(report, out_dir)
    (out_dir / "results.md").write_text(render_results(report), encoding="utf-8")
    print_tables(report)
    print(f"arms run: {','.join(arms)}")
    print(f"written to {out_dir}")


def _decide(report: Dict[str, Any], arms: Sequence[str]) -> None:
    """Summary, rule verdict and decision line from repeat 1, stored in the report."""
    regression = report["regression"]
    summary = summarise(report["rows"], regression, report["regression_unrelated"])
    identical = "identical" in regression and regression["identical"] == regression["n"]
    rule = evaluate_rule(summary["n"], summary["wins"], summary["losses"], summary["standalone_losses"], identical,
                         regression.get("rewriter_calls", 0), summary["fallbacks"], summary["gate_calls"],
                         summary["all_approved"], on_run="on" not in report["arms_not_run"] and "on" in arms)
    report["summary"] = summary
    report["rule"] = rule
    report["decision"] = {"ship_on": rule["ship_on"], "line": decision_line(rule, summary["pending"])}


if __name__ == "__main__":
    main()
