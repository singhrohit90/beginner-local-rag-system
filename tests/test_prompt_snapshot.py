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
from rag.common.llm import FakeLLM
from rag.common.trace import Trace
from rag.common.types import Hit
from rag.observe.golden import load_golden
from rag.query.generate import answer_from_context, build_prompts
from rag.query.pipeline import RagPipeline
from rag.query.prompt import build_user_prompt
from rag.security.defenses import spotlight_user_prompt

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
# Shaped like rag.query.history.render_block output but defined here, so the seam tests do not depend on it.
HISTORY_BLOCK_SAMPLE = (
    "Earlier turns (sample block for the seam tests):\n"
    "User: What is a follower?\n"
    "Assistant: A replica that applies the leader's log.\n\n"
)
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


def snapshot_trace() -> Trace:
    trace = Trace(query_id="snapshot", question=QUESTION)
    trace.record("context", "transform", list(PASSAGE_SETS["mix"]))
    return trace


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


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_empty_history_equals_no_history_equals_snapshot(case):
    """D-07: an empty history block adds nothing. Omitted, "" and None give the snapshot bytes; a careless
    caller passing None must get the old prompt, not the text "None"."""
    without = render_case(case)
    explicit = build_prompts(QUESTION, case.hits, case.style, case.subject, history_block="")
    none_given = build_prompts(QUESTION, case.hits, case.style, case.subject, history_block=None)
    assert without == explicit == none_given == load_snapshot(case)
    builder = spotlight_user_prompt if case.style == "spotlight" else build_user_prompt
    assert builder(QUESTION, case.hits) == builder(QUESTION, case.hits, history_block="") == load_snapshot(case)[1]


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_history_block_position(case):
    """D-07/D-08: a non-empty block goes after the passages and their blank line, directly before the
    Question line (and so before the spotlight Reminder); the system prompt does not change."""
    old_system, old_user = load_snapshot(case)
    system, user = build_prompts(QUESTION, case.hits, case.style, case.subject, history_block=HISTORY_BLOCK_SAMPLE)
    assert system == old_system
    assert user == old_user.replace("Question: " + QUESTION, HISTORY_BLOCK_SAMPLE + "Question: " + QUESTION, 1)
    assert user.count(HISTORY_BLOCK_SAMPLE) == 1
    if case.style == "spotlight":
        assert user.index("Reminder:") > user.index(HISTORY_BLOCK_SAMPLE)


@pytest.mark.parametrize("style, subject", [("standard", "book"), ("spotlight", "document"), ("naive", "book")])
def test_pipeline_answer_and_stream_forward_history_block(style, subject):
    llm = FakeLLM(lambda s, u: "Followers replay the leader log [S1].")
    pipeline = RagPipeline(retrieval=None, llm=llm, style=style, subject=subject)
    answered = pipeline.answer(snapshot_trace(), history_block=HISTORY_BLOCK_SAMPLE)
    events = list(pipeline.stream(snapshot_trace(), history_block=HISTORY_BLOCK_SAMPLE))
    plain = pipeline.answer(snapshot_trace())
    expected = build_prompts(QUESTION, PASSAGE_SETS["mix"], style, subject, history_block=HISTORY_BLOCK_SAMPLE)
    assert len(llm.calls) == 3
    assert (llm.calls[0][0], llm.calls[0][1]) == expected
    assert (llm.calls[1][0], llm.calls[1][1]) == expected
    assert answered.prompt == expected[1]
    assert events[-1][0] == "final"
    assert (llm.calls[2][0], llm.calls[2][1]) == load_snapshot(SnapshotCase(style, subject, "mix"))
    assert plain.prompt == llm.calls[2][1]


def test_answer_from_context_forwards_history_block():
    llm = FakeLLM(lambda s, u: "ok [S1].")
    _, prompt = answer_from_context(llm, QUESTION, PASSAGE_SETS["mix"], history_block=HISTORY_BLOCK_SAMPLE)
    expected = build_prompts(QUESTION, PASSAGE_SETS["mix"], history_block=HISTORY_BLOCK_SAMPLE)[1]
    assert prompt == llm.calls[0][1] == expected
    assert HISTORY_BLOCK_SAMPLE in prompt
