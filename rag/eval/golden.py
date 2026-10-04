"""Golden question set. One JSON object per line in data/golden/*.jsonl.

Gold evidence is stored as PDF page ranges, not chunk IDs, so the same labels score every
chunking strategy fairly.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

QUESTION_TYPES = {
    "factual",  # a fact stated in one place
    "exact_term",  # hinges on a specific term, favors BM25
    "paraphrase",  # wording differs from the book, favors dense
    "multi_chunk",  # evidence spread over several places or chapters
    "comparison",  # contrast two things
    "unanswerable",  # not in the book, correct behaviour is to refuse
    "attack",  # prompt injection or data extraction attempt
    "table",  # answer sits in a table (known weak spot: column boundaries are lost)
    "ambiguous",  # terse or underspecified query, tests query handling
}


@dataclass
class GoldQuestion:
    id: str
    question: str
    type: str
    answerable: bool
    reference_answer: str = ""
    gold_pages: List[Tuple[int, int]] = field(default_factory=list)  # inclusive PDF page ranges
    notes: str = ""
    # Terms that must appear in the text of the gold pages. verify_golden checks this so a wrong
    # page number (for example a printed page used instead of a PDF page) is caught early.
    evidence_terms: List[str] = field(default_factory=list)
    # For attack questions: strings that must never appear in the answer (a canary, a payload).
    must_not_contain: List[str] = field(default_factory=list)
    # Which authoring batch the question came from; see data/golden/BATCHES.md. 0 = unknown.
    batch: int = 0

    def validate(self) -> None:
        if self.type not in QUESTION_TYPES:
            raise ValueError(f"{self.id}: unknown type {self.type!r}")
        if not self.question.strip():
            raise ValueError(f"{self.id}: empty question")
        if self.answerable:
            if not self.gold_pages:
                raise ValueError(f"{self.id}: answerable question needs gold_pages")
            if not self.reference_answer.strip():
                raise ValueError(f"{self.id}: answerable question needs reference_answer")
        elif self.gold_pages:
            raise ValueError(f"{self.id}: unanswerable question must not have gold_pages")
        for start, end in self.gold_pages:
            if start < 1 or end < start:
                raise ValueError(f"{self.id}: bad page range {(start, end)}")


def load_golden(path: Path) -> List[GoldQuestion]:
    questions = []
    seen = set()
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            raw = json.loads(line)
            raw["gold_pages"] = [tuple(r) for r in raw.get("gold_pages", [])]
            q = GoldQuestion(**raw)
            q.validate()
            if q.id in seen:
                raise ValueError(f"{path}:{line_no}: duplicate id {q.id}")
            seen.add(q.id)
            questions.append(q)
    return questions
