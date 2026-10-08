"""Behaviour every ChunkStore must have. STORES lists the implementations under test; a database
store is added to this list when it exists, so both run the same checks."""

import numpy as np
import pytest

from rag.common.chunk_store import MemoryChunkStore, Scope
from rag.common.types import Chunk

DIM = 8


def vec(*values):
    v = np.zeros(DIM, dtype=np.float32)
    v[: len(values)] = values
    return v / np.linalg.norm(v)


def chunk(cid, text, **meta):
    return Chunk(cid, text, 1, 1, "test", meta=meta)


@pytest.fixture(params=["memory"])
def store(request):
    return MemoryChunkStore()


def fill(store):
    store.upsert("d1", "alice", [chunk("a1", "replication copies data between nodes"),
                                 chunk("a2", "compaction merges log segments")],
                 np.stack([vec(1, 0), vec(0, 1)]), "m", info={"chunker": "test"})
    store.upsert("d2", "alice", [chunk("b1", "replication lag and followers")],
                 np.stack([vec(1, 0.1)]), "m", info={"chunker": "test"})
    store.upsert("d3", "bob", [chunk("c1", "replication secrets of bob")],
                 np.stack([vec(1, 0.05)]), "m", info={"chunker": "test"})


def ids(results):
    return [c.chunk_id for c, _ in results]


def test_a_search_never_returns_another_owners_chunks(store):
    fill(store)
    alice = Scope("alice")
    assert "c1" not in ids(store.search_dense(vec(1, 0), 10, alice))
    assert "c1" not in ids(store.search_keyword("replication", 10, alice))
    assert ids(store.search_keyword("replication secrets", 10, Scope("bob"))) == ["c1"]
    assert store.search_dense(vec(1, 0), 10, Scope("nobody")) == []
    assert store.search_keyword("replication", 10, Scope("nobody")) == []


def test_scope_can_narrow_to_some_documents(store):
    fill(store)
    only_d2 = Scope("alice", ("d2",))
    assert ids(store.search_dense(vec(1, 0), 10, only_d2)) == ["b1"]
    assert ids(store.search_keyword("replication", 10, only_d2)) == ["b1"]
    assert store.document_ids(Scope("alice")) == ["d1", "d2"]
    assert store.document_ids(Scope("alice", ("d3",))) == []  # bob's document is not reachable by naming it


def test_dense_results_are_best_first_and_merged_across_documents(store):
    fill(store)
    results = store.search_dense(vec(1, 0), 3, Scope("alice"))
    scores = [s for _, s in results]
    assert scores == sorted(scores, reverse=True) and ids(results)[0] == "a1" and len(results) == 3


def test_keyword_search_ranks_by_bm25_and_drops_zero_scores(store):
    fill(store)
    assert ids(store.search_keyword("compaction segments", 5, Scope("alice"))) == ["a2"]
    assert store.search_keyword("zzzz", 5, Scope("alice")) == []


def test_upsert_replaces_a_document_and_chunk_ids_are_unique_across_documents(store):
    fill(store)
    store.upsert("d1", "alice", [chunk("a9", "brand new text about sharding")], np.stack([vec(0, 0, 1)]), "m")
    assert ids(store.search_keyword("sharding", 5, Scope("alice"))) == ["a9"]
    assert store.search_keyword("compaction", 5, Scope("alice")) == []  # the old version is gone
    with pytest.raises(ValueError, match="already belongs"):
        store.upsert("d4", "alice", [chunk("b1", "reused id")], np.stack([vec(1)]), "m")


def test_delete_removes_a_document_and_frees_its_chunk_ids(store):
    fill(store)
    assert store.has_document("d2")
    store.delete_document("d2")
    assert not store.has_document("d2") and "b1" not in ids(store.search_dense(vec(1, 0), 10, Scope("alice")))
    store.upsert("d5", "alice", [chunk("b1", "id reused after delete")], np.stack([vec(1)]), "m")
    store.delete_document("never-existed")  # deleting nothing is not an error


def test_parents_are_returned_only_inside_the_scope(store):
    parent = chunk("p1", "the larger parent passage")
    store.upsert("d1", "alice", [chunk("a1", "child text", parent_id="p1")], np.stack([vec(1)]), "m", parents={"p1": parent})
    assert store.get_parents(["p1"], Scope("alice")) == {"p1": parent}
    assert store.get_parents(["p1"], Scope("bob")) == {}


def test_describe_reports_the_chunker_or_mixed(store):
    fill(store)
    assert store.describe(Scope("alice"))["chunker"] == "test"
    store.upsert("d6", "alice", [chunk("z1", "x")], np.stack([vec(1)]), "m", info={"chunker": "other"})
    assert store.describe(Scope("alice"))["chunker"] == "mixed"


def test_vector_and_chunk_counts_must_match(store):
    with pytest.raises(ValueError, match="one vector per chunk"):
        store.upsert("d1", "alice", [chunk("a1", "x")], np.stack([vec(1), vec(0, 1)]), "m")


def test_copy_is_independent(store):
    fill(store)
    other = store.copy()
    other.delete_document("d1")
    assert store.has_document("d1") and not other.has_document("d1")
