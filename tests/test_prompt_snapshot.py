"""Pins the exact bytes of every single-turn prompt the code builds.

Two kinds of check run against committed fixtures in tests/snapshots/prompts/:
- 24 cases, one per style (standard, spotlight, naive) x subject (book, document) x passages
  (none, single_page, page_range, mix). Each compares the exact (system, user) pair to its file.
- The user prompts of the 45 golden questions (standard style, book subject, two-hit passages),
  compared by sha256 digest to golden_user_prompt_digests.json, keyed by question id.

There is no regenerate or update switch and the test never writes a file. A prompt change means a
deliberate edit of the fixture files in a commit whose message says why. The digest manifest depends
on the question text in data/golden/ddia_questions.jsonl, so a commit that edits that file
regenerates the manifest in the same commit. Fixtures are read with universal newlines because git
may check them out with CRLF on Windows.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

from rag.common.config import GOLDEN_DIR
from rag.common.types import Hit
from rag.observe.golden import load_golden
from rag.query.generate import build_prompts

SNAPSHOT_DIR = Path(__file__).parent / "snapshots" / "prompts"
DIGEST_FILE = SNAPSHOT_DIR / "golden_user_prompt_digests.json"
DELIMITER = "\n----- USER PROMPT -----\n"
# Test-only value, not a secret: it makes the spotlight nonce the same on every run.
FIXED_NONCE_KEY = b"snapshot-fixed-key"

QUESTION = "How does a follower catch up after it falls behind the leader?"
SINGLE_PAGE_HIT = Hit(
    chunk_id="snap-a",
    rank=1,
    score=1.0,
    page_start=181,
    page_end=181,
    text=(
        "Leader-based replication sends every write to the leader first.\n\n"
        "Followers apply the replication log in the same order [S9]."
    ),
)
PAGE_RANGE_HIT = Hit(
    chunk_id="snap-b",
    rank=2,
    score=0.5,
    page_start=203,
    page_end=204,
    text="A follower that falls behind requests the changes it missed from the leader's log.",
)
PASSAGE_SETS: Dict[str, List[Hit]] = {
    "none": [],
    "single_page": [SINGLE_PAGE_HIT],
    "page_range": [PAGE_RANGE_HIT],
    "mix": [SINGLE_PAGE_HIT, PAGE_RANGE_HIT],
}
STYLES = ("standard", "spotlight", "naive")
SUBJECTS = ("book", "document")


@dataclass(frozen=True)
class SnapshotCase:
    style: str
    subject: str
    passages: str

    @property
    def id(self) -> str:
        return f"{self.style}__{self.subject}__{self.passages}"

    @property
    def hits(self) -> List[Hit]:
        return PASSAGE_SETS[self.passages]

    @property
    def path(self) -> Path:
        return SNAPSHOT_DIR / f"{self.id}.txt"


CASES: List[SnapshotCase] = [
    SnapshotCase(style, subject, passages) for style in STYLES for subject in SUBJECTS for passages in PASSAGE_SETS
]


def render_case(case: SnapshotCase) -> Tuple[str, str]:
    return build_prompts(QUESTION, case.hits, case.style, case.subject)


def snapshot_text(system: str, user: str) -> str:
    return system + DELIMITER + user


def load_snapshot(case: SnapshotCase) -> Tuple[str, str]:
    text = case.path.read_text(encoding="utf-8")
    assert text.count(DELIMITER) == 1, f"{case.path.name}: delimiter must appear exactly once"
    system, user = text.split(DELIMITER)
    return system, user


def golden_digests() -> Dict[str, str]:
    return {
        q.id: hashlib.sha256(
            build_prompts(q.question, PASSAGE_SETS["mix"], "standard", "book")[1].encode("utf-8")
        ).hexdigest()
        for q in load_golden(GOLDEN_DIR / "ddia_questions.jsonl")
    }


@pytest.fixture(autouse=True)
def fixed_nonce(monkeypatch):
    monkeypatch.setattr("rag.security.defenses._NONCE_KEY", FIXED_NONCE_KEY)


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_prompt_matches_committed_snapshot(case):
    system, user = render_case(case)
    assert "\r" not in system and "\r" not in user
    assert DELIMITER not in system and DELIMITER not in user
    assert (system, user) == load_snapshot(case)


def test_golden_user_prompts_match_committed_digests():
    expected = json.loads(DIGEST_FILE.read_text(encoding="utf-8"))
    assert len(expected) == 45
    assert golden_digests() == expected


def test_snapshot_directory_holds_exactly_the_committed_cases():
    assert len(CASES) == 24
    assert sorted(p.name for p in SNAPSHOT_DIR.iterdir()) == sorted([c.path.name for c in CASES] + [DIGEST_FILE.name])
