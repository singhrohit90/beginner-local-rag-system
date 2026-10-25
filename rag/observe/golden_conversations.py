"""Multi-turn golden set. One conversation per line in data/golden/ddia_conversations.jsonl.

Each row is one scored follow-up: `message` is the scored last turn and `turns` are the fixed
prior turns, given to every experiment arm as teacher-forced history (never model-generated
answers). Gold evidence is PDF page ranges (for DDIA, printed page + 22) plus `evidence_terms`,
so retrieval is scored with strict evidence-aware relevance, never page overlap alone.

The single-turn loader `load_golden` and rag/observe/golden.py are untouched (EVAL-01, D-04);
`GoldConversation.to_question()` adapts a row to the existing `GoldQuestion` so the page check in
rag/observe/golden_tools/verify_golden.py runs unchanged.

    python -m rag.observe.golden_conversations data/golden/ddia_conversations.jsonl --pages data/processed/ddia.pages.jsonl
"""

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from rag.common.config import GOLDEN_DIR
from rag.observe.golden import GoldQuestion
from rag.observe.golden_tools.verify_golden import verify
from rag.query.history import HISTORY_ANSWER_MAX_WORDS, HISTORY_QUESTION_MAX_WORDS

CATEGORIES = (
    "pronoun_follow_up",
    "constraint_follow_up",
    "topic_switch",
    "ambiguous_follow_up",
    "standalone_in_conversation",
)
EXPECTS = ("answer", "clarify")
REVIEW_STATES = ("pending-human", "approved")
REQUIRED_KEYS = (
    "id",
    "category",
    "turns",
    "message",
    "standalone",
    "gold_pages",
    "expect",
    "key_facts",
    "evidence_terms",
    "must_contain",
    "must_not_contain",
    "review",
)
OPTIONAL_KEYS = ("source_id", "notes")
TURN_KEYS = ("question", "answer")
MIN_CLARIFY_CANDIDATES = 2  # a clarify row names at least two earlier candidates


def normalise(text: str) -> str:
    """Lower-case, collapse whitespace, and drop trailing ?, . and ! for equality checks."""
    return re.sub(r"\s+", " ", text.lower()).strip().rstrip("?.! ")


@dataclass(frozen=True)
class GoldTurn:
    question: str
    answer: str


@dataclass(frozen=True)
class GoldConversation:
    id: str
    category: str
    turns: Tuple[GoldTurn, ...]
    message: str
    standalone: Optional[str]
    gold_pages: Tuple[Tuple[int, int], ...]  # inclusive PDF page ranges, file order, never merged
    expect: str
    key_facts: Tuple[str, ...]
    evidence_terms: Tuple[str, ...]
    must_contain: Tuple[str, ...]
    must_not_contain: Tuple[str, ...]
    review: str
    source_id: Optional[str] = None
    notes: str = ""

    @property
    def expects_rewrite(self) -> bool:
        if self.expect == "clarify":
            return True
        return normalise(self.standalone or "") != normalise(self.message)

    def validate(self) -> None:
        if not self.id:
            raise ValueError("empty id")
        if self.category not in CATEGORIES:
            raise ValueError(f"{self.id}: unknown category")
        if self.expect not in EXPECTS:
            raise ValueError(f"{self.id}: unknown expect")
        if self.review not in REVIEW_STATES:
            raise ValueError(f"{self.id}: unknown review state")
        if not self.turns:
            raise ValueError(f"{self.id}: turns must not be empty")
        if not self.message.strip():
            raise ValueError(f"{self.id}: empty message")
        for start, end in self.gold_pages:
            if start < 1 or end < start:
                raise ValueError(f"{self.id}: bad page range {(start, end)}")
        for n, turn in enumerate(self.turns, start=1):
            if len(turn.question.split()) > HISTORY_QUESTION_MAX_WORDS:
                raise ValueError(f"{self.id}: turn {n} question over HISTORY_QUESTION_MAX_WORDS words")
            if len(turn.answer.split()) > HISTORY_ANSWER_MAX_WORDS:
                raise ValueError(f"{self.id}: turn {n} answer over HISTORY_ANSWER_MAX_WORDS words")
        if (self.expect == "clarify") != (self.category == "ambiguous_follow_up"):
            raise ValueError(f"{self.id}: expect clarify if and only if category ambiguous_follow_up")
        if self.expect == "clarify":
            if self.standalone is not None:
                raise ValueError(f"{self.id}: a clarify row has a null standalone")
            if self.gold_pages or self.key_facts or self.evidence_terms:
                raise ValueError(f"{self.id}: a clarify row has no gold_pages, key_facts or evidence_terms")
            if len(self.must_contain) < MIN_CLARIFY_CANDIDATES:
                raise ValueError(f"{self.id}: a clarify row needs MIN_CLARIFY_CANDIDATES must_contain terms")
            history = " ".join(t.question + " " + t.answer for t in self.turns).lower()
            if any(term.lower() not in history for term in self.must_contain):
                raise ValueError(f"{self.id}: every clarify candidate must appear in the turns")
        else:
            if not isinstance(self.standalone, str) or not self.standalone.strip():
                raise ValueError(f"{self.id}: an answer row needs a standalone question")
            if not self.gold_pages:
                raise ValueError(f"{self.id}: an answer row needs gold_pages")
            if not self.key_facts:
                raise ValueError(f"{self.id}: an answer row needs key_facts")
            if not self.evidence_terms:
                raise ValueError(f"{self.id}: an answer row needs evidence_terms")
            same = normalise(self.standalone) == normalise(self.message)
            if self.category in ("topic_switch", "standalone_in_conversation") and not same:
                raise ValueError(f"{self.id}: standalone must equal message in category {self.category}")
            if self.category in ("pronoun_follow_up", "constraint_follow_up") and same:
                raise ValueError(f"{self.id}: standalone must differ from message in category {self.category}")
            standalone = self.standalone.lower()
            if self.category == "topic_switch":
                if not self.must_not_contain:
                    raise ValueError(f"{self.id}: a topic_switch row needs must_not_contain")
                if any(term.lower() in standalone for term in self.must_not_contain):
                    raise ValueError(f"{self.id}: a must_not_contain term occurs in the standalone")
            if self.category == "constraint_follow_up":
                if not self.must_contain:
                    raise ValueError(f"{self.id}: a constraint_follow_up row needs must_contain")
                message = self.message.lower()
                if any(t.lower() not in message or t.lower() not in standalone for t in self.must_contain):
                    raise ValueError(f"{self.id}: every must_contain term must be in message and standalone")

    def to_question(self) -> GoldQuestion:
        return GoldQuestion(
            id=self.id,
            question=self.standalone or self.message,
            type="factual",
            answerable=self.expect == "answer",
            reference_answer=" ".join(self.key_facts),
            gold_pages=list(self.gold_pages),
            notes=self.notes,
            evidence_terms=list(self.evidence_terms),
            key_facts=list(self.key_facts),
        )


