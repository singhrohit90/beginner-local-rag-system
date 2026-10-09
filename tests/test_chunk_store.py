"""Behaviour every ChunkStore must have. STORES lists the implementations under test; a database
store is added to this list when it exists, so both run the same checks."""

import os

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


OPENSEARCH_URL = os.environ.get("RAG_OPENSEARCH_URL", "http://127.0.0.1:9200")


def opensearch_reachable() -> bool:
    try:
        from opensearchpy import OpenSearch

        OpenSearch(hosts=[OPENSEARCH_URL], timeout=2, max_retries=0).info()
        return True
    except Exception:
        return False


@pytest.fixture(params=["memory", "opensearch"])
def store(request):
    if request.param == "memory":
        yield MemoryChunkStore()
        return
    if not opensearch_reachable():
        pytest.skip(f"OpenSearch is not running at {OPENSEARCH_URL} (docker compose up -d opensearch)")
    from rag.common.opensearch_store import OpenSearchChunkStore, unique_prefix

    database = OpenSearchChunkStore("m", DIM, url=OPENSEARCH_URL, prefix=unique_prefix())
    yield database
    database.drop_indexes()


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
    if not hasattr(store, "copy"):
        pytest.skip("copy() is only part of the in-memory store, used by the injection harness")
    fill(store)
    other = store.copy()
    other.delete_document("d1")
    assert store.has_document("d1") and not other.has_document("d1")


def test_a_failed_upsert_keeps_the_previous_copy(store):
    fill(store)
    with pytest.raises(ValueError, match="already belongs"):
        store.upsert("d1", "alice", [chunk("a9", "new text"), chunk("b1", "steals an id from d2")],
                     np.stack([vec(1), vec(0, 1)]), "m")
    assert store.has_document("d1")
    assert ids(store.search_keyword("compaction", 5, Scope("alice"))) == ["a2"]  # d1 is exactly as before


def test_duplicate_ids_inside_one_document_are_rejected(store):
    with pytest.raises(ValueError, match="unique within"):
        store.upsert("d1", "alice", [chunk("x", "one"), chunk("x", "two")], np.stack([vec(1), vec(0, 1)]), "m")
    assert not store.has_document("d1")


def test_an_empty_document_can_be_searched_without_errors(store):
    store.upsert("e", "alice", [], np.zeros((0, DIM), dtype=np.float32), "m")
    assert store.search_dense(vec(1, 0), 5, Scope("alice")) == []
    assert store.search_keyword("anything", 5, Scope("alice")) == []


def test_searching_while_documents_are_added_and_removed_does_not_fail(store):
    import threading

    fill(store)
    errors = []

    def writer():
        try:
            for i in range(60):
                store.upsert("w", "alice", [chunk(f"w{i}", "replication copies")], np.stack([vec(1, 0)]), "m")
                store.delete_document("w")
        except Exception as err:  # pragma: no cover - only runs when the store is not thread safe
            errors.append(err)

    def reader():
        try:
            for _ in range(120):
                store.search_dense(vec(1, 0), 5, Scope("alice"))
                store.search_keyword("replication", 5, Scope("alice"))
        except Exception as err:  # pragma: no cover
            errors.append(err)

    threads = [threading.Thread(target=writer)] + [threading.Thread(target=reader) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def test_one_owners_data_never_changes_what_another_owner_searches(store):
    fill(store)
    before = [(c.chunk_id, round(s, 6)) for c, s in store.search_keyword("replication", 10, Scope("alice"))]
    assert before
    for i in range(30):  # bob uploads a lot of text full of alice's search term
        store.upsert(f"bulk{i}", "bob", [chunk(f"bulk{i}-0", "replication replication replication replication nodes")],
                     np.stack([vec(1, 0, 0.5)]), "m", info={"chunker": "test"})
    after = [(c.chunk_id, round(s, 6)) for c, s in store.search_keyword("replication", 10, Scope("alice"))]
    assert after == before  # same ranking AND the same scores: no shared statistics leak across owners


def test_describe_lists_the_documents_in_scope(store):
    fill(store)
    assert store.describe(Scope("alice"))["doc_ids"] == ["d1", "d2"]
    assert store.describe(Scope("alice", ("d2",)))["doc_ids"] == ["d2"]
    assert store.describe(Scope("nobody"))["doc_ids"] == []


def test_a_document_id_cannot_be_taken_over_by_another_owner(store):
    fill(store)
    with pytest.raises((ValueError, Exception), match="another owner|already belongs"):
        store.upsert("d1", "bob", [chunk("zz1", "stolen")], np.stack([vec(1)]), "m")
    assert ids(store.search_keyword("compaction", 5, Scope("alice"))) == ["a2"]


def test_a_changed_embedding_model_makes_documents_absent_not_empty(store):
    if not hasattr(store, "_embedder_name"):
        pytest.skip("only a database store keeps data across a change of embedding model")
    from rag.common.opensearch_store import OpenSearchChunkStore

    fill(store)
    other = OpenSearchChunkStore("another-model", DIM, url=OPENSEARCH_URL, prefix=store._prefix)
    try:
        assert not other.has_document("d1")  # so the service indexes it again instead of finding no chunks
        assert other.search_keyword("replication", 5, Scope("alice")) == []
    finally:
        pass  # indexes share the fixture's prefix and are dropped with it


def test_dense_scores_are_the_plain_cosine_similarity(store):
    fill(store)
    results = store.search_dense(vec(1, 0), 10, Scope("alice"))
    scores = {c.chunk_id: s for c, s in results}
    expected = {"a1": 1.0, "a2": 0.0, "b1": float(vec(1, 0.1) @ vec(1, 0))}
    for cid, cosine in expected.items():
        assert scores[cid] == pytest.approx(cosine, abs=1e-5), cid  # not OpenSearch's 1+cos or (1+cos)/2
