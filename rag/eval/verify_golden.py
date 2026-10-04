"""Check a golden file against the extracted pages before trusting it.

    python -m rag.eval.verify_golden data/golden/ddia_questions.jsonl data/processed/ddia.pages.jsonl

For every answerable question it checks that the gold pages exist and that each evidence term is
on those pages, and it lists other pages where the term also appears (distractors a retriever may
return instead). For unanswerable questions it reports whether the evidence terms appear anywhere,
so a "not in the book" claim is checked rather than assumed.
"""

import argparse
import re
from pathlib import Path
from typing import Dict, List, Sequence

from rag.eval.golden import GoldQuestion, load_golden
from rag.ingest.extract import load_pages


def _pages_with(term: str, texts: Dict[int, str]) -> List[int]:
    # Any run of whitespace in the term matches any run in the page, because code listings
    # align columns with extra spaces ("required string       userName").
    words = [re.escape(w) for w in term.split()]
    pattern = re.compile(r"\s+".join(words), re.IGNORECASE)
    return [n for n, text in texts.items() if pattern.search(text)]


def verify(questions: Sequence[GoldQuestion], texts: Dict[int, str]) -> List[str]:
    """Return human-readable problems. An empty list means every check passed."""
    problems: List[str] = []
    for q in questions:
        gold_numbers = {n for start, end in q.gold_pages for n in range(start, end + 1)}
        missing = sorted(n for n in gold_numbers if n not in texts)
        if missing:
            problems.append(f"{q.id}: gold pages {missing} do not exist in the extracted pages")
            continue
        if q.answerable and len(q.gold_pages) > 1 and q.evidence_terms:
            # A multi-range question claims each range holds evidence, so each needs a term.
            for start, end in q.gold_pages:
                span = set(range(start, end + 1))
                if not any(span & set(_pages_with(t, texts)) for t in q.evidence_terms):
                    problems.append(
                        f"{q.id}: gold range {[start, end]} contains none of the evidence terms; "
                        "add a term that proves this range is needed, or drop the range"
                    )
        for term in q.evidence_terms:
            found = _pages_with(term, texts)
            if q.answerable and not any(n in gold_numbers for n in found):
                problems.append(
                    f"{q.id}: {term!r} is not on gold pages {q.gold_pages}; it appears on PDF "
                    f"pages {found[:8] or 'nowhere'}"
                )
            if not q.answerable and q.type == "unanswerable" and found:
                problems.append(
                    f"{q.id}: marked unanswerable but {term!r} appears on PDF pages {found[:8]}"
                )
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("golden", type=Path)
    parser.add_argument("pages_file", type=Path)
    args = parser.parse_args()

    questions = load_golden(args.golden)
    texts = {p.page_no: p.text for p in load_pages(args.pages_file)}
    problems = verify(questions, texts)
    for q in questions:
        for term in q.evidence_terms:
            found = _pages_with(term, texts)
            gold = {n for s, e in q.gold_pages for n in range(s, e + 1)}
            elsewhere = [n for n in found if n not in gold]
            print(f"{q.id} {term!r}: on gold {sorted(set(found) & gold)}, elsewhere {elsewhere[:6]}")
    print(f"\n{len(questions)} questions, {len(problems)} problems")
    for problem in problems:
        print("  PROBLEM:", problem)
    raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    main()
