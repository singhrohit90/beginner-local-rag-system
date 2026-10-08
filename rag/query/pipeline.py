"""The query pipeline. These classes only decide the order and what to skip; each step is a module.

    question -> dense_search --+
                               +--> fuse -> rerank -> select_context -> generate -> guard
    question -> keyword_search +
                                 retrieve.py  fusion.py  rerank.py  select_context.py  generate.py  guard.py

RetrievalPipeline runs up to select_context. RagPipeline adds generate and the output guard.
Every step writes to the Trace, with stage names dense, bm25, fuse, rerank and context. A config can
switch a stage off, and a stage that is off leaves no trace entry, so the eval scores only what ran.
"""

from dataclasses import asdict
from typing import Dict, List, Optional, Sequence, Tuple

from rag.common.bm25 import BM25Index
from rag.common.embed import Embedder
from rag.common.llm import LLM
from rag.common.store import VectorIndex
from rag.common.trace import Trace
from rag.common.types import Chunk, Hit
from rag.ingestion.chunking.base import ChunkSet
from rag.query import fusion
from rag.query.configs import RetrievalConfig
from rag.query.generate import answer_from_context
from rag.query.guard import filter_output
from rag.query.rerank import Reranker
from rag.query.retrieve import dense_search, keyword_search
from rag.query.select_context import ContextConfig, hit_from_chunk, select_context


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
            scored = dense_search(self.vector_index, self.embedder, question, config.candidates)
            trace.record("dense", "retrieve", self._hits(scored))
            lists.append(scored)
        if config.bm25:
            scored = keyword_search(self.bm25_index, question, config.candidates)
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


class RagPipeline:
    """Retrieval followed by generation. The trace carries both halves, so a wrong answer can be
    traced to the stage that caused it."""

    def __init__(self, retrieval: RetrievalPipeline, llm: LLM, style: str = "standard",
                 output_filter: bool = True):
        self.retrieval = retrieval
        self.llm = llm
        self.style = style  # prompt style, see rag.query.generate.answer_from_context
        self.output_filter = output_filter  # withhold answers that show signs of a hijack

    def run(self, query_id: str, question: str, config: RetrievalConfig) -> Trace:
        return self.answer(self.retrieval.run(query_id, question, config))

    def answer(self, trace: Trace) -> Trace:
        """Generate from the context already recorded in a retrieval trace."""
        question = trace.question
        context = trace.stage("context").hits
        answer, prompt = answer_from_context(self.llm, question, context, style=self.style)
        trace.config["prompt_style"] = self.style
        trace.prompt = prompt
        trace.answer = answer.text
        blocked: List[str] = []
        if self.output_filter:
            result = filter_output(answer.text, " ".join(h.text for h in context))
            trace.answer, blocked = result.answer, result.reasons
        trace.citations = [f"S{n}" for n in answer.cited]
        trace.config["llm"] = self.llm.name
        trace.config["usage"] = {
            "prompt_tokens": answer.prompt_tokens,
            "output_tokens": answer.output_tokens,
            "abstained": answer.abstained,
            "blocked": blocked,
        }
        return trace
