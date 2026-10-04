"""LLM-as-judge for answers. Two separate judgements, each in its own call:

correctness: does the candidate state the key facts of the reference answer?
faithfulness: is every claim in the candidate supported by the retrieved passages?

They are separate so the faithfulness judge never sees the reference answer: an answer can be
correct by luck (outside knowledge) yet unfaithful to the context, and that difference is exactly
what separates a retrieval problem from a generation problem. Use a different model from the
generator, since models tend to rate their own style highly. Judges are not ground truth: check a
sample by hand (the run saves the reasons) before trusting the percentages.
"""

import json
import re
from dataclasses import dataclass
from typing import List, Optional

from rag.generation.prompt import format_context
from rag.llm import LLM
from rag.types import Hit

CORRECTNESS_SYSTEM = """You grade answers to questions about a book. You are given a question, a reference answer taken from the book, and a candidate answer.
Step 1: list the key facts in the reference answer.
Step 2: check whether each key fact appears in the candidate, in any wording or order.
The candidate is correct if every key fact appears and nothing in the candidate directly conflicts with a statement in the reference.
Extra sentences, extra detail and a different structure are NOT a conflict. A statement that is merely absent from the reference is not a contradiction, so ignore it.
The candidate is incorrect only if it leaves out a key fact, directly conflicts with the reference, or says it cannot answer.
Reply with JSON only, no other text: {"correct": true or false, "reason": "<one short sentence naming the missing or conflicting fact, or saying all key facts are present>"}"""

FAITHFULNESS_SYSTEM = """You check whether an answer is supported by the given passages. Consider only the passages, never outside knowledge, even if the answer is true in the real world.
List the factual claims in the answer and check each against the passages. Citation labels such as [S1] are not claims.
Reply with JSON only, no other text: {"faithful": true or false, "unsupported": ["<claim not supported>", ...]}
faithful is true only if every factual claim is supported by the passages."""


@dataclass
class Verdict:
    value: Optional[bool]  # None when the judge reply could not be parsed
    reason: str = ""


def parse_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of a model reply, tolerating code fences and chatter."""
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def judge_correctness(judge: LLM, question: str, reference: str, answer: str) -> Verdict:
    user = f"Question: {question}\n\nReference answer: {reference}\n\nCandidate answer: {answer}"
    parsed = parse_json(
        judge.generate(CORRECTNESS_SYSTEM, user, max_output_tokens=1500, json_mode=True).text
    )
    if not parsed or not isinstance(parsed.get("correct"), bool):
        return Verdict(None, "unparseable judge reply")
    return Verdict(parsed["correct"], str(parsed.get("reason", "")))


FACTS_SYSTEM = """You check whether an answer states specific facts. You are given an answer and a numbered list of facts.
For each fact, decide whether the answer clearly states it, in any wording. A fact the answer omits, or contradicts, is not stated.
Ignore everything in the answer that is not related to a listed fact: extra sentences, extra detail and a different order never make a fact false.
Reply with JSON only, no other text, in this form, with one entry per fact in order:
{"results": [{"n": 1, "stated": true, "quote": "<short quote from the answer, or empty>"}, ...]}"""


@dataclass
class FactVerdict:
    stated: List[Optional[bool]]  # one per fact; None when the reply could not be parsed
    missing: List[str]

    @property
    def correct(self) -> Optional[bool]:
        if not self.stated or any(s is None for s in self.stated):
            return None
        return all(self.stated)


def judge_facts(judge: LLM, answer: str, facts: List[str]) -> FactVerdict:
    numbered = "\n".join(f"{i}. {fact}" for i, fact in enumerate(facts, start=1))
    user = f"Facts:\n{numbered}\n\nAnswer:\n{answer}"
    parsed = parse_json(judge.generate(FACTS_SYSTEM, user, max_output_tokens=1500, json_mode=True).text)
    results = parsed.get("results") if parsed else None
    if not isinstance(results, list) or len(results) != len(facts):
        return FactVerdict([None] * len(facts), [])
    stated: List[Optional[bool]] = []
    for item in results:
        value = item.get("stated") if isinstance(item, dict) else None
        stated.append(value if isinstance(value, bool) else None)
    return FactVerdict(stated, [f for f, s in zip(facts, stated) if s is False])


def judge_faithfulness(judge: LLM, question: str, context: List[Hit], answer: str) -> Verdict:
    user = (
        f"Passages:\n\n{format_context(context)}\n\nQuestion: {question}\n\nAnswer to check: {answer}"
    )
    parsed = parse_json(
        judge.generate(FAITHFULNESS_SYSTEM, user, max_output_tokens=1500, json_mode=True).text
    )
    if not parsed or not isinstance(parsed.get("faithful"), bool):
        return Verdict(None, "unparseable judge reply")
    unsupported = parsed.get("unsupported") or []
    return Verdict(parsed["faithful"], "; ".join(str(u) for u in unsupported))
