"""A ChunkStore backed by OpenSearch: chunks, vectors and keyword search in one database.

Indexes (the prefix lets tests use their own, and lets several projects share a server):
    <prefix>_d_<embedder>_<dim>             one row per document: owner, chunker info, chunk count
    <prefix>_c_<embedder>_<dim>_<owner>     the searchable chunks of ONE owner: text and vector
    <prefix>_p_<embedder>_<dim>_<owner>     that owner's parent chunks, fetched by id, never searched

Each owner has indexes of their own. That is what keeps owners apart, not only the filter on each
query: Lucene's keyword scoring (idf, average length) is computed over every row in an index, so in
a shared index one user's uploads would change the ranking another user sees. Parent chunks sit in
their own index for the same reason: they are not searchable and must not move the statistics.
Inside one owner's index, a filter on document ids narrows a search to some of that owner's documents.

The documents index is per embedder, so after the embedding model changes a document is reported as
absent and gets indexed again, instead of being found with no chunks behind it.

Dense search is exact by default (scores every vector in scope, same ranking as the in-memory
store) or approximate (HNSW). The score returned is the plain cosine similarity, recovered from
OpenSearch's score (exact: 1 + cosine; approximate Lucene: (1 + cosine) / 2, both measured), so no
vector has to be fetched back.
"""

