"""Retrieval settings, and the named configurations the experiments compare.

A config only switches stages on or off and sets their parameters. The stages themselves live in
retrieve.py, fusion.py, rerank.py and select_context.py.
"""

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class RetrievalConfig:
    name: str
    dense: bool = True
    bm25: bool = True
    fusion: str = "rrf"  # "rrf" or "weighted"; ignored when only one retriever is on
    weights: Tuple[float, float] = (0.7, 0.3)  # (dense, bm25) for weighted fusion
    rrf_k: int = 60
    candidates: int = 30  # taken from each retriever
    fused_k: int = 30  # kept after fusion and sent to the reranker
    rerank: bool = False
    top_k: int = 5  # passages in the final context
    max_words: int = 1500
    use_parents: bool = True
    scan: bool = True  # context selection skips passages flagged by rag.query.guard
    max_per_source: int = 2  # cap on passages per source document; 0 = off
    drop_exact_copies: bool = True  # never send the same passage text twice


CONFIGS: Dict[str, RetrievalConfig] = {
    "dense": RetrievalConfig("dense", bm25=False),
    "bm25": RetrievalConfig("bm25", dense=False),
    "rrf": RetrievalConfig("rrf", fusion="rrf"),
    "weighted": RetrievalConfig("weighted", fusion="weighted"),
    "dense_rerank": RetrievalConfig("dense_rerank", bm25=False, rerank=True),
    "rrf_rerank": RetrievalConfig("rrf_rerank", fusion="rrf", rerank=True),
}
