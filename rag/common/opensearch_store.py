"""A ChunkStore backed by OpenSearch: chunks, vectors and keyword search in one database.

Indexes (the prefix lets tests use their own, and lets several projects share a server):
    <prefix>_chunks_<embedder>_<dim>   one row per chunk (and per parent chunk) with the text, the
                                       vector, and the owner and document id used for filtering
    <prefix>_documents                 one row per document: owner, chunker info, chunk count

Every search filters on owner (and document ids) inside the query, never afterwards, so one
owner's rows cannot appear in another owner's results or even change their ranking.

Dense search can be exact (default: scores every vector in scope, identical ranking to the
in-memory store) or approximate (HNSW, faster on large corpora). The score returned is always the
plain cosine similarity, computed here from the stored vector, so it matches the in-memory store;
OpenSearch's own score is only used for the order.
"""

import re
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from rag.common.chunk_store import Scope, Scored
from rag.common.types import Chunk

CHUNK = "chunk"
PARENT = "parent"


class OpenSearchChunkStore:
    def __init__(
        self,
        embedder_name: str,
        dim: int,
        url: str = "http://127.0.0.1:9200",
        prefix: str = "rag",
        exact: bool = True,
        client: Any = None,
    ):
        if client is None:
            from opensearchpy import OpenSearch

            client = OpenSearch(hosts=[url], http_compress=True, timeout=30, max_retries=3, retry_on_timeout=True)
        self._client = client
        self._embedder_name = embedder_name
        self._dim = dim
        self._exact = exact
        slug = re.sub(r"[^a-z0-9]+", "-", embedder_name.lower()).strip("-")
        self._chunks = f"{prefix}_chunks_{slug}_{dim}"
        self._documents = f"{prefix}_documents"
        self._ensure_indexes()

    # ---- setup --------------------------------------------------------------------------

    def _ensure_indexes(self) -> None:
        if not self._client.indices.exists(index=self._chunks):
            self._client.indices.create(index=self._chunks, body={
                "settings": {"index": {"knn": True, "number_of_shards": 1, "number_of_replicas": 0}},
                "mappings": {"properties": {
                    "chunk_id": {"type": "keyword"},
                    "doc_id": {"type": "keyword"},
                    "owner": {"type": "keyword"},
                    "kind": {"type": "keyword"},  # "chunk" is searchable, "parent" is only fetched
                    "text": {"type": "text", "analyzer": "english"},
                    "embedding": {"type": "knn_vector", "dimension": self._dim, "method": {
                        "name": "hnsw", "engine": "lucene", "space_type": "cosinesimil"}},
                    "page_start": {"type": "integer"},
                    "page_end": {"type": "integer"},
                    "section": {"type": "keyword", "ignore_above": 512},
                    "strategy": {"type": "keyword"},
                    "meta": {"type": "object", "enabled": False},  # kept in _source, not indexed
                }},
            })
        if not self._client.indices.exists(index=self._documents):
            self._client.indices.create(index=self._documents, body={
                "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
                "mappings": {"properties": {
                    "doc_id": {"type": "keyword"}, "owner": {"type": "keyword"},
                    "embedder": {"type": "keyword"}, "chunks": {"type": "integer"},
                    "info": {"type": "object", "enabled": False},
                }},
            })

    def drop_indexes(self) -> None:
        """Remove this store's indexes. For tests and a full reset."""
        for index in (self._chunks, self._documents):
            self._client.indices.delete(index=index, ignore_unavailable=True)

    # ---- query building -----------------------------------------------------------------

    @staticmethod
    def _scope_filter(scope: Scope, kind: Optional[str] = CHUNK) -> List[Dict[str, Any]]:
        filters: List[Dict[str, Any]] = [{"term": {"owner": scope.owner}}]
        if kind:
            filters.append({"term": {"kind": kind}})
        if scope.doc_ids is not None:
            filters.append({"terms": {"doc_id": list(scope.doc_ids)}})
        return filters

    @staticmethod
    def _to_chunk(source: Dict[str, Any]) -> Chunk:
        return Chunk(
            chunk_id=source["chunk_id"], text=source["text"], page_start=source["page_start"],
            page_end=source["page_end"], strategy=source.get("strategy", ""),
            section=source.get("section"), meta=dict(source.get("meta") or {}),
        )

    # ---- writes -------------------------------------------------------------------------

    def upsert(
        self,
        doc_id: str,
        owner: str,
        chunks: Sequence[Chunk],
        vectors: np.ndarray,
        embedder_name: str,
        parents: Optional[Dict[str, Chunk]] = None,
        info: Optional[Dict[str, Any]] = None,
    ) -> None:
        if embedder_name != self._embedder_name:
            raise ValueError(f"this store holds {self._embedder_name!r} vectors, not {embedder_name!r}")
        if len(chunks) != len(vectors):
            raise ValueError("one vector per chunk")
        parents = dict(parents or {})
        ids = [c.chunk_id for c in chunks] + list(parents)
        if len(set(ids)) != len(ids):
            raise ValueError("chunk ids must be unique within a document")
        vectors = np.asarray(vectors, dtype=np.float32).reshape(len(chunks), self._dim)

        # Validate before writing anything, so a refused upsert leaves the previous copy intact.
        if ids:
            clash = self._client.search(index=self._chunks, body={
                "size": 1, "_source": ["chunk_id"],
                "query": {"bool": {"filter": [{"terms": {"chunk_id": ids}}],
                                   "must_not": [{"term": {"doc_id": doc_id}}]}},
            })["hits"]["hits"]
            if clash:
                raise ValueError(f"chunk id {clash[0]['_source']['chunk_id']!r} already belongs to another document")

        operations: List[Dict[str, Any]] = []
        for chunk, vector in zip(chunks, vectors):
            operations += [{"index": {"_index": self._chunks, "_id": chunk.chunk_id}},
                           self._row(doc_id, owner, chunk, CHUNK, vector.tolist())]
        for chunk in parents.values():
            operations += [{"index": {"_index": self._chunks, "_id": chunk.chunk_id}},
                           self._row(doc_id, owner, chunk, PARENT, None)]
        if operations:
            result = self._client.bulk(body=operations, refresh=True)
            if result.get("errors"):
                failed = next(item for item in result["items"] if "error" in item["index"])
                raise RuntimeError(f"OpenSearch refused a chunk: {failed['index']['error']}")
        # Rows from an earlier version of this document that are not in the new one.
        self._client.delete_by_query(index=self._chunks, refresh=True, body={"query": {"bool": {
            "filter": [{"term": {"doc_id": doc_id}}],
            "must_not": [{"terms": {"chunk_id": ids}}] if ids else [],
        }}})
        self._client.index(index=self._documents, id=doc_id, refresh=True, body={
            "doc_id": doc_id, "owner": owner, "embedder": embedder_name,
            "chunks": len(chunks), "info": dict(info or {}),
        })

    @staticmethod
    def _row(doc_id: str, owner: str, chunk: Chunk, kind: str, vector: Optional[List[float]]) -> Dict[str, Any]:
        row: Dict[str, Any] = {
            "chunk_id": chunk.chunk_id, "doc_id": doc_id, "owner": owner, "kind": kind,
            "text": chunk.text, "page_start": chunk.page_start, "page_end": chunk.page_end,
            "section": chunk.section, "strategy": chunk.strategy, "meta": chunk.meta,
        }
        if vector is not None:
            row["embedding"] = vector
        return row

    def delete_document(self, doc_id: str) -> None:
        self._client.delete_by_query(index=self._chunks, refresh=True, body={"query": {"term": {"doc_id": doc_id}}})
        self._client.delete(index=self._documents, id=doc_id, refresh=True, ignore=[404])

    # ---- reads --------------------------------------------------------------------------

    def has_document(self, doc_id: str) -> bool:
        return bool(self._client.exists(index=self._documents, id=doc_id))

    def _documents_in(self, scope: Scope) -> List[Dict[str, Any]]:
        response = self._client.search(index=self._documents, body={
            "size": 10000, "query": {"bool": {"filter": self._scope_filter(scope, kind=None)}},
        })
        return [h["_source"] for h in response["hits"]["hits"]]

    def document_ids(self, scope: Scope) -> List[str]:
        return sorted(d["doc_id"] for d in self._documents_in(scope))

    def describe(self, scope: Scope) -> Dict[str, Any]:
        infos = [d.get("info") or {} for d in self._documents_in(scope)]
        if infos and all(i == infos[0] for i in infos):
            return dict(infos[0])
        return {"chunker": "mixed" if infos else None}

    def search_dense(self, vector: np.ndarray, k: int, scope: Scope) -> Scored:
        vector = np.asarray(vector, dtype=np.float32)
        filters = self._scope_filter(scope)
        if self._exact:
            query: Dict[str, Any] = {"script_score": {
                "query": {"bool": {"filter": filters}},
                "script": {"source": "knn_score", "lang": "knn", "params": {
                    "field": "embedding", "query_value": vector.tolist(), "space_type": "cosinesimil"}},
            }}
        else:
            query = {"knn": {"embedding": {"vector": vector.tolist(), "k": k, "filter": {"bool": {"filter": filters}}}}}
        hits = self._client.search(index=self._chunks, body={
            "size": k, "query": query, "_source": {"excludes": []},
        })["hits"]["hits"]
        found: Scored = []
        for hit in hits:
            source = hit["_source"]
            cosine = float(np.dot(np.asarray(source["embedding"], dtype=np.float32), vector))
            found.append((self._to_chunk(source), cosine))
        found.sort(key=lambda pair: pair[1], reverse=True)  # raw cosine, as the in-memory store reports
        return found

    def search_keyword(self, text: str, k: int, scope: Scope) -> Scored:
        if not text.strip():
            return []
        hits = self._client.search(index=self._chunks, body={
            "size": k, "_source": {"excludes": ["embedding"]},
            "query": {"bool": {"must": [{"match": {"text": {"query": text}}}], "filter": self._scope_filter(scope)}},
        })["hits"]["hits"]
        return [(self._to_chunk(h["_source"]), float(h["_score"])) for h in hits if h["_score"] > 0]

    def get_parents(self, parent_ids: Sequence[str], scope: Scope) -> Dict[str, Chunk]:
        if not parent_ids:
            return {}
        hits = self._client.search(index=self._chunks, body={
            "size": len(set(parent_ids)), "_source": {"excludes": ["embedding"]},
            "query": {"bool": {"filter": self._scope_filter(scope, kind=PARENT) + [{"terms": {"chunk_id": list(set(parent_ids))}}]}},
        })["hits"]["hits"]
        return {h["_source"]["chunk_id"]: self._to_chunk(h["_source"]) for h in hits}


def unique_prefix() -> str:
    """A throwaway index prefix, for tests."""
    return f"ragtest_{uuid.uuid4().hex[:8]}"