def _strings(raw: Dict[str, Any], key: str, where: str) -> Tuple[str, ...]:
    value = raw[key]
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise ValueError(f"{where}: {key} must be a list of non-empty strings")
    return tuple(value)


def parse_row(raw: Dict[str, Any], where: str) -> GoldConversation:
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: a row must be a JSON object")
    unknown = set(raw) - set(REQUIRED_KEYS) - set(OPTIONAL_KEYS)
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}")
    missing = [k for k in REQUIRED_KEYS if k not in raw]
    if missing:
        raise ValueError(f"{where}: missing keys {missing}")
    for key in ("id", "category", "message", "expect", "review"):
        if not isinstance(raw[key], str):
            raise ValueError(f"{where}: {key} must be a string")
    for key in ("standalone", "source_id"):
        if raw.get(key) is not None and not isinstance(raw[key], str):
            raise ValueError(f"{where}: {key} must be a string or null")
    if not isinstance(raw.get("notes", ""), str):
        raise ValueError(f"{where}: notes must be a string")
    turns_raw = raw["turns"]
    if not isinstance(turns_raw, list):
        raise ValueError(f"{where}: turns must be a list")
    turns = []
    for turn in turns_raw:
        if not isinstance(turn, dict) or set(turn) != set(TURN_KEYS):
            raise ValueError(f"{where}: each turn has exactly the keys {list(TURN_KEYS)}")
        if not all(isinstance(turn[k], str) and turn[k].strip() for k in TURN_KEYS):
            raise ValueError(f"{where}: turn question and answer must be non-empty strings")
        turns.append(GoldTurn(question=turn["question"], answer=turn["answer"]))
    pages_raw = raw["gold_pages"]
    if not isinstance(pages_raw, list):
        raise ValueError(f"{where}: gold_pages must be a list")
    pages = []
    for rng in pages_raw:
        ok = isinstance(rng, list) and len(rng) == 2
        if not ok or not all(isinstance(p, int) and not isinstance(p, bool) for p in rng):
            raise ValueError(f"{where}: gold_pages entries must be [start, end] integers")
        pages.append((rng[0], rng[1]))
    item = GoldConversation(
        id=raw["id"],
        category=raw["category"],
        turns=tuple(turns),
        message=raw["message"],
        standalone=raw["standalone"],
        gold_pages=tuple(pages),
        expect=raw["expect"],
        key_facts=_strings(raw, "key_facts", where),
        evidence_terms=_strings(raw, "evidence_terms", where),
        must_contain=_strings(raw, "must_contain", where),
        must_not_contain=_strings(raw, "must_not_contain", where),
        review=raw["review"],
        source_id=raw.get("source_id"),
        notes=raw.get("notes", ""),
    )
    try:
        item.validate()
    except ValueError as err:
        raise ValueError(f"{where}: {err}") from err
    return item


def load_conversations(path: Path) -> List[GoldConversation]:
    conversations: List[GoldConversation] = []
    seen = set()
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                raise ValueError(f"{path}:{line_no}: not JSON") from None
            item = parse_row(raw, f"{path}:{line_no}")
            if item.id in seen:
                raise ValueError(f"{path}:{line_no}: duplicate id {item.id}")
            seen.add(item.id)
            conversations.append(item)
    return conversations


def check_against_pages(conversations: Sequence[GoldConversation], texts: Dict[int, str]) -> List[str]:
    """Run the single-turn page check over the answer rows (gold pages exist, evidence terms on them)."""
    return verify([c.to_question() for c in conversations if c.expect == "answer"], texts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", nargs="?", type=Path, default=GOLDEN_DIR / "ddia_conversations.jsonl")
    parser.add_argument("--pages", type=Path, default=None)
    args = parser.parse_args()

    conversations = load_conversations(args.path)
    answers = sum(1 for c in conversations if c.expect == "answer")
    clarify = sum(1 for c in conversations if c.expect == "clarify")
    print(f"conversations {len(conversations)} (answer {answers}, clarify {clarify})")
    for name in CATEGORIES:
        print(f"category {name} {sum(1 for c in conversations if c.category == name)}")
    for state in REVIEW_STATES:
        print(f"review {state} {sum(1 for c in conversations if c.review == state)}")
    if args.pages is None:
        print("problems 0 (pages not checked)")
        return
    from rag.ingestion.extract import load_pages

    texts = {p.page_no: p.text for p in load_pages(args.pages)}
    problems = check_against_pages(conversations, texts)
    for problem in problems:
        print(problem)
    print(f"problems {len(problems)}")
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
