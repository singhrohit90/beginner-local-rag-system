"""The body of the book as one string, with a map from character offsets back to PDF pages.

Every chunker works on offsets into Document.text, so each chunk's page range comes from the same
place and can be compared fairly with the gold page ranges.
"""

import json
import re
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from rag.ingestion.extract import load_pages
from rag.common.types import Chunk, Page


def body_range(toc: List[Dict[str, Any]]) -> tuple:
    """First and last PDF page of the body: from 'Part I' to just before the glossary or index.

    The index and glossary repeat many technical terms next to page numbers, so a keyword search
    would rank them highly without them containing an answer.
    """
    first = next((e["page"] for e in toc if re.match(r"Part I\.", e["title"])), None)
    last = next((e["page"] - 1 for e in toc if e["title"] in ("Glossary", "Index")), None)
    return first, last


@dataclass
class Document:
    pages: List[Page]
    toc: List[Dict[str, Any]]
    text: str
    page_nos: List[int]
    starts: List[int]

    @classmethod
    def from_pages(
        cls,
        pages: List[Page],
        toc: Optional[List[Dict[str, Any]]] = None,
        first: Optional[int] = None,
        last: Optional[int] = None,
    ) -> "Document":
        toc = toc or []
        body = [
            p
            for p in pages
            if p.text.strip()
            and (first is None or p.page_no >= first)
            and (last is None or p.page_no <= last)
        ]
        starts, position = [], 0
        for page in body:
            starts.append(position)
            position += len(page.text) + 2  # the two newlines that join pages
        return cls(
            pages=body,
            toc=[e for e in toc if first is None or first <= e["page"] <= (last or 10**9)],
            text="\n\n".join(p.text for p in body),
            page_nos=[p.page_no for p in body],
            starts=starts,
        )

    @classmethod
    def from_files(cls, pages_path: Path, toc_path: Optional[Path] = None) -> "Document":
        pages = load_pages(pages_path)
        toc = json.loads(toc_path.read_text(encoding="utf-8")) if toc_path else []
        first, last = body_range(toc)
        return cls.from_pages(pages, toc, first, last)

    def page_of(self, offset: int) -> int:
        index = bisect_right(self.starts, offset) - 1
        return self.page_nos[max(index, 0)]

    def page_span(self, start: int, end: int) -> tuple:
        return self.page_of(start), self.page_of(max(end - 1, start))

    def page_text_range(self, page_no: int) -> tuple:
        """Character offsets of one page inside text."""
        index = self.page_nos.index(page_no)
        end = self.starts[index + 1] - 2 if index + 1 < len(self.starts) else len(self.text)
        return self.starts[index], end

    def make_chunk(
        self,
        strategy: str,
        index: int,
        start: int,
        end: int,
        section: Optional[str] = None,
        **meta: Any,
    ) -> Optional[Chunk]:
        """Build a chunk from a character span, trimming whitespace. None if it is empty."""
        while start < end and self.text[start].isspace():
            start += 1
        while end > start and self.text[end - 1].isspace():
            end -= 1
        if start >= end:
            return None
        page_start, page_end = self.page_span(start, end)
        return Chunk(
            chunk_id=f"{strategy}-{index:05d}",
            text=self.text[start:end],
            page_start=page_start,
            page_end=page_end,
            strategy=strategy,
            section=section,
            meta={"span": [start, end], **meta},
        )
