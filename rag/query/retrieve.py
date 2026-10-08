"""Query step 1: find candidate chunks. Returns (row, score) pairs, best first."""

from typing import List, Tuple

from rag.common.bm25 import BM25Index
from rag.common.embed import Embedder
from rag.common.store import VectorIndex

Scored = List[Tuple[int, float]]


def dense_search(index: VectorIndex, embedder: Embedder, question: str, k: int) -> Scored:
    """Nearest chunks by embedding similarity."""
    return index.search(embedder.embed_query(question), k)


def keyword_search(index: BM25Index, question: str, k: int) -> Scored:
    """Best chunks by BM25 keyword match."""
    return index.search(question, k)
