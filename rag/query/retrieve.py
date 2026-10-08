"""Query step 1: find candidate chunks in the store. Returns (chunk, score) pairs, best first,
only from documents inside the scope."""

import numpy as np

from rag.common.chunk_store import ChunkStore, Scope, Scored


def dense_search(store: ChunkStore, vector: np.ndarray, k: int, scope: Scope) -> Scored:
    """Nearest chunks by embedding similarity. The caller embeds the question."""
    return store.search_dense(vector, k, scope)


def keyword_search(store: ChunkStore, question: str, k: int, scope: Scope) -> Scored:
    """Best chunks by BM25 keyword match."""
    return store.search_keyword(question, k, scope)
