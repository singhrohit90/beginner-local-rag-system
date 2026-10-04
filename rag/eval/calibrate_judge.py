"""Measure how far a judge model can be trusted, using cases whose right answer is known.

    python -m rag.eval.calibrate_judge --judge ollama:qwen2.5:7b

correctness:   reference answer judged against its own question         -> should be CORRECT
               another question's reference judged against this one     -> should be INCORRECT
faithfulness:  reference answer with the gold pages as context          -> should be FAITHFUL
               the same answer with unrelated pages as context          -> should be UNFAITHFUL

These are easy cases (identical text, or unrelated text), so a judge that fails them cannot be
trusted. Passing them does not prove it handles subtle errors, such as a nearly right answer.
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Tuple

from rag.config import GOLDEN_DIR, PROCESSED_DIR
from rag.eval.golden import GoldQuestion, load_golden
from rag.eval.judge import judge_correctness, judge_faithfulness
from rag.ingest.extract import load_pages
from rag.llm import get_llm
from rag.log import setup_logging
from rag.types import Hit

WORD_LIMIT = 700  # keep contexts inside a small local model's window


def page_hit(pages: Dict[int, str], start: int, end: int) -> Hit:
    text = "\n".join(pages.get(p, "") for p in range(start, end + 1))
    return Hit(f"p{start}", 1, 1.0, start, end, " ".join(text.split()[:WORD_LIMIT]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge", default="ollama:qwen2.5:7b")
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR / "ddia_questions.jsonl")
    parser.add_argument("--pages", type=Path, default=PROCESSED_DIR / "ddia.pages.jsonl")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    setup_logging()

    questions: List[GoldQuestion] = [q for q in load_golden(args.golden) if q.answerable]
    if args.limit:
        questions = questions[: args.limit]
    pages = {p.page_no: p.text for p in load_pages(args.pages)}
    judge = get_llm(args.judge)

    cases: List[Tuple[str, bool, GoldQuestion, str]] = []  # group, expected, question, payload
    for i, q in enumerate(questions):
        other = questions[(i + 1) % len(questions)]
        cases.append(("correct: own reference", True, q, q.reference_answer))
        cases.append(("correct: another question's reference", False, q, other.reference_answer))
        cases.append(("faithful: gold pages as context", True, q, q.reference_answer))
        cases.append(("faithful: unrelated pages as context", False, q, q.reference_answer))

    def run(case: Tuple[str, bool, GoldQuestion, str]):
        group, expected, q, answer = case
        if group.startswith("correct"):
            return judge_correctness(judge, q.question, q.reference_answer, answer)
        start, end = q.gold_pages[0]
        if expected:
            context = [page_hit(pages, s, e) for s, e in q.gold_pages]
        else:
            shift = 150 if start < 300 else -150
            context = [page_hit(pages, start + shift, start + shift)]
        return judge_faithfulness(judge, q.question, context, answer)

    with ThreadPoolExecutor(args.workers) as pool:
        verdicts = list(pool.map(run, cases))

    groups: Dict[str, List[Tuple[bool, object]]] = {}
    for (group, expected, q, _), verdict in zip(cases, verdicts):
        groups.setdefault(group, []).append((expected, verdict.value))
    print(f"\njudge: {judge.name}   questions: {len(questions)}")
    for group, rows in groups.items():
        right = sum(1 for expected, value in rows if value is expected)
        unparsed = sum(1 for _, value in rows if value is None)
        print(f"  {group:<40} right {right}/{len(rows)}  ({right / len(rows):.0%})  unparseable {unparsed}")
    out = PROCESSED_DIR / "judge_calibration.json"
    out.write_text(
        json.dumps({g: [[e, v] for e, v in rows] for g, rows in groups.items()}, indent=1),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
