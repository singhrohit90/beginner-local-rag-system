"""The multi-turn golden loader (rag/observe/golden_conversations.py) and the committed set."""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

import pytest

from rag.common.config import GOLDEN_DIR, PROCESSED_DIR
from rag.observe.golden import load_golden
from rag.observe.golden_conversations import (
    CATEGORIES, REVIEW_STATES, GoldConversation, GoldTurn, check_against_pages, load_conversations, main, parse_row,
)
from rag.query.history import HISTORY_ANSWER_MAX_WORDS, HISTORY_QUESTION_MAX_WORDS
from rag.query.rewrite import REWRITE_SYSTEM_PROMPT, REWRITE_SYSTEM_PROMPT_NO_CLARIFY

COMMITTED = GOLDEN_DIR / "ddia_conversations.jsonl"
PAGES_FILE = PROCESSED_DIR / "ddia.pages.jsonl"
REVIEW_FILE = GOLDEN_DIR / "MULTITURN_REVIEW.md"

Q015 = "Why does a B-tree write each piece of data to disk more than once?"
Q015_FACTS = ["A B-tree writes every piece of data at least twice: once to the write-ahead log and once to the tree "
              "page itself"]


def row(**overrides: Any) -> Dict[str, Any]:
    """A valid pronoun_follow_up row built from q015."""
    base: Dict[str, Any] = {
        "id": "t001",
        "category": "pronoun_follow_up",
        "turns": [{"question": "How does a B-tree index store its keys?",
                   "answer": "It keeps keys sorted in fixed-size pages that point to child pages."}],
        "message": "Why does it write each piece of data to disk more than once?",
        "standalone": Q015,
        "gold_pages": [[106, 106]],
        "expect": "answer",
        "key_facts": list(Q015_FACTS),
        "evidence_terms": ["write-ahead log"],
        "must_contain": [],
        "must_not_contain": [],
        "review": "pending-human",
        "source_id": "q015",
        "notes": "",
    }
    base.update(overrides)
    return base


def clarify_row(**overrides: Any) -> Dict[str, Any]:
    """A valid ambiguous_follow_up row naming two candidates."""
    base: Dict[str, Any] = {
        "id": "t002",
        "category": "ambiguous_follow_up",
        "turns": [{"question": "What is leader-based replication?",
                   "answer": "Every write goes to one leader, which sends it to the followers."},
                  {"question": "And what is leaderless replication?",
                   "answer": "The client sends each write to several replicas directly."}],
        "message": "Which one copes better with a node going down?",
        "standalone": None,
        "gold_pages": [],
        "expect": "clarify",
        "key_facts": [],
        "evidence_terms": [],
        "must_contain": ["leader-based replication", "leaderless replication"],
        "must_not_contain": [],
        "review": "pending-human",
    }
    base.update(overrides)
    return base


def write_rows(tmp_path: Path, rows: List[Any]) -> Path:
    path = tmp_path / "rows.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def test_a_valid_row_loads(tmp_path):
    first, second = load_conversations(write_rows(tmp_path, [row(), clarify_row(id="t002")]))
    assert isinstance(first, GoldConversation) and isinstance(first.turns[0], GoldTurn)
    assert first.gold_pages == ((106, 106),)
    assert first.source_id == "q015" and first.notes == ""
    assert first.expects_rewrite and second.expects_rewrite
    q = first.to_question()
    assert q.question == Q015 and q.answerable is True
    assert q.gold_pages == [(106, 106)]
    assert q.evidence_terms == ["write-ahead log"] and q.key_facts == Q015_FACTS


def test_the_committed_set_covers_every_category():
    rows = load_conversations(COMMITTED)
    answer = [r for r in rows if r.expect == "answer"]
    assert len(answer) >= 30
    assert sum(1 for r in rows if r.expect == "clarify") >= 4
    counts = Counter(r.category for r in rows)
    assert all(counts[name] >= 4 for name in CATEGORIES), counts
    assert all(r.review in REVIEW_STATES for r in rows)
    sources = [r.source_id for r in answer]
    assert None not in sources and len(sources) == len(set(sources))


def test_the_committed_set_matches_the_book():
    if not PAGES_FILE.exists():
        pytest.skip("data/processed/ddia.pages.jsonl is absent; run the extraction first")
    from rag.ingestion.extract import load_pages

    texts = {p.page_no: p.text for p in load_pages(PAGES_FILE)}
    assert check_against_pages(load_conversations(COMMITTED), texts) == []


def _without(key: str) -> Dict[str, Any]:
    bad = row()
    del bad[key]
    return bad


