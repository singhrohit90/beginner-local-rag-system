"""Run retrieval experiments: every chunker crossed with every retrieval config, scored on the
golden set. No LLM is involved, so this isolates the retrieval half of the system.

    python -m rag.experiment
    python -m rag.experiment --chunkers recursive,heading --configs dense,bm25,rrf
    python -m rag.experiment --configs rrf,rrf_rerank        # downloads the cross-encoder once

Configs:
    dense           embedding search only
    bm25            keyword search only
    rrf             dense + BM25 merged with reciprocal rank fusion
    weighted        dense + BM25 merged with 0.7 / 0.3 min-max weights
    dense_rerank    dense search, then cross-encoder rerank
    rrf_rerank      RRF, then cross-encoder rerank

Each (chunker, config) writes traces and a report to runs/<prefix><chunker>__<config>/.
"""

import argparse
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from rag.chunking.base import load_chunkset
from rag.config import GOLDEN_DIR, PROCESSED_DIR
from rag.embed import get_embedder
from rag.eval.golden import load_golden
from rag.eval.run_eval import run_eval
from rag.log import setup_logging
from rag.retrieval.bm25 import BM25Index
from rag.retrieval.pipeline import RetrievalConfig, RetrievalPipeline
from rag.retrieval.rerank import CrossEncoderReranker, Reranker
from rag.retrieval.store import VectorIndex, index_dir

logger = logging.getLogger("rag.experiment")

CONFIGS: Dict[str, RetrievalConfig] = {
    "dense": RetrievalConfig("dense", bm25=False),
    "bm25": RetrievalConfig("bm25", dense=False),
    "rrf": RetrievalConfig("rrf", fusion="rrf"),
    "weighted": RetrievalConfig("weighted", fusion="weighted"),
    "dense_rerank": RetrievalConfig("dense_rerank", bm25=False, rerank=True),
    "rrf_rerank": RetrievalConfig("rrf_rerank", fusion="rrf", rerank=True),
}
KS = (1, 3, 5, 10, 30)


def get_index(chunkset, embedder, variant: str, rebuild: bool) -> VectorIndex:
    directory = index_dir(chunkset.strategy, embedder.name, variant)
    if directory.exists() and not rebuild:
        index = VectorIndex.load(directory)
        if index.matches(chunkset.chunks):
            return index
    text_of = (
        (lambda c: f"{c.section}\n{c.text}" if c.section else c.text)
        if variant == "heading"
        else (lambda c: c.text)
    )
    index = VectorIndex.build(chunkset.chunks, embedder, text_of, variant=variant)
    index.save(directory)
    return index


def summarise(report: Dict[str, Any]) -> Dict[str, Any]:
    per_stage = report["per_stage"]
    final = per_stage.get("context", {})
    candidate_stage = "fuse" if "fuse" in per_stage else next(
        s for s in per_stage if s in ("dense", "bm25")
    )
    failures = {k: v for k, v in report["failure_counts"].items() if k != "retrieval_ok"}
    return {
        "hit@1": final.get("hit@1"),
        "hit@5": final.get("hit@5"),
        "recall@5": final.get("recall@5"),
        "mrr": final.get("mrr"),
        "ndcg@5": final.get("ndcg@5"),
        "cand@30": per_stage[candidate_stage].get("recall@30"),
        "failures": failures,
        "n": report["n_scored"],
    }


def print_table(rows: List[Dict[str, Any]]) -> None:
    head = f"{'chunker':<14}{'config':<14}{'hit@1':>7}{'hit@5':>7}{'rec@5':>7}{'mrr':>7}{'ndcg@5':>8}{'cand@30':>9}  failures"
    print(head)
    for r in rows:
        f = ", ".join(f"{k}:{v}" for k, v in sorted(r["failures"].items()))
        print(
            f"{r['chunker']:<14}{r['config']:<14}{r['hit@1']:>7.3f}{r['hit@5']:>7.3f}"
            f"{r['recall@5']:>7.3f}{r['mrr']:>7.3f}{r['ndcg@5']:>8.3f}{r['cand@30']:>9.3f}  {f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--chunkers", default="fixed,recursive,semantic,heading,parent_child")
    parser.add_argument("--configs", default="dense,bm25,rrf,weighted")
    parser.add_argument("--embedder", default="st:sentence-transformers/all-mpnet-base-v2")
    parser.add_argument("--chunks-dir", type=Path, default=PROCESSED_DIR / "chunks")
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR / "ddia_questions.jsonl")
    parser.add_argument("--prefix", default="exp__")
    parser.add_argument("--variant", choices=["plain", "heading"], default="plain",
                        help="heading: embed 'section path + text' instead of text alone")
    parser.add_argument("--rebuild", action="store_true", help="re-embed even if an index exists")
    parser.add_argument("--page-level", action="store_true",
                        help="count a hit when it overlaps the gold pages, even without the evidence text")
    args = parser.parse_args()
    setup_logging()

    questions = load_golden(args.golden)
    embedder = get_embedder(args.embedder)
    configs = [CONFIGS[c.strip()] for c in args.configs.split(",")]
    reranker: Optional[Reranker] = None
    if any(c.rerank for c in configs):
        reranker = CrossEncoderReranker()

    rows: List[Dict[str, Any]] = []
    for name in [c.strip() for c in args.chunkers.split(",")]:
        chunkset = load_chunkset(args.chunks_dir, name)
        index = get_index(chunkset, embedder, args.variant, args.rebuild)
        if "truncated_pct" in index.meta:
            logger.info(
                "%s: median %d tokens, %.1f%% of chunks exceed the model limit of %d (tail not embedded)",
                name, index.meta["median_tokens"], index.meta["truncated_pct"], index.meta["max_tokens"],
            )
        pipeline = RetrievalPipeline(chunkset, index, BM25Index(chunkset.chunks), embedder, reranker)
        for config in configs:
            report = run_eval(
                questions,
                lambda q, c=config: pipeline.run(q.id, q.question, c),
                run_name=f"{args.prefix}{name}__{config.name}",
                ks=KS,
                strict=not args.page_level,
            )
            rows.append({"chunker": name, "config": config.name, **summarise(report)})
    print()
    print_table(rows)


if __name__ == "__main__":
    main()
