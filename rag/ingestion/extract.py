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
from typing import List, Optional

import pymupdf

from rag.common.config import (
    FOOTER_FRACTION,
    HEADER_FRACTION,
    PROCESSED_DIR,
    REPEAT_THRESHOLD,
)
from rag.ingestion.clean import clean_block, is_noise, is_running_footer, normalize_key
from rag.common.types import Page

logger = logging.getLogger(__name__)


@dataclass
class _Block:
    text: str
    in_margin: bool
    is_code: bool = False


_MONO_FLAG = 8  # PyMuPDF span flag bit for monospaced fonts
_SUPERSCRIPT_FLAG = 1
_CODE_SHARE = 0.6  # a block is code when this share of its characters is monospaced


def _line_text(spans: List[dict]) -> str:
    """Join the spans of one line. Superscripts (footnote marks, exponents) get a ^ prefix so
    "fan-out" + superscript "ii" reads "fan-out^ii" instead of the fused "fan-outii"."""
    parts = []
    for span in spans:
        text = span["text"]
        if span["flags"] & _SUPERSCRIPT_FLAG and not span["flags"] & _MONO_FLAG and text.strip():
            text = "^" + text.strip()
        parts.append(text)
    return "".join(parts)


def _block_text(block: dict) -> tuple:
    """Return (text, is_code) for one PyMuPDF dict block."""
    lines = block["lines"]
    mono = total = 0
    for line in lines:
        for span in line["spans"]:
            total += len(span["text"])
            if span["flags"] & _MONO_FLAG:
                mono += len(span["text"])
    is_code = total > 0 and mono / total >= _CODE_SHARE
    if not is_code:
        return "\n".join(_line_text(line["spans"]) for line in lines), False

    # Code keeps its line breaks and indentation. Indent is measured in character cells.
    first = next((s for line in lines for s in line["spans"] if s["text"].strip()), None)
    if first is None:  # monospaced but only blanks: nothing to keep, and no character width to measure
        return "\n".join(_line_text(line["spans"]) for line in lines), False
    cell =(first["bbox"][2] - first["bbox"][0]) / max(len(first["text"]), 1) or 1.0
    left = min(line["bbox"][0] for line in lines)
    out = []
    for line in lines:
        indent = max(0, round((line["bbox"][0] - left) / cell))
        out.append(" " * indent + "".join(s["text"] for s in line["spans"]).rstrip())
    return "\n".join(out), True


def _read_blocks(
    pdf_path: Path, header_fraction: float, footer_fraction: float, max_page_chars: Optional[int] = None
) -> List[List[_Block]]:
    pages: List[List[_Block]] = []
    with pymupdf.open(pdf_path) as doc:
        for page in doc:
            height = page.rect.height
            blocks = []
            chars = 0
            for block in page.get_text("dict", sort=True)["blocks"]:
                if block["type"] != 0:  # 0 = text, 1 = image
                    continue
                if max_page_chars is not None and chars >= max_page_chars:
                    break  # a page this large is hostile or broken; keep what we have
                _x0, y0, _x1, y1 = block["bbox"]
                centre = (y0 + y1) / 2  # a footer can start a little above the zone edge
                in_margin = centre <= height * header_fraction or centre >= height * (
                    1 - footer_fraction
                )
                text, is_code = _block_text(block)
                if max_page_chars is not None:
                    text = text[: max_page_chars - chars]  # one huge block is cut as well
                chars += len(text)
                blocks.append(_Block(text=text, in_margin=in_margin, is_code=is_code))
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
        kept: List[str] = []
        code_run: List[str] = []  # consecutive code blocks merge into one fenced block

        def flush_code() -> None:
            if code_run:
                kept.append("```\n" + "\n".join(code_run) + "\n```")
                code_run.clear()

        for block in blocks:
            if block.is_code and not block.in_margin:
                code = "\n".join(line.rstrip() for line in block.text.splitlines()).strip("\n")
                if code.strip():
                    code_run.append(code)
                continue
            text = clean_block(block.text)
            if is_noise(text):
                continue
            if block.in_margin and (
                normalize_key(text) in repeated or is_running_footer(text)
            ):
                continue
            flush_code()
            kept.append(text)
        flush_code()
        pages.append(Page(page_no=index, text="\n\n".join(kept)))
    return pages


def extract_pages(
    pdf_path: Path,
    header_fraction: float = HEADER_FRACTION,
    footer_fraction: float = FOOTER_FRACTION,
    repeat_threshold: float = REPEAT_THRESHOLD,
    max_page_chars: Optional[int] = None,  # None = no cap (CLI); the API sandbox sets one
) -> List[Page]:
    raw = _read_blocks(Path(pdf_path), header_fraction, footer_fraction, max_page_chars)
    pages = build_pages(raw, repeat_threshold)
    empty = [p.page_no for p in pages if not p.text]
    logger.info("Extracted %d pages, %d empty %s", len(pages), len(empty), empty[:20])
    return pages


def save_pages(pages: List[Page], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for page in pages:
            f.write(json.dumps({"page_no": page.page_no, "text": page.text}) + "\n")


def extract_toc(pdf_path: Path) -> List[dict]:
    """The PDF's bookmarks as [{level, title, page}], page being the 1-based PDF index.

    Used later by the heading-aware chunker and for section metadata. Empty if the PDF has none.
    """
    with pymupdf.open(Path(pdf_path)) as doc:
        return [{"level": lv, "title": t, "page": p} for lv, t, p in doc.get_toc()]


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
    toc = extract_toc(args.pdf)
    toc_out = out.with_name(out.name.replace(".pages.jsonl", ".toc.json"))
    toc_out.write_text(json.dumps(toc, indent=1), encoding="utf-8")
    words = sum(len(p.text.split()) for p in pages)
    print(f"{len(pages)} pages, {words} words -> {out}")
    print(f"{len(toc)} bookmarks -> {toc_out}")


if __name__ == "__main__":
    main()
