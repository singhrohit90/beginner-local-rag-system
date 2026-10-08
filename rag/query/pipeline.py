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

from rag.common.chunk_store import ChunkStore, MemoryChunkStore, Scope
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
    """Reads from a ChunkStore, for one Scope (an owner and, optionally, some of their documents)."""

    def __init__(
        self,
        store: ChunkStore,
        embedder: Embedder,
        scope: Scope,
        reranker: Optional[Reranker] = None,
    ):
        self.store = store
        self.embedder = embedder
        self.scope = scope
        self.reranker = reranker

    @classmethod
    def from_chunkset(
        cls,
        chunkset: ChunkSet,
        vector_index: VectorIndex,
        embedder: Embedder,
        reranker: Optional[Reranker] = None,
        owner: str = "local",
        doc_id: str = "doc",
    ) -> "RetrievalPipeline":
        """One document in a fresh in-memory store. Used by the experiments and the tests."""
        store = MemoryChunkStore.from_chunkset(chunkset, vector_index, doc_id, owner)
        return cls(store, embedder, Scope(owner), reranker)

    def run(self, query_id: str, question: str, config: RetrievalConfig) -> Trace:
        store, scope = self.store, self.scope
        info = store.describe(scope)
        trace = Trace(
            query_id=query_id,
            question=question,
            config={
                "chunker": info.get("chunker"),
                "chunker_params": info.get("chunker_params"),
                "embedder": self.embedder.name,
                "reranker": self.reranker.name if (config.rerank and self.reranker) else None,
                "retrieval": asdict(config),
            },
        )
        by_id: Dict[str, Chunk] = {}

        def keyed(results: List[Tuple[Chunk, float]]) -> List[Tuple[str, float]]:
            for chunk, _ in results:
                by_id[chunk.chunk_id] = chunk
            return [(chunk.chunk_id, score) for chunk, score in results]

        def hits(scored: Sequence[Tuple[str, float]]) -> List[Hit]:
            return [hit_from_chunk(by_id[cid], rank, score) for rank, (cid, score) in enumerate(scored, start=1)]

        lists: List[List[Tuple[str, float]]] = []
        if config.dense:
            vector = self.embedder.embed_query(question)
            scored = keyed(dense_search(store, vector, config.candidates, scope))
            trace.record("dense", "retrieve", hits(scored))
            lists.append(scored)
        if config.bm25:
            scored = keyed(keyword_search(store, question, config.candidates, scope))
            trace.record("bm25", "retrieve", hits(scored))
            lists.append(scored)

        if len(lists) == 2:
            if config.fusion == "rrf":
                merged = fusion.rrf(lists, k=config.rrf_k)
            elif config.fusion == "weighted":
                merged = fusion.weighted(lists, config.weights)
            else:
                raise ValueError(f"unknown fusion {config.fusion!r}")
            merged = merged[: config.fused_k]
            trace.record("fuse", "transform", hits(merged), method=config.fusion)
        else:
            merged = lists[0][: config.fused_k]

        if config.rerank:
            if not self.reranker:
                raise ValueError(f"config {config.name!r} wants a reranker but none was given")
            texts = [by_id[cid].text for cid, _ in merged]
            new_scores = self.reranker.score(question, texts)
            order = sorted(range(len(merged)), key=lambda i: new_scores[i], reverse=True)
            merged = [(merged[i][0], new_scores[i]) for i in order]
            trace.record("rerank", "transform", hits(merged))

        parent_ids = [c.meta["parent_id"] for c in by_id.values() if "parent_id" in c.meta]
        parents = store.get_parents(parent_ids, scope) if parent_ids and config.use_parents else {}
        # With one document in scope there is nothing to flood, so the per-source cap would only
        # cut a legitimate document down to a few passages.
        single_document = len(store.document_ids(scope)) == 1
        context = select_context(
            hits(merged),
            by_id,
            parents,
            ContextConfig(config.top_k, config.max_words, use_parents=config.use_parents,
                          scan=config.scan, max_per_source=0 if single_document else config.max_per_source),
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
