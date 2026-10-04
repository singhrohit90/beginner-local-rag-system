"""Build chunk files for each strategy and print a side-by-side comparison.

    python -m rag.chunking.build
    python -m rag.chunking.build --strategies fixed,recursive --size 150
    python -m rag.chunking.build --strategies semantic --embedder st:sentence-transformers/all-mpnet-base-v2

Output: data/processed/chunks/<strategy>.jsonl (and <strategy>.parents.jsonl for parent_child).
The comparison needs no retrieval: it shows chunk sizes, how often chunks start or end mid
sentence, how many code fences were cut, and how often one chunk still holds a question's evidence.
"""

import argparse
import logging
from pathlib import Path
from typing import Any, Dict, List

from rag.chunking import (
    FixedChunker,
    HeadingChunker,
    ParentChildChunker,
    RecursiveChunker,
    SemanticChunker,
)
from rag.chunking.document import Document
from rag.chunking.stats import chunk_stats, evidence_intact, format_table
from rag.config import GOLDEN_DIR, PROCESSED_DIR
from rag.embed import get_embedder
from rag.eval.golden import load_golden

DEFAULT_STRATEGIES = "fixed,recursive,heading,parent_child"


def make_chunker(name: str, args: argparse.Namespace):
    if name == "fixed":
        return FixedChunker(size=args.size, overlap=args.overlap)
    if name == "recursive":
        return RecursiveChunker(size=args.size, overlap=args.overlap)
    if name == "heading":
        return HeadingChunker(max_words=args.max_words)
    if name == "parent_child":
        return ParentChildChunker(child_size=args.child_size)
    if name == "semantic":
        return SemanticChunker(get_embedder(args.embedder), max_words=args.max_words)
    raise SystemExit(f"unknown strategy {name!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=Path, default=PROCESSED_DIR / "ddia.pages.jsonl")
    parser.add_argument("--toc", type=Path, default=PROCESSED_DIR / "ddia.toc.json")
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR / "ddia_questions.jsonl")
    parser.add_argument("--out", type=Path, default=PROCESSED_DIR / "chunks")
    parser.add_argument("--strategies", default=DEFAULT_STRATEGIES)
    parser.add_argument("--embedder", default="st:sentence-transformers/all-mpnet-base-v2")
    parser.add_argument("--size", type=int, default=200, help="words per chunk, fixed/recursive")
    parser.add_argument("--overlap", type=int, default=40)
    parser.add_argument("--max-words", type=int, default=300, help="heading and semantic")
    parser.add_argument("--child-size", type=int, default=100)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    doc = Document.from_files(args.pages, args.toc)
    questions = load_golden(args.golden) if args.golden.exists() else []
    page_texts = {p.page_no: p.text for p in doc.pages}
    print(
        f"body: PDF pages {doc.page_nos[0]}-{doc.page_nos[-1]}, "
        f"{len(doc.text.split())} words, {len(questions)} golden questions\n"
    )

    rows: List[Dict[str, Any]] = []
    for name in [s.strip() for s in args.strategies.split(",") if s.strip()]:
        result = make_chunker(name, args).chunk(doc)
        result.save(args.out)
        rows.append(
            {
                "strategy": name,
                **chunk_stats(result.chunks),
                "intact": evidence_intact(result.chunks, questions, page_texts)["rate"],
            }
        )
        if result.parents:
            parents = list(result.parents.values())
            rows.append(
                {
                    "strategy": f"{name} (parents)",
                    **chunk_stats(parents),
                    "intact": evidence_intact(parents, questions, page_texts)["rate"],
                }
            )
    print(format_table(rows))
    print(f"\nchunk files written to {args.out}")


if __name__ == "__main__":
    main()
