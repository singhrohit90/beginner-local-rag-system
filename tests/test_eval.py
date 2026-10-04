import json

import pytest

from rag.eval.diagnose import locate_failure, stage_ranks
from rag.eval.golden import GoldQuestion, load_golden
from rag.eval.metrics import (
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
    score_hits,
)
from rag.eval.run_eval import run_eval
from rag.trace import Trace, load_trace
from rag.types import Hit


def hit(cid, rank, start, end=None):
    return Hit(chunk_id=cid, rank=rank, score=1.0 / rank, page_start=start, page_end=end or start)


GOLD = [(10, 11)]


def test_rank_and_mrr():
    hits = [hit("a", 1, 1), hit("b", 2, 5), hit("c", 3, 11, 12)]
    assert reciprocal_rank(hits, GOLD) == pytest.approx(1 / 3)
    assert reciprocal_rank([hit("a", 1, 1)], GOLD) == 0.0


def test_recall_counts_each_gold_range_once():
    gold = [(10, 10), (50, 50)]
    hits = [hit("a", 1, 10), hit("b", 2, 10), hit("c", 3, 50)]
    assert recall_at_k(hits, gold, 2) == 0.5  # second hit is a duplicate of the first range
    assert recall_at_k(hits, gold, 3) == 1.0


def test_ndcg_never_exceeds_one_with_redundant_hits():
    gold = [(10, 10)]
    hits = [hit("a", 1, 10), hit("b", 2, 10), hit("c", 3, 10)]
    assert ndcg_at_k(hits, gold, 3) == pytest.approx(1.0)


def test_ndcg_rewards_earlier_rank():
    early = ndcg_at_k([hit("a", 1, 10)], GOLD, 5)
    late = ndcg_at_k([hit("x", 1, 1), hit("y", 2, 2), hit("a", 3, 10)], GOLD, 5)
    assert early > late > 0


def test_score_hits_keys():
    scores = score_hits([hit("a", 1, 10)], GOLD, ks=(1, 5))
    assert set(scores) == {"mrr", "hit@1", "recall@1", "ndcg@1", "hit@5", "recall@5", "ndcg@5"}


def _trace(dense, bm25, fused, reranked, context):
    t = Trace(query_id="q", question="?")
    t.record("dense", "retrieve", dense)
    t.record("bm25", "retrieve", bm25)
    t.record("fuse", "transform", fused)
    t.record("rerank", "transform", reranked)
    t.record("context", "transform", context)
    return t


GOOD = hit("g", 1, 10)
BAD = hit("b", 2, 99)


def test_locate_failure_cases():
    assert locate_failure(_trace([BAD], [BAD], [BAD], [BAD], [BAD]), GOLD) == "retrieval_miss"
    # only bm25 finds it, then everything keeps it
    assert locate_failure(_trace([BAD], [GOOD], [GOOD], [GOOD], [GOOD]), GOLD) == "retrieval_ok"
    assert locate_failure(_trace([GOOD], [BAD], [BAD], [BAD], [BAD]), GOLD) == "lost_at_fuse"
    assert locate_failure(_trace([GOOD], [GOOD], [GOOD], [BAD], [BAD]), GOLD) == "lost_at_rerank"
    assert locate_failure(_trace([GOOD], [GOOD], [GOOD], [GOOD], [BAD]), GOLD) == "lost_at_context"
    assert locate_failure(Trace(query_id="q", question="?"), GOLD) == "no_stages"


def test_stage_ranks():
    t = _trace([BAD, GOOD], [BAD], [GOOD], [GOOD], [GOOD])
    assert stage_ranks(t, GOLD) == {
        "dense": 2,
        "bm25": None,
        "fuse": 1,
        "rerank": 1,
        "context": 1,
    }


def test_trace_roundtrip(tmp_path):
    t = _trace([GOOD], [BAD], [GOOD], [GOOD], [GOOD])
    t.answer = "hello"
    path = t.save(tmp_path)
    loaded = load_trace(path)
    assert loaded.answer == "hello"
    assert [s.name for s in loaded.stages] == ["dense", "bm25", "fuse", "rerank", "context"]
    assert loaded.stages[0].hits[0].chunk_id == "g"


def test_golden_validation(tmp_path):
    good = {
        "id": "q1",
        "question": "What is an SSTable?",
        "type": "factual",
        "answerable": True,
        "reference_answer": "A sorted string table.",
        "gold_pages": [[10, 11]],
    }
    unanswerable = {"id": "q2", "question": "Who won the 2030 cup?", "type": "unanswerable",
                    "answerable": False}
    path = tmp_path / "g.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in [good, unanswerable]), encoding="utf-8")
    qs = load_golden(path)
    assert qs[0].gold_pages == [(10, 11)]

    bad = dict(good, id="q3", gold_pages=[])
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError):
        load_golden(path)

    dup = "\n".join(json.dumps(x) for x in [good, good])
    path.write_text(dup, encoding="utf-8")
    with pytest.raises(ValueError):
        load_golden(path)


def test_harness_end_to_end(tmp_path):
    questions = [
        GoldQuestion("q1", "a?", "factual", True, "ans", [(10, 10)]),
        GoldQuestion("q2", "b?", "exact_term", True, "ans", [(20, 20)]),
        GoldQuestion("q3", "c?", "unanswerable", False),
    ]

    def pipeline(q):
        t = Trace(query_id=q.id, question=q.question, config={"chunker": "fake"})
        if q.id == "q1":
            t.record("dense", "retrieve", [hit("a", 1, 10)])
            t.record("rerank", "transform", [hit("a", 1, 10)])
        elif q.id == "q2":
            t.record("dense", "retrieve", [hit("a", 1, 20)])
            t.record("rerank", "transform", [hit("z", 1, 99)])  # reranker drops it
        else:
            t.record("dense", "retrieve", [hit("a", 1, 1)])
            t.record("rerank", "transform", [hit("a", 1, 1)])
        return t

    report = run_eval(questions, pipeline, "unit", ks=(1, 5), out_root=tmp_path)
    assert report["n_scored"] == 2
    assert report["per_stage"]["dense"]["recall@5"] == 1.0
    assert report["per_stage"]["rerank"]["recall@5"] == 0.5
    assert report["failure_counts"]["lost_at_rerank"] == 1
    assert report["failure_counts"]["retrieval_ok"] == 1
    assert (tmp_path / "unit" / "traces" / "q1.json").exists()
    assert (tmp_path / "unit" / "report.json").exists()


def test_harness_survives_pipeline_exception(tmp_path):
    def boom(q):
        raise RuntimeError("nope")

    q = [GoldQuestion("q1", "a?", "factual", True, "ans", [(1, 1)])]
    report = run_eval(q, boom, "err", out_root=tmp_path)
    assert report["failure_counts"] == {"pipeline_error": 1}
