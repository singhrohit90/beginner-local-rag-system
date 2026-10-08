"""Where chunks and their vectors live, behind one interface.

The query pipeline only talks to a ChunkStore, so the numpy store used for experiments and tests
can be swapped for a vector database without touching the pipeline. Ingestion writes with
`upsert`; the query side reads with `search_dense` and `search_keyword`.

Every read takes a Scope. The owner is required and the filter is applied inside the store, so a
caller cannot forget it and one user's chunks never reach another user's results.
Chunk ids must be unique across the whole store; the store refuses a document that reuses one.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

import numpy as np

from rag.common.bm25 import BM25Index
from rag.common.store import VectorIndex
from rag.common.types import Chunk

Scored = List[Tuple[Chunk, float]]


@dataclass(frozen=True)
class Scope:
    """Whose documents a search may look at. doc_ids narrows it to some of the owner's documents."""

    owner: str
    doc_ids: Optional[Tuple[str, ...]] = None


class ChunkStore(Protocol):
    def upsert(
        self,
        doc_id: str,
        owner: str,
        chunks: Sequence[Chunk],
        vectors: np.ndarray,
        embedder_name: str,
        parents: Optional[Dict[str, Chunk]] = None,
        info: Optional[Dict[str, Any]] = None,
    ) -> None: ...

    def search_dense(self, vector: np.ndarray, k: int, scope: Scope) -> Scored: ...

    def search_keyword(self, text: str, k: int, scope: Scope) -> Scored: ...

    def get_parents(self, parent_ids: Sequence[str], scope: Scope) -> Dict[str, Chunk]: ...

    def document_ids(self, scope: Scope) -> List[str]: ...

    def describe(self, scope: Scope) -> Dict[str, Any]: ...

    def has_document(self, doc_id: str) -> bool: ...

    def delete_document(self, doc_id: str) -> None: ...


@dataclass
class _Document:
    owner: str
    chunks: List[Chunk]
    parents: Dict[str, Chunk]
    index: VectorIndex
    info: Dict[str, Any]


class MemoryChunkStore:
    """Exact cosine search and BM25 held in memory. This is what the experiments and tests use,
    and it behaves like the previous per-corpus indexes when a scope covers one document."""

    def __init__(self) -> None:
        self._docs: Dict[str, _Document] = {}
        self._doc_of_chunk: Dict[str, str] = {}  # chunk id -> doc id
        self._bm25: Dict[Tuple[str, ...], Tuple[BM25Index, List[Chunk]]] = {}

    @classmethod
    def from_chunkset(cls, chunkset: Any, vector_index: VectorIndex, doc_id: str = "doc",
                      owner: str = "local") -> "MemoryChunkStore":
        """A store holding one document: a ChunkSet and the VectorIndex built from it."""
        store = cls()
        store.upsert(doc_id, owner, chunkset.chunks, vector_index.vectors, vector_index.embedder_name,
                     chunkset.parents, {"chunker": chunkset.strategy, "chunker_params": chunkset.params})
        return store

    def copy(self) -> "MemoryChunkStore":
        """A store with the same documents; adding to the copy leaves this one untouched."""
        other = MemoryChunkStore()
        other._docs = dict(self._docs)
        other._doc_of_chunk = dict(self._doc_of_chunk)
        return other

    # ---- writes -------------------------------------------------------------------------

    def upsert(self, doc_id, owner, chunks, vectors, embedder_name, parents=None, info=None) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("one vector per chunk")
        self.delete_document(doc_id)  # an upsert replaces the whole document
        for chunk in chunks:
            if chunk.chunk_id in self._doc_of_chunk:
                raise ValueError(f"chunk id {chunk.chunk_id!r} already belongs to another document")
        index = VectorIndex([c.chunk_id for c in chunks], np.asarray(vectors), embedder_name, {})
        self._docs[doc_id] = _Document(owner, list(chunks), dict(parents or {}), index, dict(info or {}))
        for chunk in chunks:
            self._doc_of_chunk[chunk.chunk_id] = doc_id
        self._bm25.clear()

    def delete_document(self, doc_id: str) -> None:
        doc = self._docs.pop(doc_id, None)
        if doc:
            for chunk in doc.chunks:
                self._doc_of_chunk.pop(chunk.chunk_id, None)
        self._bm25.clear()

    # ---- reads --------------------------------------------------------------------------

    def has_document(self, doc_id: str) -> bool:
        return doc_id in self._docs

    def document_ids(self, scope: Scope) -> List[str]:
        return [
            doc_id for doc_id, doc in self._docs.items()
            if doc.owner == scope.owner and (scope.doc_ids is None or doc_id in scope.doc_ids)
        ]

    def describe(self, scope: Scope) -> Dict[str, Any]:
        infos = [self._docs[d].info for d in self.document_ids(scope)]
        if infos and all(i == infos[0] for i in infos):
            return dict(infos[0])
        return {"chunker": "mixed" if infos else None}

    def search_dense(self, vector: np.ndarray, k: int, scope: Scope) -> Scored:
        found: Scored = []
        for doc_id in self.document_ids(scope):
            doc = self._docs[doc_id]
            found += [(doc.chunks[row], score) for row, score in doc.index.search(vector, k)]
        found.sort(key=lambda pair: pair[1], reverse=True)
        return found[:k]

    def search_keyword(self, text: str, k: int, scope: Scope) -> Scored:
        key = tuple(self.document_ids(scope))
        if not key:
            return []
        if key not in self._bm25:
            chunks = [c for doc_id in key for c in self._docs[doc_id].chunks]
            self._bm25[key] = (BM25Index(chunks), chunks)  # one index, so scores are comparable
        index, chunks = self._bm25[key]
        return [(chunks[row], score) for row, score in index.search(text, k)]

    def get_parents(self, parent_ids: Sequence[str], scope: Scope) -> Dict[str, Chunk]:
        wanted = set(parent_ids)
        found: Dict[str, Chunk] = {}
        for doc_id in self.document_ids(scope):
            found.update({pid: p for pid, p in self._docs[doc_id].parents.items() if pid in wanted})
        return found
