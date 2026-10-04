import json

from rag.eval.golden import GoldQuestion, load_golden
from rag.eval.verify_golden import verify

TEXTS = {
    1: "intro text",
    2: "The SSTable is a sorted file. Bulk import (ETL) is common.",
    3: "other text about SSTable in a distractor",
}


def q(**kw):
    base = dict(id="q", question="?", type="factual", answerable=True,
                reference_answer="a", gold_pages=[(2, 2)])
    base.update(kw)
    return GoldQuestion(**base)


def test_term_matches_across_aligned_whitespace():
    texts = {1: "struct Person {\n  1: required string       userName,\n}"}
    question = q(gold_pages=[(1, 1)], evidence_terms=["required string userName"])
    assert verify([question], texts) == []


def test_correct_label_passes():
    assert verify([q(evidence_terms=["SSTable"])], TEXTS) == []


def test_wrong_page_is_caught_and_correct_pages_are_suggested():
    problems = verify([q(gold_pages=[(1, 1)], evidence_terms=["Bulk import"])], TEXTS)
    assert len(problems) == 1 and "[2]" in problems[0]


def test_missing_page_is_caught():
    problems = verify([q(gold_pages=[(99, 99)])], TEXTS)
    assert "do not exist" in problems[0]


def test_unanswerable_claim_is_checked():
    ok = q(type="unanswerable", answerable=False, gold_pages=[], reference_answer="",
           evidence_terms=["Kubernetes"])
    bad = q(type="unanswerable", answerable=False, gold_pages=[], reference_answer="",
            evidence_terms=["SSTable"])
    assert verify([ok], TEXTS) == []
    assert "marked unanswerable" in verify([bad], TEXTS)[0]


def test_attack_question_may_name_terms_that_exist(tmp_path):
    attack = q(type="attack", answerable=False, gold_pages=[], reference_answer="",
               evidence_terms=["SSTable"], must_not_contain=["PWNED"])
    assert verify([attack], TEXTS) == []
    path = tmp_path / "g.jsonl"
    path.write_text(json.dumps({
        "id": "a", "question": "?", "type": "attack", "answerable": False,
        "must_not_contain": ["PWNED"],
    }), encoding="utf-8")
    assert load_golden(path)[0].must_not_contain == ["PWNED"]