import hashlib
import re
import uuid
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from rag.common.chunk_store import Scope, Scored
from rag.common.types import Chunk


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
        self._prefix = prefix
        self._slug = f"{re.sub(r'[^a-z0-9]+', '-', embedder_name.lower()).strip('-')}_{dim}"
        self._documents = f"{prefix}_d_{self._slug}"
        self._ensure_documents_index()

    def ping(self) -> str:
        """The cluster's health colour ("green", "yellow", "red"); raises if the server does not answer."""
        return self._client.cluster.health(params={"request_timeout": 2})["status"]

    # ---- index names and setup ----------------------------------------------------------

    def _owner_key(self, owner: str) -> str:
        return hashlib.sha1(owner.encode("utf-8")).hexdigest()[:16]  # index names cannot hold arbitrary text

    def _chunks_index(self, owner: str) -> str:
        return f"{self._prefix}_c_{self._slug}_{self._owner_key(owner)}"

    def _parents_index(self, owner: str) -> str:
        return f"{self._prefix}_p_{self._slug}_{self._owner_key(owner)}"

    def _ensure_documents_index(self) -> None:
        if not self._client.indices.exists(index=self._documents):
            self._client.indices.create(index=self._documents, body={
                "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
                "mappings": {"properties": {
                    "doc_id": {"type": "keyword"}, "owner": {"type": "keyword"},
                    "embedder": {"type": "keyword"}, "chunks": {"type": "integer"},
                    "info": {"type": "object", "enabled": False},
                }},
            })

    def _ensure_owner_indexes(self, owner: str) -> None:
        shared = {"chunk_id": {"type": "keyword"}, "doc_id": {"type": "keyword"}, "owner": {"type": "keyword"},
                  "page_start": {"type": "integer"}, "page_end": {"type": "integer"},
                  "section": {"type": "keyword", "ignore_above": 512}, "strategy": {"type": "keyword"},
                  "meta": {"type": "object", "enabled": False}}  # meta is kept in _source, not indexed
        chunks, parents = self._chunks_index(owner), self._parents_index(owner)
        if not self._client.indices.exists(index=chunks):
            self._client.indices.create(index=chunks, body={
                "settings": {"index": {"knn": True, "number_of_shards": 1, "number_of_replicas": 0}},
                "mappings": {"properties": {**shared, "text": {"type": "text", "analyzer": "english"},
                    "embedding": {"type": "knn_vector", "dimension": self._dim, "method": {
                        "name": "hnsw", "engine": "lucene", "space_type": "cosinesimil"}}}},
            })
        if not self._client.indices.exists(index=parents):
            self._client.indices.create(index=parents, body={
                "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
                "mappings": {"properties": {**shared, "text": {"type": "text", "index": False}}},
            })

    def drop_indexes(self) -> None:
        """Remove every index this store created. For tests and a full reset."""
        try:
            names = list(self._client.indices.get(index=f"{self._prefix}_*").keys())
        except Exception:  # nothing matches
            return
        for name in names:
            self._client.indices.delete(index=name, ignore_unavailable=True)

    # ---- query building -----------------------------------------------------------------

    @staticmethod
    def _filters(scope: Scope) -> List[Dict[str, Any]]:
        filters: List[Dict[str, Any]] = [{"term": {"owner": scope.owner}}]  # redundant with the index, kept as a second guard
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

    def _search(self, index: str, body: Dict[str, Any]) -> List[Dict[str, Any]]:
        """A search that treats an owner with no index yet as having no results."""
        from opensearchpy.exceptions import NotFoundError

        try:
            return self._client.search(index=index, body=body)["hits"]["hits"]
        except NotFoundError:
            return []

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

        previous = self._client.get(index=self._documents, id=doc_id, ignore=[404])
        if previous.get("found") and previous["_source"]["owner"] != owner:
            raise ValueError(f"document {doc_id!r} belongs to another owner")
        self._ensure_owner_indexes(owner)
        chunk_index, parent_index = self._chunks_index(owner), self._parents_index(owner)

        # Validate before writing anything, so a refused upsert leaves the previous copy intact.
        # Ids only have to be unique among this owner's documents: other owners have indexes of their own.
        if ids:
            clash = self._client.search(index=f"{chunk_index},{parent_index}", body={
                "size": 1, "_source": ["chunk_id"],
                "query": {"bool": {"filter": [{"terms": {"chunk_id": ids}}],
                                   "must_not": [{"term": {"doc_id": doc_id}}]}},
            })["hits"]["hits"]
            if clash:
                raise ValueError(f"chunk id {clash[0]['_source']['chunk_id']!r} already belongs to another document")

        operations: List[Dict[str, Any]] = []
        for chunk, vector in zip(chunks, vectors):
            operations += [{"index": {"_index": chunk_index, "_id": chunk.chunk_id}},
                           self._row(doc_id, owner, chunk, vector.tolist())]
        for chunk in parents.values():
            operations += [{"index": {"_index": parent_index, "_id": chunk.chunk_id}},
                           self._row(doc_id, owner, chunk, None)]
        if operations:
            result = self._client.bulk(body=operations, refresh=True)
            if result.get("errors"):
                failed = next(item for item in result["items"] if "error" in item["index"])
                raise RuntimeError(f"OpenSearch refused a chunk: {failed['index']['error']}")
        # Rows from an earlier version of this document that are not in the new one.
        for index in (chunk_index, parent_index):
            self._client.delete_by_query(index=index, refresh=True, body={"query": {"bool": {
                "filter": [{"term": {"doc_id": doc_id}}],
                "must_not": [{"terms": {"chunk_id": ids}}] if ids else [],
            }}})
        self._client.index(index=self._documents, id=doc_id, refresh=True, body={
            "doc_id": doc_id, "owner": owner, "embedder": embedder_name,
            "chunks": len(chunks), "info": dict(info or {}),
        })

    @staticmethod
    def _row(doc_id: str, owner: str, chunk: Chunk, vector: Optional[List[float]]) -> Dict[str, Any]:
        row: Dict[str, Any] = {
            "chunk_id": chunk.chunk_id, "doc_id": doc_id, "owner": owner,
            "text": chunk.text, "page_start": chunk.page_start, "page_end": chunk.page_end,
            "section": chunk.section, "strategy": chunk.strategy, "meta": chunk.meta,
        }
        if vector is not None:
            row["embedding"] = vector
        return row

    def delete_document(self, doc_id: str) -> None:
        record = self._client.get(index=self._documents, id=doc_id, ignore=[404])
        if not record.get("found"):
            return
        owner = record["_source"]["owner"]
        for index in (self._chunks_index(owner), self._parents_index(owner)):
            self._client.delete_by_query(index=index, refresh=True, ignore_unavailable=True,
                                         body={"query": {"term": {"doc_id": doc_id}}})
        self._client.delete(index=self._documents, id=doc_id, refresh=True, ignore=[404])

    # ---- reads --------------------------------------------------------------------------

    def has_document(self, doc_id: str) -> bool:
        return bool(self._client.exists(index=self._documents, id=doc_id))

    def _documents_in(self, scope: Scope) -> List[Dict[str, Any]]:
        hits = self._search(self._documents, {"size": 10000, "query": {"bool": {"filter": self._filters(scope)}}})
        return [h["_source"] for h in hits]

    def document_ids(self, scope: Scope) -> List[str]:
        return sorted(d["doc_id"] for d in self._documents_in(scope))

    def describe(self, scope: Scope) -> Dict[str, Any]:
        documents = self._documents_in(scope)  # one query answers both what the chunker was and which documents
        infos = [d.get("info") or {} for d in documents]
        described = dict(infos[0]) if infos and all(i == infos[0] for i in infos) else {"chunker": "mixed" if infos else None}
        described["doc_ids"] = sorted(d["doc_id"] for d in documents)
        return described

    def search_dense(self, vector: np.ndarray, k: int, scope: Scope) -> Scored:
        vector = np.asarray(vector, dtype=np.float32)
        filters = self._filters(scope)
        if self._exact:
            query: Dict[str, Any] = {"script_score": {
                "query": {"bool": {"filter": filters}},
                "script": {"source": "knn_score", "lang": "knn", "params": {
                    "field": "embedding", "query_value": vector.tolist(), "space_type": "cosinesimil"}},
            }}
        else:
            query = {"knn": {"embedding": {"vector": vector.tolist(), "k": k, "filter": {"bool": {"filter": filters}}}}}
        hits = self._search(self._chunks_index(scope.owner), {
            "size": k, "query": query, "_source": {"excludes": ["embedding"]},
        })
        found: Scored = []
        for hit in hits:
            score = float(hit["_score"])
            cosine = score - 1.0 if self._exact else 2.0 * score - 1.0  # undo OpenSearch's score transform
            found.append((self._to_chunk(hit["_source"]), max(-1.0, min(1.0, cosine))))
        return found

    def search_keyword(self, text: str, k: int, scope: Scope) -> Scored:
        if not text.strip():
            return []
        hits = self._search(self._chunks_index(scope.owner), {
            "size": k, "_source": {"excludes": ["embedding"]},
            "query": {"bool": {"must": [{"match": {"text": {"query": text}}}], "filter": self._filters(scope)}},
        })
        return [(self._to_chunk(h["_source"]), float(h["_score"])) for h in hits if h["_score"] > 0]

    def get_parents(self, parent_ids: Sequence[str], scope: Scope) -> Dict[str, Chunk]:
        if not parent_ids:
            return {}
        wanted = list(set(parent_ids))
        hits = self._search(self._parents_index(scope.owner), {
            "size": len(wanted),
            "query": {"bool": {"filter": self._filters(scope) + [{"terms": {"chunk_id": wanted}}]}},
        })
        return {h["_source"]["chunk_id"]: self._to_chunk(h["_source"]) for h in hits}


def unique_prefix() -> str:
    """A throwaway index prefix, for tests."""
    return f"ragtest_{uuid.uuid4().hex[:8]}"
