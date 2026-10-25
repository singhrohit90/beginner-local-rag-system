"""The multi-turn golden loader (rag/observe/golden_conversations.py) and the committed set."""

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

import pytest

from rag.common.config import GOLDEN_DIR, PROCESSED_DIR
from rag.observe.golden_conversations import (
    CATEGORIES, REVIEW_STATES, GoldConversation, GoldTurn, check_against_pages, load_conversations,
)

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
