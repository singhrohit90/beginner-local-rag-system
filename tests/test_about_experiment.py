"""The about-the-documents runner (rag/experiments/about.py) and its golden questions, with fake models."""

import json

from rag.common.config import GOLDEN_DIR
from rag.common.llm import FakeLLM
from rag.experiments.about import print_table, run_questions, summarise
from rag.observe.golden import load_golden
from tests.test_about import add_document, make_service
from tests.test_api import COMPACTION, REPLICATION


def fake_judge(stated_for):
    """A judge that replies the way the fact checklist expects: stated_for(n_facts) -> list of booleans."""
    def reply(system, user):
        n = sum(1 for line in user.split("Answer:")[0].splitlines() if line[:1].isdigit())
        return json.dumps({"results": [{"n": i + 1, "stated": s, "quote": ""} for i, s in enumerate(stated_for(n))]})
    return FakeLLM(reply)


def test_the_golden_file_loads_and_every_question_has_facts():
    questions = load_golden(GOLDEN_DIR / "about_questions.jsonl")
    assert len(questions) == 6 and len({q.id for q in questions}) == 6
    assert all(q.key_facts for q in questions)
    assert [q.answerable for q in questions].count(False) == 1  # the one unanswerable from profiles


def test_each_question_is_asked_over_the_documents_and_scored_by_facts(tmp_path):
    service, seen = make_service(tmp_path)
    first = add_document(service, "local", "a.pdf", REPLICATION)
    second = add_document(service, "local", "b.pdf", COMPACTION)
    questions = load_golden(GOLDEN_DIR / "about_questions.jsonl")[:2]
    rows = run_questions(service, "local", [first, second], questions, fake_judge(lambda n: [True] * n))
    assert [r["id"] for r in rows] == ["a001", "a002"]
    assert all(r["correct"] is True and r["outcome"] == "ok" and r["citations"] == ["D1", "D2"] for r in rows)
    assert questions[1].question in seen["user"]  # the last question reached the model with both profiles
    assert "a.pdf" in seen["user"] and "b.pdf" in seen["user"]


def test_a_missing_fact_makes_the_answer_incorrect_and_is_named(tmp_path):
    service, _ = make_service(tmp_path)
    doc = add_document(service, "local", "a.pdf", REPLICATION)
    questions = load_golden(GOLDEN_DIR / "about_questions.jsonl")[:1]
    rows = run_questions(service, "local", [doc], questions, fake_judge(lambda n: [True] + [False] * (n - 1)))
    assert rows[0]["correct"] is False and rows[0]["outcome"] == "fail"
    assert rows[0]["missing"] == questions[0].key_facts[1:]
    summary = summarise(rows)
    assert summary["correct"] == 0 and summary["facts_stated"] == 1 and summary["facts_total"] == len(questions[0].key_facts)


def test_without_a_judge_the_answers_are_unjudged_and_an_error_is_recorded(tmp_path):
    service, _ = make_service(tmp_path)
    doc = add_document(service, "local", "a.pdf", REPLICATION)
    questions = load_golden(GOLDEN_DIR / "about_questions.jsonl")[:1]
    rows = run_questions(service, "local", [doc], questions, None)
    assert rows[0]["outcome"] == "unjudged" and rows[0]["correct"] is None and rows[0]["answer"]
    missing = run_questions(service, "local", ["doesnotexist"], questions, None)  # not the owner's document
    assert missing[0]["outcome"] == "error" and "NotFound" in missing[0]["error"]
    summary = summarise(rows + missing)
    assert summary["judged"] == 0 and summary["errors"] == 1 and summary["correct_rate"] is None


def test_the_table_prints(tmp_path, capsys):
    service, _ = make_service(tmp_path)
    doc = add_document(service, "local", "a.pdf", REPLICATION)
    questions = load_golden(GOLDEN_DIR / "about_questions.jsonl")[:2]
    rows = run_questions(service, "local", [doc], questions, fake_judge(lambda n: [True] * n))
    print_table(rows, summarise(rows))
    out = capsys.readouterr().out
    assert "a001" in out and "a002" in out and "correct 2/2" in out