BAD_ROWS = [
    pytest.param(lambda: row(extra=1), id="unknown_key"),
    pytest.param(lambda: _without("review"), id="missing_key"),
    pytest.param(lambda: row(category="other"), id="unknown_category"),
    pytest.param(lambda: row(expect="rewrite"), id="bad_expect"),
    pytest.param(lambda: row(review="done"), id="bad_review"),
    pytest.param(lambda: row(gold_pages=[[107, 106]]), id="inverted_range"),
    pytest.param(lambda: row(gold_pages=[[0, 1]]), id="page_zero"),
    pytest.param(lambda: row(gold_pages=[[True, 106]]), id="bool_page"),
    pytest.param(lambda: row(turns=[]), id="empty_turns"),
    pytest.param(lambda: row(turns=[{"question": "q?", "answer": "a.", "asked_at": "x"}]), id="turn_extra_key"),
    pytest.param(lambda: row(message="   "), id="blank_message"),
    pytest.param(lambda: row(standalone=None), id="answer_without_standalone"),
    pytest.param(lambda: row(key_facts=[]), id="answer_without_key_facts"),
    pytest.param(lambda: row(evidence_terms=[]), id="answer_without_evidence_terms"),
    pytest.param(lambda: row(gold_pages=[]), id="answer_without_pages"),
    pytest.param(lambda: clarify_row(gold_pages=[[106, 106]]), id="clarify_with_pages"),
    pytest.param(lambda: clarify_row(standalone="Which replication handles a failed node?"),
                 id="clarify_with_standalone"),
    pytest.param(lambda: clarify_row(must_contain=["leader-based replication"]), id="clarify_one_candidate"),
    pytest.param(lambda: clarify_row(must_contain=["leader-based replication", "chain replication"]),
                 id="clarify_candidate_not_in_turns"),
    pytest.param(lambda: clarify_row(category="pronoun_follow_up"), id="clarify_in_wrong_category"),
    pytest.param(lambda: row(category="ambiguous_follow_up"), id="ambiguous_expecting_answer"),
    pytest.param(lambda: row(category="topic_switch", must_not_contain=["keys"]), id="topic_switch_standalone_differs"),
    pytest.param(lambda: row(category="topic_switch", message=Q015, must_not_contain=["b-tree"]),
                 id="topic_switch_leak_in_standalone"),
    pytest.param(lambda: row(category="topic_switch", message=Q015), id="topic_switch_without_must_not_contain"),
    pytest.param(lambda: row(category="constraint_follow_up", must_contain=["B-tree"]),
                 id="constraint_term_missing_from_message"),
    pytest.param(lambda: row(message=Q015), id="pronoun_standalone_equals_message"),
    pytest.param(lambda: row(turns=[{"question": "What is a B-tree?",
                                     "answer": " ".join(["word"] * (HISTORY_ANSWER_MAX_WORDS + 1))}]),
                 id="long_turn_answer"),
    pytest.param(lambda: row(turns=[{"question": " ".join(["word"] * (HISTORY_QUESTION_MAX_WORDS + 1)),
                                     "answer": "A sorted tree of pages."}]),
                 id="long_turn_question"),
]


@pytest.mark.parametrize("make", BAD_ROWS)
def test_a_bad_row_is_rejected(tmp_path, make):
    path = write_rows(tmp_path, [make()])
    with pytest.raises(ValueError) as err:
        load_conversations(path)
    assert str(err.value).startswith(f"{path}:1")


def test_touching_ranges_are_kept_apart():
    touching = parse_row(row(gold_pages=[[100, 101], [102, 103]]), "x:1")
    assert touching.gold_pages == ((100, 101), (102, 103))
    assert parse_row(row(gold_pages=[[106, 106]]), "x:1").gold_pages == ((106, 106),)


def test_an_empty_file_loads_as_no_rows(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    assert load_conversations(path) == []


def test_blank_lines_are_skipped_and_file_order_is_kept(tmp_path):
    path = tmp_path / "rows.jsonl"
    lines = [json.dumps(row(id="t003")), "", json.dumps(row(id="t001")), "   ", json.dumps(row(id="t002"))]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert [r.id for r in load_conversations(path)] == ["t003", "t001", "t002"]


def test_duplicate_ids_are_rejected_with_the_line(tmp_path):
    path = write_rows(tmp_path, [row(), row()])
    with pytest.raises(ValueError) as err:
        load_conversations(path)
    assert str(err.value).startswith(f"{path}:2") and "t001" in str(err.value)


def test_load_golden_is_untouched(tmp_path):
    questions = load_golden(GOLDEN_DIR / "ddia_questions.jsonl")
    assert len(questions) == 45
    assert sum(q.answerable for q in questions) == 37
    with pytest.raises(TypeError):
        load_golden(write_rows(tmp_path, [row()]))


def test_no_row_text_is_in_the_rewriter_prompts():
    prompts = (REWRITE_SYSTEM_PROMPT + "\n" + REWRITE_SYSTEM_PROMPT_NO_CLARIFY).lower()
    for r in load_conversations(COMMITTED):
        texts = [r.message, r.standalone or ""] + [t.question for t in r.turns]
        assert not [t for t in texts if t and t.lower() in prompts], r.id


def test_the_review_file_lists_every_row():
    rows = load_conversations(COMMITTED)
    text = REVIEW_FILE.read_text(encoding="utf-8")
    assert [r.id for r in rows if f"| {r.id} |" not in text] == []
    assert text.count("pending-human") >= sum(1 for r in rows if r.review == "pending-human")


def test_the_cli_prints_counts(tmp_path, monkeypatch, capsys):
    path = write_rows(tmp_path, [row(), clarify_row(id="t002")])
    monkeypatch.setattr(sys, "argv", ["golden_conversations", str(path)])
    main()
    lines = capsys.readouterr().out.splitlines()
    for expected in ("conversations 2 (answer 1, clarify 1)", "category pronoun_follow_up 1",
                     "review pending-human 2", "problems 0 (pages not checked)"):
        assert expected in lines
