"""The multi-turn experiment (rag/experiments/conversation.py) on a three-page fixture with fake models."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

import rag.experiments.conversation as conversation
from rag.api.main import build_default_service
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
from tests.test_rewrite_api import spied_settings

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


def question_of(prompt: str) -> str:
    """The question line of an answer prompt (the text after the last "Question:")."""
    return prompt.rsplit("Question:", 1)[1].strip()


def passages_of(prompt: str) -> str:
    return prompt.rsplit("Question:", 1)[0]


def test_each_arm_retrieves_on_its_own_query():
    pipeline = fixture_pipeline()
    seen: List[Any] = []
    spy_runs(pipeline, seen)
    run_arms(pipeline, CONFIG, ITEMS, ["off", "on", "oracle", "concat"], scripted_rewriter(REPLIES))
    p1 = {query_id.split("__")[1]: question for query_id, question in seen if query_id.startswith("p1__")}
    assert p1 == {
        "off": "Why is that needed?",
        "oracle": "Why does a write ahead log record every change before the tree page?",
        "concat": WAL_TURN["question"] + " " + "Why is that needed?",
        "on": REWRITE_P1,
    }
    assert not [q for q in seen if q[0].startswith("a1__")]  # a clarify item is never retrieved


def test_every_arm_sees_the_same_teacher_forced_history():
    pipeline = fixture_pipeline()
    rewriter_prompts: List[str] = []
    item = ITEMS[0]
    rows, traces = run_arms(pipeline, CONFIG, [item], ["off", "on", "oracle", "concat"],
                            scripted_rewriter(REPLIES, rewriter_prompts))
    block = render_block(window(teacher_history(item)))
    assert block and block in rewriter_prompts[0]
    answer_prompts: List[str] = []
    rag = RagPipeline(pipeline, recording_generator(answer_prompts, "Every change is logged first [S1]."))
    run_answers(rag, fake_judge(lambda n: [True] * n), [item], rows, traces)
    assert len(answer_prompts) == 4  # off, oracle, on, on_original: four different slots or retrievals
    for prompt in answer_prompts:
        assert block in prompt and prompt.count(HISTORY_HEADER) == 1

    switch = make_item(id="t1", category="topic_switch", message="What do stream processors join an event stream with?",
                       standalone="What do stream processors join an event stream with?", gold_pages=[[3, 3]],
                       evidence_terms=["stream processors"], must_not_contain=["tree page"])
    rows, traces = run_arms(pipeline, CONFIG, [switch], ["off", "on", "oracle"], scripted_rewriter(
        {switch.message: "NEW_TOPIC: " + switch.message}))
    assert rows[0]["rewrite"]["status"] == "new_topic"
    answer_prompts.clear()
    results = run_answers(rag, fake_judge(lambda n: [True] * n), [switch], rows, traces)
    with_history = [p for p in answer_prompts if HISTORY_HEADER in p]
    without = [p for p in answer_prompts if HISTORY_HEADER not in p]
    assert with_history and without  # off and oracle keep the history, the on variants after new_topic drop it
    assert results[0]["on_original"]["reused"] is True  # same slot, same retrieval, same (empty) history


def hand_row(item_id: str, off: float, on: float, oracle: float = 1.0,
             category: str = "pronoun_follow_up") -> Dict[str, Any]:
    def score(hit: float) -> Dict[str, Any]:
        return {"query": "q", "hit@5": hit, "mrr": hit, "recall@5": hit, "chunk_ids": []}
    return {"id": item_id, "category": category, "expect": "answer", "review": "pending-human", "source_id": None,
            "expects_rewrite": True, "arms": {"off": score(off), "on": dict(score(on), false_clarify=False),
                                              "oracle": score(oracle)},
            "rewrite": None, "clarify": None}


def test_paired_counts_and_category_table():
    rows = [hand_row("h1", 0.0, 1.0), hand_row("h2", 0.0, 1.0), hand_row("h3", 1.0, 1.0), hand_row("h4", 1.0, 0.0)]
    assert paired(rows) == {"win": 2, "tie": 1, "loss": 1, "n": 4}
    assert [entry["category"] for entry in category_table(rows)] == list(CATEGORIES)
    skipped = {"skipped": "not run"}
    summary = summarise(rows, skipped, skipped)
    assert summary["oracle_gap_closed"] is None  # oracle 4 hits minus off 2 hits is under three items
    rule = evaluate_rule(summary["n"], summary["wins"], summary["losses"], summary["standalone_losses"], False, 0,
                         summary["fallbacks"], summary["gate_calls"], summary["all_approved"])
    report = {"meta": meta(), "arms_not_run": {}, "rows": rows, "regression": skipped,
              "regression_unrelated": skipped, "summary": summary, "rule": rule}
    assert "Oracle gap closed by on: n/a." in render_results(report)


def test_a_fallback_is_a_counted_failure():
    rows, _ = run_arms(fixture_pipeline(), CONFIG, ITEMS, ["off", "on"], raising(ConnectionRefusedError))
    p1 = rows[0]
    assert p1["rewrite"]["status"] == "fallback" and p1["rewrite"]["reason"] == "unavailable"
    assert p1["arms"]["on"]["query"] == "Why is that needed?" and p1["arms"]["on"]["false_clarify"] is False
    summary = summarise(rows, {"skipped": "x"}, {"skipped": "x"})
    assert summary["fallbacks"] == summary["gate_calls"] >= 1
    assert status_counts(rows)["reasons"].get("unavailable", 0) >= 1
    rule = evaluate_rule(summary["n"], summary["wins"], summary["losses"], summary["standalone_losses"], True, 0,
                         summary["fallbacks"], summary["gate_calls"], True)
    assert [c["label"] for c in rule["checks"] if not c["passed"]][-1] == "e" and rule["ship_on"] is False


def test_clarify_items_are_scored_apart():
    rows, _ = run_arms(fixture_pipeline(), CONFIG, ITEMS, ["off", "on", "oracle"], scripted_rewriter(REPLIES))
    a1 = rows[2]
    assert a1["clarify"]["asked"] is True and a1["clarify"]["named_both"] is True
    assert a1["clarify"]["second_clarified"] is False  # the turn after a clarification never clarifies again
    assert all(v is None for v in a1["arms"].values())
    assert summarise(rows, {"skipped": "x"}, {"skipped": "x"})["n"] == 2

    clarifying = dict(REPLIES, **{"Why is that needed?": "CLARIFY: do you mean the write ahead log or the tree page?"})
    rows, _ = run_arms(fixture_pipeline(), CONFIG, ITEMS, ["off", "on"], scripted_rewriter(clarifying))
    p1_on = rows[0]["arms"]["on"]
    assert p1_on["hit@5"] == 0.0 and p1_on["false_clarify"] is True and p1_on["query"] is None
    assert summarise(rows, {"skipped": "x"}, {"skipped": "x"})["false_clarify"] == 1


def test_answers_are_scored_with_the_fact_checklist(monkeypatch):
    def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the holistic correctness judge must not be called")

    monkeypatch.setattr("rag.observe.generation_quality.judge.judge_correctness", never)
    pipeline = fixture_pipeline()
    seen: List[Any] = []
    spy_runs(pipeline, seen)
    item = ITEMS[0]
    rows, traces = run_arms(pipeline, CONFIG, [item], ["off", "on", "oracle"], scripted_rewriter(REPLIES))
    prompts: List[str] = []

    def reply(system: str, user: str) -> str:
        prompts.append(user)
        return ABSTAIN if item.standalone in question_of(user) else "Every change is logged first [S1]."

    rag = RagPipeline(pipeline, FakeLLM(reply))
    result = run_answers(rag, fake_judge(lambda n: [True] * n), [item], rows, traces)[0]
    assert result["oracle"]["correct"] is False and result["oracle"]["abstained"] is True
    assert result["off"]["correct"] is True and result["on"]["correct"] is True
    on_prompt = next(p for p in prompts if REWRITE_P1 in question_of(p))
    original = [p for p in prompts if question_of(p) == item.message and passages_of(p) == passages_of(on_prompt)]
    assert len(original) == 1  # on_original: the on retrieval, only the question slot differs
    assert [q for q in seen if q[0] == "p1__on"] == [("p1__on", REWRITE_P1)]  # one on retrieval for both slots


def patch_main(monkeypatch, tmp_path: Path, rule: Dict[str, Any], llm: Any) -> Path:
    """main() on the fixture: no model download, no data/processed, the report under tmp_path."""
    set_path = tmp_path / "set.jsonl"
    set_path.write_text("".join(json.dumps(item_raw(**raw)) + "\n" for raw in raw_items()), encoding="utf-8")
    single = tmp_path / "single.jsonl"
    single.write_text("".join(json.dumps({"id": q.id, "question": q.question, "type": q.type,
                                          "answerable": q.answerable, "reference_answer": q.reference_answer,
                                          "gold_pages": [list(r) for r in q.gold_pages],
                                          "evidence_terms": q.evidence_terms, "key_facts": q.key_facts}) + "\n"
                              for q in QUESTIONS), encoding="utf-8")
    monkeypatch.setattr(conversation, "get_embedder", lambda spec: HashingEmbedder())
    monkeypatch.setattr(conversation, "load_chunkset", lambda folder, name: fixture_chunkset())
    monkeypatch.setattr(conversation, "get_index",
                        lambda chunkset, embedder, variant, rebuild: VectorIndex.build(chunkset.chunks, embedder))
    monkeypatch.setattr(conversation, "rule_status", lambda root=None: dict(rule))
    monkeypatch.setattr(conversation, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(conversation, "SINGLE_TURN_GOLDEN", single)
    monkeypatch.setattr("rag.common.llm.get_llm", lambda spec, cache_dir=None: llm)
    monkeypatch.setattr(sys, "argv", ["conversation", "--golden", str(set_path), "--name", "t"])
    return tmp_path / "conversation" / "t"


def test_an_unreachable_model_skips_its_arm(tmp_path, monkeypatch, capsys):
    out_dir = patch_main(monkeypatch, tmp_path, OK_RULE, raising(ConnectionRefusedError))
    conversation.main()
    printed = capsys.readouterr().out
    assert "arm skipped: model unreachable: on" in printed
    report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    assert "on" in report["arms_not_run"]
    assert all(r["rewrite"] is None for r in report["rows"])
    assert report["decision"]["ship_on"] is False and report["decision"]["line"].startswith("Decision: ships off")


def test_repeats_report_instability_without_gating():
    pipeline = fixture_pipeline()
    first, _ = run_arms(pipeline, CONFIG, ITEMS, ["off", "on", "oracle"], scripted_rewriter(REPLIES))
    clarifying = dict(REPLIES, **{"Why is that needed?": "CLARIFY: do you mean the write ahead log or the tree page?"})
    second, _ = run_arms(pipeline, CONFIG, ITEMS, ["on"], scripted_rewriter(clarifying))
    regression = {"n": 2, "identical": 2, "rewriter_calls": 0}
    before = build_report(first, regression)["rule"]
    report = instability([first, second])
    assert report["per_repeat"][1]["changed"] == ["p1"] and report["unstable_ids"] == ["p1"]
    assert build_report(first, regression)["rule"] == before  # the rule reads repeat 1 only


def rule_args(**overrides: Any) -> Dict[str, Any]:
    args: Dict[str, Any] = {"n": 30, "wins": 5, "losses": 0, "standalone_losses": 0, "regression_identical": True,
                            "regression_calls": 0, "fallbacks": 0, "gate_calls": 20, "all_approved": True}
    args.update(overrides)
    return args


# (evaluate_rule arguments, ship_on, failed labels or None when the rule is not evaluated, expected band or None)
RULE_CASES = [
    pytest.param(rule_args(wins=3), False, ["a"], 10.0, id="n30_net3_fails_a"),
    pytest.param(rule_args(wins=4), True, [], 10.0, id="n30_net4_passes"),
    pytest.param(rule_args(n=37, wins=4), True, [], 300 / 37, id="n37_band"),
    pytest.param(rule_args(n=38, wins=4), True, [], 8.0, id="n38_band_floor"),
    pytest.param(rule_args(n=40, wins=4), True, [], 8.0, id="n40_band_floor"),
    pytest.param(rule_args(standalone_losses=1), False, ["c"], None, id="standalone_loss_fails_c"),
    pytest.param(rule_args(regression_identical=False), False, ["d"], None, id="regression_changed_fails_d"),
    pytest.param(rule_args(regression_calls=1), False, ["d"], None, id="regression_call_fails_d"),
    pytest.param(rule_args(fallbacks=2), True, [], None, id="fallback_2_of_20_passes_e"),
    pytest.param(rule_args(fallbacks=3), False, ["e"], None, id="fallback_3_of_20_fails_e"),
    pytest.param(rule_args(gate_calls=0), False, ["e"], None, id="no_gate_call_fails_e"),
    pytest.param(rule_args(all_approved=False), False, ["f"], None, id="pending_fails_f"),
    pytest.param(rule_args(n=0, wins=0), False, None, None, id="n0_not_evaluated"),
    pytest.param(dict(rule_args(), on_run=False), False, None, None, id="on_not_run_not_evaluated"),
]


@pytest.mark.parametrize("kwargs, ship_on, failed, band", RULE_CASES)
def test_the_rule_table(kwargs, ship_on, failed, band):
    rule = evaluate_rule(**kwargs)
    assert rule["ship_on"] is ship_on
    if failed is None:
        assert rule["evaluated"] is False and rule["reason"]
        return
    assert [c["label"] for c in rule["checks"]] == ["a", "b", "c", "d", "e", "f"]
    assert [c["label"] for c in rule["checks"] if not c["passed"]] == failed
    if band is not None:
        assert noise_band(kwargs["n"]) == band and rule["band"] == band


def test_the_sign_test_and_percentiles():
    assert sign_test_p(4, 0) == 0.0625
    assert abs(sign_test_p(8, 4) - 0.194) < 0.001
    assert sign_test_p(0, 0) == 1.0
    assert nearest_rank([], 50) is None
    assert nearest_rank([3.0, 1.0, 2.0], 50) == 2.0
    assert nearest_rank([1.0, 2.0, 3.0, 4.0], 95) == 4.0
    assert oracle_gap_closed(10, 12, 12) is None
    assert oracle_gap_closed(10, 12, 14) == 0.5


def test_the_results_file_starts_with_the_rule():
    text = (Path(conversation.ROOT) / RULE_PATH).read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == RULE_HEADING
    assert next(line for line in lines if line.startswith("## ")) == RULE_HEADING
    assert f"max({int(BAND_FLOOR_POINTS)}, {int(BAND_ITEM_POINTS)} / n)" in text
    assert f"net >= {MIN_NET_WINS}" in text
    assert f"<= {round(MAX_FALLBACK_RATE * 100)}% of rewriter calls" in text
    section = rule_section(text)
    assert section and section in " ".join((conversation.__doc__ or "").split())


def test_the_on_arm_needs_a_committed_rule(tmp_path, monkeypatch, capsys):
    assert scoring_refusal(["off", "on"], OK_RULE) is None
    assert scoring_refusal(["off", "oracle"], dict(OK_RULE, clean=False)) is None
    for key, value in (("committed", False), ("clean", False), ("unchanged", False), ("first_has_results", True)):
        assert scoring_refusal(["on"], dict(OK_RULE, **{key: value})), key
    out_dir = patch_main(monkeypatch, tmp_path, dict(OK_RULE, clean=False), scripted_rewriter(REPLIES))
    with pytest.raises(SystemExit) as stop:
        conversation.main()
    assert stop.value.code == 2
    assert "refusing to run the on arm" in capsys.readouterr().out
    assert not out_dir.exists() and not (tmp_path / "conversation").exists()


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=rule-test", "-c", "user.email=rule-test", "-c", "commit.gpgsign=false",
                    *args], cwd=repo, check=True, capture_output=True)


def new_repo(repo: Path, text: str) -> Path:
    repo.mkdir()
    git(repo, "init", "-q")
    doc = repo / RULE_PATH
    doc.parent.mkdir(parents=True)
    doc.write_text(text, encoding="utf-8")
    git(repo, "add", RULE_PATH)
    git(repo, "commit", "-q", "-m", "rule")
    return doc


def test_rule_status_reads_git(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    repo = tmp_path / "repo"
    doc = new_repo(repo, RULE_HEADING + "\n\nShip only when the gain exceeds the band.\n")
    status = rule_status(repo)
    assert status["committed"] and status["clean"] and status["unchanged"] and not status["first_has_results"]
    assert len(status["rule_commit"]) == 40 and status["head"] == status["rule_commit"]
    doc.write_text(RULE_HEADING + "\n\nShip when the gain reaches the band.\n", encoding="utf-8")
    status = rule_status(repo)
    assert status["committed"] and not status["clean"] and not status["unchanged"]
    git(repo, "commit", "-q", "-am", "edit the rule")
    status = rule_status(repo)
    assert status["clean"] and not status["unchanged"]

    other = tmp_path / "other"
    new_repo(other, RULE_HEADING + "\n\nA rule.\n\n## Results\n\nNumbers.\n")
    assert rule_status(other)["first_has_results"] is True


def test_the_regression_arm_matches_off_with_no_rewriter_call():
    result = run_regression(fixture_pipeline(), CONFIG, QUESTIONS, scripted_rewriter({}))
    assert result["rewriter_calls"] == 0 and result["gate_fired"] == 0
    assert result["identical"] == result["n"] == 2


def test_the_regression_arm_detects_a_rewriter_call(monkeypatch):
    monkeypatch.setattr(conversation, "needs_rewrite", lambda message, win: True)
    swap = {QUESTIONS[1].question: "REWRITE: what does a write ahead log record before the tree page?"}
    result = run_regression(fixture_pipeline(), CONFIG, QUESTIONS, scripted_rewriter(swap))
    assert result["rewriter_calls"] > 0 and result["identical"] < 2
    rule = evaluate_rule(**rule_args(regression_identical=result["identical"] == result["n"],
                                     regression_calls=result["rewriter_calls"]))
    assert [c["label"] for c in rule["checks"] if not c["passed"]] == ["d"]


QWEN = {"spec": "ollama:qwen2.5:7b", "on_hit@5": 0.60, "p50": 900.0}


def gpt(hit: float, p50: Optional[float]) -> Dict[str, Any]:
    return {"spec": "vllm:/models/gpt-oss-20b", "on_hit@5": hit, "p50": p50}


CHOICE_CASES = [
    pytest.param(None, "ollama:qwen2.5:7b", "qwen by default, not compared", id="no_second_run"),
    pytest.param(gpt(0.71, 5000.0), "vllm:/models/gpt-oss-20b", "on hit@5 higher by more than the band",
                 id="second_better_by_more_than_band"),
    pytest.param(gpt(0.70, 5000.0), "ollama:qwen2.5:7b", "inside the band; lower p50 latency", id="exactly_the_band"),
    pytest.param(gpt(0.65, 500.0), "vllm:/models/gpt-oss-20b", "inside the band; lower p50 latency",
                 id="inside_band_second_faster"),
    pytest.param(gpt(0.62, 5000.0), "ollama:qwen2.5:7b", "inside the band; lower p50 latency",
                 id="inside_band_first_faster"),
    pytest.param(gpt(0.45, 100.0), "ollama:qwen2.5:7b", "on hit@5 higher by more than the band",
                 id="first_better_by_more_than_band"),
    pytest.param(gpt(0.60, None), "ollama:qwen2.5:7b", "inside the band; lower p50 latency", id="missing_latency"),
]


@pytest.mark.parametrize("second, chosen, reason", CHOICE_CASES)
def test_the_rewriter_choice_table(second, chosen, reason):
    assert choose_rewriter(QWEN, second, 10.0) == {"chosen": chosen, "reason": reason}


def test_the_results_text_holds_no_model_text():
    marker = "zanzibarquux"
    replies = {"Why is that needed?": "REWRITE: " + REWRITE_P1.rstrip("?") + " " + marker + "?",
               "Which one is it?": "CLARIFY: do you mean the write ahead log or the event stream " + marker + "?"}
    pipeline = fixture_pipeline()
    rows, traces = run_arms(pipeline, CONFIG, ITEMS, ["off", "on", "oracle", "concat"], scripted_rewriter(replies))
    assert marker in rows[0]["rewrite"]["rewritten_question"] and marker in rows[2]["rewrite"]["clarify_question"]
    regression = run_regression(pipeline, CONFIG, QUESTIONS, scripted_rewriter({}))
    report = build_report(rows, regression)
    rag = RagPipeline(pipeline, FakeLLM(lambda system, user: "Logged first, " + marker + " [S1]."))
    report["answers"] = run_answers(rag, fake_judge(lambda n: [True] * n), ITEMS, rows, traces)
    report["answers_summary"] = conversation.answers_summary(report["answers"])
    report["slot"] = conversation.slot_decision(report["answers_summary"], report["summary"]["band"])
    report["judge_same_as_rewriter"] = True
    text = render_results(report)
    lines = text.splitlines()
    for label in RESULT_LABELS:
        assert any(line.startswith(label) for line in lines), label
    last = [line for line in lines if line.strip()][-1]
    assert last.startswith("Decision: ships off") and "provisional: items pending human review" in last
    assert sum(1 for line in lines if line.startswith("Decision:")) == 1
    assert marker not in text


DOC = Path(conversation.ROOT) / RULE_PATH


def recorded(label: str) -> str:
    """The rest of the first line of the committed Results section that starts with label, stripped."""
    text = DOC.read_text(encoding="utf-8")
    assert "## Results" in text, "docs/chat_memory_eval.md has no Results section"
    for line in text.split("## Results", 1)[1].splitlines():
        if line.startswith(label):
            return line[len(label):].strip()
    raise AssertionError(f"no {label!r} line in the Results section")


def test_the_default_matches_the_recorded_decision(monkeypatch, tmp_path):
    on = recorded("Decision:").startswith("ships on")
    built = spied_settings(monkeypatch, tmp_path)
    service = build_default_service()
    assert service.rewrite is on, recorded("Decision:")
    assert built and all(cache_dir is None for _, cache_dir in built), built


def test_the_results_file_records_every_decision():
    results = DOC.read_text(encoding="utf-8").split("## Results", 1)[1]
    lines = results.splitlines()
    for label in RESULT_LABELS:
        assert any(line.startswith(label) for line in lines), label
    assert [line for line in lines if line.strip()][-1].startswith("Decision: ships")
    assert recorded("Question slot:").startswith(("rewritten question", "original message"))
    assert recorded("Judge and rewriter are the same model:").startswith(("yes", "no", "not applicable"))
    commit = recorded("Rule commit:")
    assert len(commit) == 40 and all(c in "0123456789abcdef" for c in commit), commit
    if shutil.which("git"):
        assert commit == rule_status()["rule_commit"]


def test_the_rewriter_default_matches_the_recorded_choice(monkeypatch, tmp_path):
    built = spied_settings(monkeypatch, tmp_path)
    monkeypatch.setenv("RAG_REWRITE", "1")
    build_default_service()
    assert len(built) == 2, built
    assert built[1] == (recorded("Rewriter chosen:").split(" ", 1)[0], None)
    assert all(cache_dir is None for _, cache_dir in built), built
