"""The query path up to, but not including, the LLM. Each stage writes its output to the trace.

    question -> dense search --+
                               +--> fuse -> rerank -> select context
    question -> BM25 search ---+

Stage names in the trace: dense, bm25, fuse, rerank, context. A config can switch stages off, and
a stage that is off leaves no trace entry, so the eval harness scores only what actually ran.
"""

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from rag.chunking.base import ChunkSet
from rag.embed import Embedder
from rag.retrieval import fusion
from rag.retrieval.bm25 import BM25Index
from rag.retrieval.rerank import Reranker
from rag.retrieval.select import ContextConfig, hit_from_chunk, select_context
from rag.retrieval.store import VectorIndex
from rag.trace import Trace
from rag.types import Chunk, Hit


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
    scan: bool = True  # context selection skips passages flagged by rag.security.scan
    max_per_source: int = 2  # cap on passages per source document; 0 = off


class RetrievalPipeline:
    def __init__(
        self,
        chunkset: ChunkSet,
        vector_index: VectorIndex,
        bm25_index: BM25Index,
        embedder: Embedder,
        reranker: Optional[Reranker] = None,
    ):
        self.chunkset = chunkset
        self.chunks: List[Chunk] = chunkset.chunks
        self.by_id: Dict[str, Chunk] = {c.chunk_id: c for c in self.chunks}
        self.vector_index = vector_index
        self.bm25_index = bm25_index
        self.embedder = embedder
        self.reranker = reranker

    def _hits(self, scored: Sequence[Tuple[int, float]], keep_text: bool = True) -> List[Hit]:
        return [
            hit_from_chunk(self.chunks[row], rank, score, keep_text)
            for rank, (row, score) in enumerate(scored, start=1)
        ]

    def run(self, query_id: str, question: str, config: RetrievalConfig) -> Trace:
        trace = Trace(
            query_id=query_id,
            question=question,
            config={
                "chunker": self.chunkset.strategy,
                "chunker_params": self.chunkset.params,
                "embedder": self.embedder.name,
                "reranker": self.reranker.name if (config.rerank and self.reranker) else None,
                "retrieval": asdict(config),
            },
        )
        lists: List[List[Tuple[int, float]]] = []
        if config.dense:
            scored = self.vector_index.search(self.embedder.embed_query(question), config.candidates)
            trace.record("dense", "retrieve", self._hits(scored))
            lists.append(scored)
        if config.bm25:
            scored = self.bm25_index.search(question, config.candidates)
            trace.record("bm25", "retrieve", self._hits(scored))
            lists.append(scored)

        if len(lists) == 2:
            if config.fusion == "rrf":
                merged = fusion.rrf(lists, k=config.rrf_k)
            elif config.fusion == "weighted":
                merged = fusion.weighted(lists, config.weights)
            else:
                raise ValueError(f"unknown fusion {config.fusion!r}")
            merged = merged[: config.fused_k]
            trace.record("fuse", "transform", self._hits(merged), method=config.fusion)
        else:
            merged = lists[0][: config.fused_k]

        if config.rerank:
            if not self.reranker:
                raise ValueError(f"config {config.name!r} wants a reranker but none was given")
            texts = [self.chunks[row].text for row, _ in merged]
            new_scores = self.reranker.score(question, texts)
            order = sorted(range(len(merged)), key=lambda i: new_scores[i], reverse=True)
            merged = [(merged[i][0], new_scores[i]) for i in order]
            trace.record("rerank", "transform", self._hits(merged))

        context = select_context(
            self._hits(merged, keep_text=True),
            self.by_id,
            self.chunkset.parents,
            ContextConfig(config.top_k, config.max_words, use_parents=config.use_parents,
                          scan=config.scan, max_per_source=config.max_per_source),
        )
        trace.record("context", "transform", context)
        return trace
