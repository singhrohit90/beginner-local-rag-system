import re
from dataclasses import dataclass
from typing import List, Sequence

from rag.generation.prompt import ABSTAIN, SYSTEM_PROMPT, build_user_prompt
from rag.llm import LLM
from rag.retrieval.pipeline import RetrievalConfig, RetrievalPipeline
from rag.trace import Trace
from rag.types import Hit

_CITATION = re.compile(r"\[S(\d+)\]")
_ABSTAIN_PATTERN = re.compile(
    r"cannot answer this from the provided book|can't answer this from the provided book"
    r"|(?:passages?|context|book|text) (?:do(?:es)? not|doesn't|don't) (?:contain|provide|cover|mention|discuss|include)"
    r"|no information (?:about|on)|not (?:mentioned|covered|discussed) in the (?:passages|context|book)",
    re.IGNORECASE,
)


def looks_like_abstention(text: str) -> bool:
    return ABSTAIN.lower() in text.lower() or bool(_ABSTAIN_PATTERN.search(text))


def parse_citations(text: str, n_passages: int) -> List[int]:
    """Passage numbers cited in the answer, in order, without repeats. May include numbers that
    do not exist; citation_is_valid checks that."""
    seen: List[int] = []
    for match in _CITATION.finditer(text):
        number = int(match.group(1))
        if number not in seen:
            seen.append(number)
    return seen


def citation_is_valid(cited: Sequence[int], n_passages: int) -> bool:
    return all(1 <= n <= n_passages for n in cited)


@dataclass
class Answer:
    text: str
    cited: List[int]
    abstained: bool
    prompt_tokens: int
    output_tokens: int


def answer_from_context(llm: LLM, question: str, context: List[Hit]) -> tuple:
    """Returns (Answer, user_prompt)."""
    user_prompt = build_user_prompt(question, context)
    result = llm.generate(SYSTEM_PROMPT, user_prompt, max_output_tokens=600)
    return (
        Answer(
            text=result.text,
            cited=parse_citations(result.text, len(context)),
            abstained=looks_like_abstention(result.text),
            prompt_tokens=result.prompt_tokens,
            output_tokens=result.output_tokens,
        ),
        user_prompt,
    )


class RagPipeline:
    """Retrieval followed by generation. The trace carries both halves, so a wrong answer can be
    traced to the stage that caused it."""

    def __init__(self, retrieval: RetrievalPipeline, llm: LLM):
        self.retrieval = retrieval
        self.llm = llm

    def run(self, query_id: str, question: str, config: RetrievalConfig) -> Trace:
        return self.answer(self.retrieval.run(query_id, question, config))

    def answer(self, trace: Trace) -> Trace:
        """Generate from the context already recorded in a retrieval trace."""
        question = trace.question
        context = trace.stage("context").hits
        answer, prompt = answer_from_context(self.llm, question, context)
        trace.prompt = prompt
        trace.answer = answer.text
        trace.citations = [f"S{n}" for n in answer.cited]
        trace.config["llm"] = self.llm.name
        trace.config["usage"] = {
            "prompt_tokens": answer.prompt_tokens,
            "output_tokens": answer.output_tokens,
            "abstained": answer.abstained,
        }
        return trace
