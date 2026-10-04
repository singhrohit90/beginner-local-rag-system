from typing import Any, Dict, List

import numpy as np

from rag.chunking.base import ChunkSet, collect
from rag.chunking.document import Document
from rag.chunking.units import Unit, atomic_units, blocks, sentences
from rag.embed import Embedder


class SemanticChunker:
    """Embed every sentence, then start a new chunk where consecutive sentences are unusually
    dissimilar (distance above the `percentile` of all distances in the book).

    Two guards stop it producing silly sizes: a chunk is never cut before it has `min_words`, and
    always cut before it would pass `max_words`. Fenced code blocks count as one sentence.
    Costs one embedding per sentence, so it is the slowest strategy to build.
    """

    name = "semantic"

    def __init__(
        self,
        embedder: Embedder,
        percentile: float = 85.0,
        min_words: int = 80,
        max_words: int = 300,
        code_max: int = 400,
    ):
        self.embedder = embedder
        self.percentile = percentile
        self.min_words = min_words
        self.max_words = max_words
        self.code_max = code_max

    def params(self) -> Dict[str, Any]:
        return {
            "embedder": self.embedder.name,
            "percentile": self.percentile,
            "min_words": self.min_words,
            "max_words": self.max_words,
            "code_max": self.code_max,
        }

    def _units(self, doc: Document) -> List[Unit]:
        units: List[Unit] = []
        for block in blocks(doc):
            units.extend(
                atomic_units(doc, block.start, block.end, self.max_words, self.code_max)
                if block.kind == "code"
                else [s for s in sentences(doc, block)]
            )
        return units

    def chunk(self, doc: Document) -> ChunkSet:
        units = self._units(doc)
        if len(units) < 2:
            spans = [(u.start, u.end) for u in units]
            return ChunkSet(self.name, self.params(), collect(doc, self.name, spans))

        vectors = self.embedder.embed_documents([doc.text[u.start : u.end] for u in units])
        distance = 1.0 - np.sum(vectors[:-1] * vectors[1:], axis=1)  # between unit i and i+1
        threshold = float(np.percentile(distance, self.percentile))

        spans, first, last = [], units[0], units[0]
        words = units[0].words
        for i in range(1, len(units)):
            unit = units[i]
            too_big = words + unit.words > self.max_words
            topic_shift = words >= self.min_words and distance[i - 1] > threshold
            if too_big or topic_shift:
                spans.append((first.start, last.end))
                first, words = unit, 0
            last = unit
            words += unit.words
        spans.append((first.start, last.end))
        return ChunkSet(self.name, self.params(), collect(doc, self.name, spans))
