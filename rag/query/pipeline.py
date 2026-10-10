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
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

from rag.common.chunk_store import ChunkStore, MemoryChunkStore, Scope
from rag.common.embed import Embedder
from rag.common.llm import LLM, LLMResult, stream_answer
from rag.common.store import VectorIndex
from rag.common.trace import Trace
from rag.common.types import Chunk, Hit
from rag.ingestion.chunking.base import ChunkSet
from rag.query import fusion
from rag.query.configs import RetrievalConfig
from rag.query.generate import Answer, answer_from_context, answer_from_result, build_prompts
from rag.query.guard import StreamGuard, filter_output
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
        stem: bool = False,
    ) -> "RetrievalPipeline":
        """One document in a fresh in-memory store. Used by the experiments and the tests."""
        store = MemoryChunkStore.from_chunkset(chunkset, vector_index, doc_id, owner, stem=stem)
        return cls(store, embedder, Scope(owner), reranker)

    def run(self, query_id: str, question: str, config: RetrievalConfig) -> Trace:
        store, scope = self.store, self.scope
        info = store.describe(scope)
        doc_ids = info.pop("doc_ids", [])  # one call answers which chunker and how many documents
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
        single_document = len(doc_ids) == 1
        skipped: List[Tuple[str, List[str]]] = []
        context = select_context(
            hits(merged),
            by_id,
            parents,
            ContextConfig(config.top_k, config.max_words, use_parents=config.use_parents,
                          scan=config.scan, max_per_source=0 if single_document else config.max_per_source,
                          drop_exact_copies=config.drop_exact_copies),
            skipped,
        )
        trace.record("context", "transform", context,
                     skipped_by_scanner=[{"chunk_id": cid, "rules": rules} for cid, rules in skipped])
        return trace


class RagPipeline:
    """Retrieval followed by generation. The trace carries both halves, so a wrong answer can be
    traced to the stage that caused it."""

    def __init__(self, retrieval: RetrievalPipeline, llm: LLM, style: str = "standard",
                 output_filter: bool = True, subject: str = "book"):
        self.retrieval = retrieval
        self.llm = llm
        self.style = style  # prompt style, see rag.query.generate.answer_from_context
        self.output_filter = output_filter  # withhold answers that show signs of a hijack
        self.subject = subject  # "book" (the DDIA prompt) or "document" (uploads)

    def run(self, query_id: str, question: str, config: RetrievalConfig) -> Trace:
        return self.answer(self.retrieval.run(query_id, question, config))

    def answer(self, trace: Trace) -> Trace:
        """Generate from the context already recorded in a retrieval trace."""
        question = trace.question
        context = trace.stage("context").hits
        answer, prompt = answer_from_context(self.llm, question, context, style=self.style,
                                           subject=self.subject)
        trace.answer = answer.text
        blocked: List[str] = []
        if self.output_filter:
            result = filter_output(answer.text, " ".join(h.text for h in context))
            trace.answer, blocked = result.answer, result.reasons
        return self._record(trace, prompt, answer, blocked)

    def _record(self, trace: Trace, prompt: str, answer: Answer, blocked: List[str]) -> Trace:
        trace.config["prompt_style"] = self.style
        trace.prompt = prompt
        trace.citations = [f"S{n}" for n in answer.cited]
        trace.config["llm"] = self.llm.name
        trace.config["usage"] = {
            "prompt_tokens": answer.prompt_tokens,
            "output_tokens": answer.output_tokens,
            "abstained": answer.abstained,
            "blocked": blocked,
        }
        return trace

    def stream(self, trace: Trace) -> Iterator[Tuple[str, str]]:
        """Generate from the context in a retrieval trace, as a stream of events:

            ("token", text)     text that is safe to show now (it has passed the stream guard)
            ("final", replace)  the answer is finished and recorded in the trace; trace.answer is the
                                checked answer. replace is "1" when text already shown must be replaced
                                by trace.answer (the whole-answer check failed after some text went out).

        The guard (rag.query.guard.StreamGuard) holds back anything that could be the start of a
        risky piece until it is judged, so a blocked answer has not already leaked a link. If the
        guard blocks, generation is stopped (the model connection is closed)."""
        context = trace.stage("context").hits
        system, prompt = build_prompts(trace.question, context, self.style, self.subject)
        guard = StreamGuard(" ".join(h.text for h in context)) if self.output_filter else None
        pieces = stream_answer(self.llm, system, prompt, max_output_tokens=600)
        result: Optional[LLMResult] = None
        raw: List[str] = []
        try:
            for piece in pieces:
                if piece.result is not None:
                    result = piece.result
                    break
                raw.append(piece.text)
                safe = guard.feed(piece.text) if guard else piece.text
                if safe:
                    yield ("token", safe)
                if guard and guard.blocked:
                    break  # stop paying for text that will be withheld
        finally:
            pieces.close()  # closes the model connection when we stopped early or the reader went away
        text = result.text if result else ("".join(raw)).strip()
        answer = answer_from_result(result or LLMResult(text=text), context)
        blocked: List[str] = []
        replace = False
        trace.answer = text
        if guard:
            tail, verdict = guard.finish()
            if tail:
                yield ("token", tail)
            trace.answer, blocked = verdict.answer, verdict.reasons
            replace = verdict.blocked and bool(guard.released)
        self._record(trace, prompt, answer, blocked)
        yield ("final", "1" if replace else "")
