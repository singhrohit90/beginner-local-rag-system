import re
from dataclasses import dataclass
from typing import List, Sequence

from rag.query.prompt import ABSTAIN, ABSTAIN_DOCUMENT, DOCUMENT_SYSTEM_PROMPT, SYSTEM_PROMPT, build_user_prompt
from rag.common.llm import LLM
from rag.common.types import Hit

_CITATION = re.compile(r"\[S(\d+)\]")
_ABSTAIN_PATTERN = re.compile(
    r"(?:cannot|can't) answer this from the provided (?:book|document)"
    r"|(?:passages?|context|book|document|text) (?:do(?:es)? not|doesn't|don't) (?:contain|provide|cover|mention|discuss|include)"
    r"|no information (?:about|on)|not (?:mentioned|covered|discussed) in the (?:passages|context|book)",
    re.IGNORECASE,
)


def looks_like_abstention(text: str) -> bool:
    lowered = text.lower()
    return ABSTAIN.lower() in lowered or ABSTAIN_DOCUMENT.lower() in lowered or bool(_ABSTAIN_PATTERN.search(text))


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


def answer_from_context(
    llm: LLM, question: str, context: List[Hit], style: str = "standard", subject: str = "book"
) -> tuple:
    """Returns (Answer, user_prompt). style picks the prompts:
    standard   the production prompt, which tells the model to ignore instructions in passages
    spotlight  also wraps passages in nonce tags and repeats the warning (rag.security.defenses)
    naive      a first-draft prompt with no injection rules, used only as a baseline in tests
    subject    "book" is the DDIA prompt the golden set was measured with; "document" is for uploads"""
    base = DOCUMENT_SYSTEM_PROMPT if subject == "document" else SYSTEM_PROMPT
    if style == "spotlight":
        from rag.security.defenses import SPOTLIGHT_ADDENDUM, spotlight_user_prompt

        system, user_prompt = base + SPOTLIGHT_ADDENDUM, spotlight_user_prompt(question, context)
    elif style == "naive":
        from rag.security.defenses import NAIVE_SYSTEM_PROMPT

        system, user_prompt = NAIVE_SYSTEM_PROMPT, build_user_prompt(question, context)
    elif style == "standard":
        system, user_prompt = base, build_user_prompt(question, context)
    else:
        raise ValueError(f"unknown prompt style {style!r}")
    result = llm.generate(system, user_prompt, max_output_tokens=600)
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
