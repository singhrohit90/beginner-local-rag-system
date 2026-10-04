"""Step 1: PDF -> list of clean pages. Writes data/processed/<name>.pages.jsonl.

Pages are numbered by PDF index (1-based), not by the printed number, so gold labels and
chunk page ranges always refer to the same thing.
"""

import argparse
import json
import logging
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import List

import pymupdf

from rag.config import (
    FOOTER_FRACTION,
    HEADER_FRACTION,
    PROCESSED_DIR,
    REPEAT_THRESHOLD,
)
from rag.ingest.clean import clean_block, is_noise, normalize_key
from rag.types import Page

logger = logging.getLogger(__name__)


@dataclass
class _Block:
    text: str
    in_margin: bool


def _read_blocks(
    pdf_path: Path, header_fraction: float, footer_fraction: float
) -> List[List[_Block]]:
    pages: List[List[_Block]] = []
    with pymupdf.open(pdf_path) as doc:
        for page in doc:
            height = page.rect.height
            blocks = []
            for x0, y0, x1, y1, text, _no, kind in page.get_text("blocks", sort=True):
                if kind != 0:  # 0 = text, 1 = image
                    continue
                in_margin = y1 <= height * header_fraction or y0 >= height * (
                    1 - footer_fraction
                )
                blocks.append(_Block(text=text, in_margin=in_margin))
            pages.append(blocks)
    return pages


def _repeated_margin_keys(pages: List[List[_Block]], threshold: float) -> set:
    """Margin texts that appear on enough pages to be running headers/footers."""
    counts: Counter = Counter()
    for blocks in pages:
        # count each key once per page
        counts.update({normalize_key(b.text) for b in blocks if b.in_margin})
    min_pages = max(2, int(len(pages) * threshold))
    return {key for key, n in counts.items() if key and n >= min_pages}


def build_pages(
    raw: List[List[_Block]], repeat_threshold: float = REPEAT_THRESHOLD
) -> List[Page]:
    repeated = _repeated_margin_keys(raw, repeat_threshold)
    pages: List[Page] = []
    for index, blocks in enumerate(raw, start=1):
        kept = []
        for block in blocks:
            text = clean_block(block.text)
            if is_noise(text):
                continue
            if block.in_margin and normalize_key(text) in repeated:
                continue
            kept.append(text)
        pages.append(Page(page_no=index, text="\n\n".join(kept)))
    return pages


def extract_pages(
    pdf_path: Path,
    header_fraction: float = HEADER_FRACTION,
    footer_fraction: float = FOOTER_FRACTION,
    repeat_threshold: float = REPEAT_THRESHOLD,
) -> List[Page]:
    raw = _read_blocks(Path(pdf_path), header_fraction, footer_fraction)
    pages = build_pages(raw, repeat_threshold)
    empty = [p.page_no for p in pages if not p.text]
    logger.info("Extracted %d pages, %d empty %s", len(pages), len(empty), empty[:20])
    return pages


def save_pages(pages: List[Page], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for page in pages:
            f.write(json.dumps({"page_no": page.page_no, "text": page.text}) + "\n")


def load_pages(path: Path) -> List[Page]:
    with open(path, encoding="utf-8") as f:
        return [Page(**json.loads(line)) for line in f if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract and clean pages from a PDF")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    out = args.out or PROCESSED_DIR / f"{args.pdf.stem}.pages.jsonl"
    pages = extract_pages(args.pdf)
    save_pages(pages, out)
    words = sum(len(p.text.split()) for p in pages)
    print(f"{len(pages)} pages, {words} words -> {out}")


if __name__ == "__main__":
    main()
