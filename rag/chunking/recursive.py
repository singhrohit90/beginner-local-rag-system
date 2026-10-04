from typing import Any, Dict

from rag.chunking.base import ChunkSet, collect
from rag.chunking.document import Document
from rag.chunking.units import atomic_units, pack


class RecursiveChunker:
    """Split on the largest natural boundary that fits: paragraphs first, then sentences, then
    words only as a last resort. Fenced code blocks stay whole while they are at most `code_max`
    words. Pieces are then packed up to `size` words, repeating `overlap` words between chunks."""

    name = "recursive"

    def __init__(self, size: int = 200, overlap: int = 30, code_max: int = 400):
        self.size = size
        self.overlap = overlap
        self.code_max = code_max

    def params(self) -> Dict[str, Any]:
        return {"size": self.size, "overlap": self.overlap, "code_max": self.code_max}

    def chunk(self, doc: Document) -> ChunkSet:
        units = atomic_units(doc, 0, len(doc.text), self.size, self.code_max)
        spans = pack(units, self.size, self.overlap)
        return ChunkSet(self.name, self.params(), collect(doc, self.name, spans))
