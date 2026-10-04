"""Helper for writing the golden set: find which pages mention a term.

    python -m rag.eval.find_pages data/processed/ddia.pages.jsonl "SSTable" "LSM-tree"
"""

import argparse
import re
from pathlib import Path

from rag.ingest.extract import load_pages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pages_file", type=Path)
    parser.add_argument("terms", nargs="+")
    parser.add_argument("--context", type=int, default=70, help="characters around the match")
    parser.add_argument("--max", type=int, default=15, help="max matches per term")
    args = parser.parse_args()

    pages = load_pages(args.pages_file)
    for term in args.terms:
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        matches = [p for p in pages if pattern.search(p.text)]
        print(f"\n{term!r}: {len(matches)} pages")
        for page in matches[: args.max]:
            m = pattern.search(page.text)
            start = max(0, m.start() - args.context)
            snippet = page.text[start : m.end() + args.context].replace("\n", " ")
            print(f"  p{page.page_no}: ...{snippet}...")


if __name__ == "__main__":
    main()
