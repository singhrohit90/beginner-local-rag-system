from typing import Any, Dict

from rag.ingestion.chunking.base import ChunkSet, collect
from rag.ingestion.chunking.document import Document
from rag.ingestion.chunking.units import pack, words_of


class FixedChunker:
    """Baseline: a sliding window over words. It ignores sentences, paragraphs, code and
    headings, so it will cut through all of them. That is the point of having it."""

    name = "fixed"

    def __init__(self, size: int = 200, overlap: int = 40):
        self.size = size
        self.overlap = overlap

    def params(self) -> Dict[str, Any]:
        return {"size": self.size, "overlap": self.overlap}

    def chunk(self, doc: Document) -> ChunkSet:
        spans = pack(words_of(doc), self.size, self.overlap)
        return ChunkSet(self.name, self.params(), collect(doc, self.name, spans))
