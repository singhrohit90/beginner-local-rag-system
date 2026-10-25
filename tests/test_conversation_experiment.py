"""The multi-turn experiment (rag/experiments/conversation.py) on a three-page fixture with fake models."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

import rag.experiments.conversation as conversation
from rag.common.config import RUNS_DIR
from rag.common.embed import HashingEmbedder
from rag.common.llm import FakeLLM
from rag.common.store import VectorIndex
from rag.common.types import Page
from rag.experiments.conversation import (
    BAND_FLOOR_POINTS, BAND_ITEM_POINTS, MAX_FALLBACK_RATE, MIN_NET_WINS, RESULT_LABELS, RULE_HEADING, RULE_PATH,
    category_table, choose_rewriter, decision_line, evaluate_rule, instability, nearest_rank, noise_band,
    oracle_gap_closed, paired, render_results, rule_section, rule_status, run_answers, run_arms, run_regression,
    scoring_refusal, sign_test_p, status_counts, summarise, teacher_history, write_report,
)
from rag.ingestion.chunking import RecursiveChunker
from rag.ingestion.chunking.document import Document
from rag.observe.golden import GoldQuestion
from rag.observe.golden_conversations import CATEGORIES, GoldConversation, parse_row
from rag.query.configs import CONFIGS
from rag.query.history import HISTORY_HEADER, render_block, window
from rag.query.pipeline import RagPipeline, RetrievalPipeline
from rag.query.prompt import ABSTAIN
from tests.test_about_experiment import fake_judge

PAGES = [
    Page(1, "Cats chase mice around the garden every single morning. " * 12),
    Page(2, "A write ahead log records every change before it reaches the tree page. " * 12),
    Page(3, "Stream processors join an event stream with a table of user profiles. " * 12),
]
CONFIG = CONFIGS["weighted"]
REWRITE_P1 = "why does a write ahead log record every change before it reaches the tree page?"
REPLIES = {
    "Why is that needed?": "REWRITE: " + REWRITE_P1,
    "Which one is it?": "CLARIFY: do you mean the write ahead log or the event stream?",
}
WAL_TURN = {"question": "What does a write ahead log record?",
            "answer": "It records every change before it reaches the tree page."}
OK_RULE = {"path": RULE_PATH, "rule_commit": "b" * 40, "head": "a" * 40, "committed": True, "clean": True,
           "unchanged": True, "first_has_results": False}


def fixture_chunkset():
    return RecursiveChunker(size=40, overlap=5).chunk(Document.from_pages(PAGES))


def fixture_pipeline() -> RetrievalPipeline:
    chunkset = fixture_chunkset()
    embedder = HashingEmbedder()
    return RetrievalPipeline.from_chunkset(chunkset, VectorIndex.build(chunkset.chunks, embedder), embedder, None)


def make_item(**overrides: Any) -> GoldConversation:
    return parse_row(item_raw(**overrides), "fixture:1")


def item_raw(**overrides: Any) -> Dict[str, Any]:
    """A valid golden row (pronoun item p1 unless overridden), as it would sit in the JSONL file."""
    raw: Dict[str, Any] = {
        "id": "p1",
        "category": "pronoun_follow_up",
        "turns": [dict(WAL_TURN)],
        "message": "Why is that needed?",
        "standalone": "Why does a write ahead log record every change before the tree page?",
        "gold_pages": [[2, 2]],
        "expect": "answer",
        "key_facts": ["Every change is recorded in the log first"],
        "evidence_terms": ["write ahead log"],
        "must_contain": [],
        "must_not_contain": [],
        "review": "pending-human",
    }
    raw.update(overrides)
    return raw


def raw_items() -> List[Dict[str, Any]]:
    return [
        {"id": "p1"},
        {"id": "s1", "category": "standalone_in_conversation",
         "turns": [{"question": "What do cats chase in the garden?", "answer": "Cats chase mice every morning."}],
         "message": "What do stream processors join an event stream with?",
         "standalone": "What do stream processors join an event stream with?", "gold_pages": [[3, 3]],
         "evidence_terms": ["stream processors"]},
        {"id": "a1", "category": "ambiguous_follow_up", "expect": "clarify",
         "turns": [dict(WAL_TURN), {"question": "What is an event stream?",
                                    "answer": "An event stream is a sequence of events that processors join."}],
         "message": "Which one is it?", "standalone": None, "gold_pages": [], "key_facts": [], "evidence_terms": [],
         "must_contain": ["write ahead log", "event stream"]},
    ]


ITEMS = [make_item(**raw) for raw in raw_items()]
QUESTIONS = [
    GoldQuestion(id="g1", question="What does a write ahead log record before the tree page?", type="factual",
                 answerable=True, reference_answer="Every change.", gold_pages=[(2, 2)],
                 evidence_terms=["write ahead log"], key_facts=["every change"]),
    GoldQuestion(id="g2", question="What do stream processors join an event stream with?", type="factual",
                 answerable=True, reference_answer="A table of user profiles.", gold_pages=[(3, 3)],
                 evidence_terms=["stream processors"], key_facts=["a table of user profiles"]),
]


def last_message(user: str) -> str:
    return user.rsplit("Last message: ", 1)[1].strip()


def scripted_rewriter(replies: Dict[str, str], seen: Optional[List[str]] = None) -> FakeLLM:
    def reply(system: str, user: str) -> str:
        if seen is not None:
            seen.append(user)
        return replies.get(last_message(user), "STANDALONE")
    return FakeLLM(reply)


def raising(exc_type: type) -> Any:
    class Raising:
        name = "raising"

        def generate(self, system: str, user: str, **kwargs: Any) -> Any:
            raise exc_type()
    return Raising()


def recording_generator(seen: List[str], reply: str) -> FakeLLM:
    def answer(system: str, user: str) -> str:
        seen.append(user)
        return reply
    return FakeLLM(answer)


def spy_runs(pipeline: RetrievalPipeline, seen: List[Any]) -> None:
    original = pipeline.run

    def run(query_id: str, question: str, config: Any) -> Any:
        seen.append((query_id, question))
        return original(query_id, question, config)
    pipeline.run = run  # type: ignore[method-assign]


def meta() -> Dict[str, Any]:
    return {"command": "python -m rag.experiments.conversation", "date": "2026-10-25T00:00:00+00:00",
            "rewriter": "ollama:qwen2.5:7b", "chunker": "semantic", "config": "weighted", "embedder": "hash",
            "golden": "fixture.jsonl", "items": 3, "reasoning_effort": "unset", "head": "a" * 40,
            "rule": dict(OK_RULE)}


def build_report(rows: List[Dict[str, Any]], regression: Dict[str, Any]) -> Dict[str, Any]:
    """The report main() assembles, from rows and a regression result."""
    summary = summarise(rows, regression, {"skipped": "not run in this test"})
    rule = evaluate_rule(summary["n"], summary["wins"], summary["losses"], summary["standalone_losses"],
                         regression["identical"] == regression["n"], regression["rewriter_calls"],
                         summary["fallbacks"], summary["gate_calls"], summary["all_approved"])
    return {"meta": meta(), "arms_not_run": {}, "rows": rows, "regression": regression,
            "regression_unrelated": {"skipped": "not run in this test"}, "summary": summary, "rule": rule,
            "decision": {"ship_on": rule["ship_on"], "line": decision_line(rule, summary["pending"])}}


def run_listing() -> set:
    folder = RUNS_DIR / "conversation"
    return {str(p) for p in folder.rglob("*")} if folder.exists() else set()


def test_the_smoke_run_writes_a_complete_report(tmp_path):
    before = run_listing()
    pipeline = fixture_pipeline()
    rows, traces = run_arms(pipeline, CONFIG, ITEMS, ["off", "on", "oracle", "concat"], scripted_rewriter(REPLIES))
    regression = run_regression(pipeline, CONFIG, QUESTIONS, scripted_rewriter({}))
    report = build_report(rows, regression)
    path = write_report(report, tmp_path / "run")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert {"meta", "rows", "summary", "rule", "decision", "regression"} <= set(loaded)
    assert [r["id"] for r in loaded["rows"]] == ["p1", "s1", "a1"]
    by_id = {r["id"]: r for r in loaded["rows"]}
    for item_id in ("p1", "s1"):
        assert set(by_id[item_id]["arms"]) == {"off", "on", "oracle", "concat"}
        assert all(by_id[item_id]["arms"][arm] is not None for arm in ("off", "on", "oracle", "concat"))
    assert all(v is None for v in by_id["a1"]["arms"].values())
    summary = loaded["summary"]
    assert summary["n"] == 2 and summary["wins"] + summary["ties"] + summary["losses"] == summary["n"]
    assert render_results(report).startswith("## Results")
    assert run_listing() == before
