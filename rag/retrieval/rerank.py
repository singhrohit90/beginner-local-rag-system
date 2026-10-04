"""Rerankers re-score a short candidate list by reading the query and each passage together.

A bi-encoder (the embedding model) encodes query and passage separately, so it can search millions
of passages but misses fine detail. A cross-encoder reads both at once, which is far more accurate
and far too slow to run over the whole book, so it only sees the fused top candidates.
"""

from typing import List, Protocol


class Reranker(Protocol):
    name: str

    def score(self, query: str, texts: List[str]) -> List[float]: ...


class CrossEncoderReranker:
    def __init__(
        self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2", batch_size: int = 32
    ):
        from sentence_transformers import CrossEncoder  # heavy import, kept lazy

        self.name = model_name
        self._model = CrossEncoder(model_name)
        self._batch_size = batch_size

    def score(self, query: str, texts: List[str]) -> List[float]:
        pairs = [(query, text) for text in texts]
        return [float(s) for s in self._model.predict(pairs, batch_size=self._batch_size)]


class KeywordOverlapReranker:
    """Counts query words found in each passage. For tests only."""

    name = "keyword-overlap"

    def score(self, query: str, texts: List[str]) -> List[float]:
        words = set(query.lower().split())
        return [float(len(words & set(t.lower().split()))) for t in texts]
