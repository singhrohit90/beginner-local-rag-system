"""Tests for the history helpers in rag/query/history.py (window, neutralize, render_block, the
budget constants) and the D-11 worst-case budget.

The budget test sends a rendered history block through the real prompt builders, so a wording
change to the header or the builders is caught, not only the arithmetic of the constants. The
output budget it adds comes from docs/models.md (3000 thinking tokens, Generator row) and
rag/query/generate.py (600 answer tokens, answer_from_context).
"""

import dataclasses
from pathlib import Path
from typing import List, Optional

import pytest

from rag.common.types import Hit
from rag.query.generate import _CITATION, build_prompts
from rag.query.guard import BLOCKED, filter_output, scan_text
from rag.query.history import (
    CONVERSATION_MAX_TURNS,
    DEFANG_MARKER,
    HISTORY_ANSWER_MAX_WORDS,
    HISTORY_BLOCK_MAX_WORDS,
    HISTORY_HEADER,
    HISTORY_QUESTION_MAX_WORDS,
    HISTORY_WINDOW_TURNS,
    HISTORY_WITHHELD,
    MODEL_CONTEXT_TOKENS,
    TOKENS_PER_WORD,
    TRUNCATION_MARKER,
    HistoryTurn,
    neutralize,
    render_block,
    window,
)
from rag.query.prompt import CANARY, DOCUMENT_SYSTEM_PROMPT, SYSTEM_PROMPT
from rag.security.defenses import SPOTLIGHT_ADDENDUM
from rag.security.fixtures import POISONED_DOCS

THINKING_TOKENS = 3000  # the client's reasoning budget, docs/models.md Generator row
ANSWER_TOKENS = 600  # max_output_tokens in rag/query/generate.py answer_from_context

QUESTION_60_WORDS = " ".join(["word"] * HISTORY_QUESTION_MAX_WORDS)
# 1999 characters, about 400 words of prose; the API caps a question at max_length=2000 (rag/api/main.py)
QUESTION_2000_CHARS = ("data " * 400).strip()


def turn(
    question: str = "What is a follower?",
    answer: str = "A replica of the leader.",
    rewritten: Optional[str] = None,
) -> HistoryTurn:
    return HistoryTurn(question, answer, asked_at="2026-10-22T09:30:00+00:00", rewritten=rewritten)


def maximal_turns(n: int = 6) -> List[HistoryTurn]:
    """Turns whose question and answer both exceed their per-turn caps."""
    return [turn(" ".join([f"q{i}"] * 80), " ".join([f"a{i}"] * 80)) for i in range(n)]


def budget_hits() -> List[Hit]:
    """Five 300-word passages, 1500 words: select_context's word cap; book chunks are at most 300 words."""
    return [Hit(f"w{i}", i, 1.0, 100 + i, 100 + i, " ".join(["data"] * 300)) for i in range(1, 6)]


@pytest.mark.parametrize(
    "question", [QUESTION_60_WORDS, QUESTION_2000_CHARS], ids=["60_word_question", "2000_char_question"]
)
def test_worst_case_prompt_fits_the_context_window(question):
    # A pathological 1000-word question would exceed an 8192-token window; refusing it before the
    # model call is Phase 2's hard cap (PRMT-04). Plan-time arithmetic with the planned module:
    # worst case 2544 words, 7416 tokens for the 2000-character question.
    block = render_block(window(maximal_turns()))
    assert block
    assert "q5" in block
    for style in ("standard", "spotlight", "naive"):
        for subject in ("book", "document"):
            system, user = build_prompts(question, budget_hits(), style, subject, history_block=block)
            assert block in user
            words = len(system.split()) + len(user.split())
            total = words * TOKENS_PER_WORD + THINKING_TOKENS + ANSWER_TOKENS
            assert total <= MODEL_CONTEXT_TOKENS, (style, subject, words)


def test_budget_constants_fit_the_context_window():
    system_words = max(len((p + SPOTLIGHT_ADDENDUM).split()) for p in (SYSTEM_PROMPT, DOCUMENT_SYSTEM_PROMPT))
    words = system_words + 1500 + HISTORY_BLOCK_MAX_WORDS + HISTORY_QUESTION_MAX_WORDS
    assert words * TOKENS_PER_WORD + THINKING_TOKENS + ANSWER_TOKENS <= MODEL_CONTEXT_TOKENS
