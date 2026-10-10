"""Export extracted pages as one plain text file with page markers, for tools that accept
.txt but not .jsonl (for example NotebookLM).

    python -m rag.ingestion.export_text data/processed/ddia.pages.jsonl --max-page 580

Each page starts with a line "=== PDF PAGE <n> (printed <n - offset>) ===" so a reader can cite
pages. Empty pages are skipped. --max-page leaves out the back-of-book index.
"""

import argparse
from pathlib import Path
from typing import List

from rag.ingestion.extract import load_pages
from rag.common.types import Page


def render(pages: List[Page], max_page: int, offset: int) -> str:
    parts = []
    for page in pages:
        if page.page_no > max_page or not page.text.strip():
            continue
        printed = page.page_no - offset
        label = f"printed {printed}" if printed >= 1 else "front matter"
        parts.append(f"=== PDF PAGE {page.page_no} ({label}) ===\n{page.text}\n")
    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pages_file", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--max-page", type=int, default=580)
    parser.add_argument("--offset", type=int, default=22)
    args = parser.parse_args()

    out = args.out or args.pages_file.with_name(
        args.pages_file.name.replace(".pages.jsonl", "_for_agent.txt")
    )
    text = render(load_pages(args.pages_file), args.max_page, args.offset)
    out.write_text(text, encoding="utf-8")
    print(f"{len(text.split())} words, {out.stat().st_size / 1e6:.1f} MB -> {out}")


if __name__ == "__main__":
    main()
