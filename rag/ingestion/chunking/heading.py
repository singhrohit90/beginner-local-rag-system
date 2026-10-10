"""Heading-aware chunking: cut the book at its own section boundaries, using the PDF bookmarks.

The bookmarks only give a page, so the exact position of each heading is found by looking for the
heading text as a line on that page. If it is not found the section starts at the top of the page.
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List

from rag.ingestion.chunking.base import ChunkSet, collect
from rag.ingestion.chunking.document import Document
from rag.ingestion.chunking.units import atomic_units, count_words, pack

_PREFIX = re.compile(r"^(?:Chapter|Part)\s+[\dIVX]+\.\s*")


@dataclass
class Section:
    start: int
    end: int
    level: int
    path: List[str]

    @property
    def title(self) -> str:
        return " > ".join(self.path)


def _heading_pattern(title: str) -> "re.Pattern[str]":
    bare = _PREFIX.sub("", title).replace("’", "'")
    words = [re.escape(w).replace("'", "['’]") for w in bare.split()]
    # chapter openers print "CHAPTER 3" before the title on the same line
    return re.compile(
        r"(?mi)^\s*(?:(?:chapter|part)\s+[\dIVX]+\s+)?" + r"\s+".join(words) + r"\s*$"
    )


def sections(doc: Document) -> List[Section]:
    """Sections in reading order, each running from its heading to the next heading."""
    marks = []  # (offset, level, title)
    last_offset, last_page = -1, -1
    for entry in doc.toc:
        if entry["page"] not in doc.page_nos:
            continue
        page_start, page_end = doc.page_text_range(entry["page"])
        search_from = max(page_start, last_offset + 1) if entry["page"] == last_page else page_start
        match = _heading_pattern(entry["title"]).search(doc.text, search_from, page_end)
        if match:
            offset = match.start() + len(match.group()) - len(match.group().lstrip())
        elif entry["page"] == last_page:
            continue  # cannot place a second heading on a page that already has one
        else:
            offset = page_start
        marks.append((offset, entry["level"], entry["title"]))
        last_offset, last_page = offset, entry["page"]

    result: List[Section] = []
    stack: Dict[int, str] = {}
    if not marks or marks[0][0] > 0:
        end = marks[0][0] if marks else len(doc.text)
        result.append(Section(0, end, 1, ["(start of body)"]))
    for index, (offset, level, title) in enumerate(marks):
        for deeper in [lv for lv in stack if lv >= level]:
            del stack[deeper]
        stack[level] = title
        end = marks[index + 1][0] if index + 1 < len(marks) else len(doc.text)
        result.append(Section(offset, end, level, [stack[lv] for lv in sorted(stack)]))
    return [s for s in result if s.end > s.start]


class HeadingChunker:
    """One chunk per section. Sections shorter than `min_words` are merged into the next
    section (never across a chapter or part boundary). Sections longer than `max_words` are split
    with the recursive method, inside the section only. Each chunk records its heading path in
    `section`, which a later step can prepend to the text before embedding."""

    name = "heading"

    def __init__(
        self,
        min_words: int = 60,
        max_words: int = 300,
        overlap: int = 0,
        code_max: int = 400,
    ):
        self.min_words = min_words
        self.max_words = max_words
        self.overlap = overlap
        self.code_max = code_max

    def params(self) -> Dict[str, Any]:
        return {
            "min_words": self.min_words,
            "max_words": self.max_words,
            "overlap": self.overlap,
            "code_max": self.code_max,
        }

    def merged_sections(self, doc: Document) -> List[Section]:
        secs = sections(doc)
        merged: List[Section] = []
        i = 0
        while i < len(secs):
            current = secs[i]
            while (
                count_words(doc.text[current.start : current.end]) < self.min_words
                and i + 1 < len(secs)
                and secs[i + 1].level > 2
            ):
                i += 1
                # A stub heading (often just a title above its first subsection) is absorbed by
                # the section after it, which carries the label because it holds most of the text.
                current = Section(current.start, secs[i].end, secs[i].level, secs[i].path)
            merged.append(current)
            i += 1
        return merged

    def split(self, doc: Document, section: Section, size: int, overlap: int) -> List[tuple]:
        if count_words(doc.text[section.start : section.end]) <= size:
            return [(section.start, section.end)]
        units = atomic_units(doc, section.start, section.end, size, self.code_max)
        return pack(units, size, overlap)

    def chunk(self, doc: Document) -> ChunkSet:
        chunks = []
        for section in self.merged_sections(doc):
            spans = self.split(doc, section, self.max_words, self.overlap)
            chunks.extend(
                collect(
                    doc, self.name, spans, section.title, start_index=len(chunks), level=section.level
                )
            )
        return ChunkSet(self.name, self.params(), chunks)
