"""Building blocks shared by the chunkers: split text into units, then pack units into chunks.

A unit is a span of Document.text that should not be cut: a word, a sentence, a paragraph or a
fenced code block. Chunk size is counted in whitespace-separated words everywhere, so strategies
are compared at the same size.
"""

import re
from dataclasses import dataclass
from typing import List, Tuple

from rag.ingestion.chunking.document import Document

_CODE = re.compile(r"(?m)^```\n.*?\n```$", re.DOTALL)
_PARAGRAPH = re.compile(r"\S.*?(?=\n\s*\n|\Z)", re.DOTALL)
_SENTENCE_END = re.compile(r'(?<=[.!?])["”’)\]]*\s+(?=[A-Z“"(\[])')
_WORD = re.compile(r"\S+")


@dataclass(frozen=True)
class Unit:
    start: int
    end: int
    words: int
    kind: str  # "text", "code", "word", "line"


def count_words(text: str) -> int:
    return len(text.split())


def _span_unit(doc: Document, start: int, end: int, kind: str) -> Unit:
    return Unit(start, end, count_words(doc.text[start:end]), kind)


def words_of(doc: Document) -> List[Unit]:
    return [Unit(m.start(), m.end(), 1, "word") for m in _WORD.finditer(doc.text)]


def blocks(doc: Document, start: int = 0, end: int = -1) -> List[Unit]:
    """Paragraphs and fenced code blocks inside [start, end), in order."""
    end = len(doc.text) if end < 0 else end
    units: List[Unit] = []

    def add_paragraphs(a: int, b: int) -> None:
        for match in _PARAGRAPH.finditer(doc.text, a, b):
            stop = match.start() + len(match.group().rstrip())
            units.append(_span_unit(doc, match.start(), stop, "text"))

    position = start
    for fence in _CODE.finditer(doc.text, start, end):
        add_paragraphs(position, fence.start())
        units.append(_span_unit(doc, fence.start(), fence.end(), "code"))
        position = fence.end()
    add_paragraphs(position, end)
    return units


def sentences(doc: Document, unit: Unit) -> List[Unit]:
    """Split a text unit into sentences. Code units come back whole."""
    if unit.kind != "text":
        return [unit]
    cuts = [unit.start]
    for match in _SENTENCE_END.finditer(doc.text, unit.start, unit.end):
        cuts.append(match.end())
    cuts.append(unit.end)
    parts = []
    for a, b in zip(cuts, cuts[1:]):
        stop = a + len(doc.text[a:b].rstrip())
        if stop > a:
            parts.append(_span_unit(doc, a, stop, "text"))
    return parts


def _split_words(doc: Document, unit: Unit, size: int) -> List[Unit]:
    spans = [(m.start(), m.end()) for m in _WORD.finditer(doc.text, unit.start, unit.end)]
    pieces = []
    for i in range(0, len(spans), size):
        group = spans[i : i + size]
        pieces.append(Unit(group[0][0], group[-1][1], len(group), "text"))
    return pieces


def _split_lines(doc: Document, unit: Unit) -> List[Unit]:
    lines, position = [], unit.start
    for line in doc.text[unit.start : unit.end].split("\n"):
        end = position + len(line)
        if line.strip():
            lines.append(Unit(position, end, count_words(line), "line"))
        position = end + 1
    return lines


def atomic_units(doc: Document, start: int, end: int, size: int, code_max: int) -> List[Unit]:
    """Blocks cut down so that no text unit exceeds `size` words and no code block exceeds
    `code_max`. Code is kept whole whenever it fits, which keeps listings readable."""
    result: List[Unit] = []
    for block in blocks(doc, start, end):
        if block.kind == "code":
            result.extend([block] if block.words <= code_max else _split_lines(doc, block))
        elif block.words <= size:
            result.append(block)
        else:
            for sentence in sentences(doc, block):
                if sentence.words <= size:
                    result.append(sentence)
                else:
                    result.extend(_split_words(doc, sentence, size))
    return result


def pack(units: List[Unit], size: int, overlap: int) -> List[Tuple[int, int]]:
    """Group consecutive units into spans of at most `size` words, repeating up to `overlap`
    words of the previous span at the start of the next. A single unit larger than `size` is
    emitted alone rather than cut."""
    spans: List[Tuple[int, int]] = []
    i, n = 0, len(units)
    while i < n:
        j, total = i, 0
        while j < n and (j == i or total + units[j].words <= size):
            total += units[j].words
            j += 1
        spans.append((units[i].start, units[j - 1].end))
        if j >= n:
            break
        k, carried = j, 0
        while k > i + 1 and carried + units[k - 1].words <= overlap:
            carried += units[k - 1].words
            k -= 1
        i = k if k > i else j
    return spans
