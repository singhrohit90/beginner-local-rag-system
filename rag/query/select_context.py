"""Context selection: turn a ranked candidate list into the passages the LLM will actually see.

Steps, in order: swap a retrieved child for its parent (parent-child strategy only), skip
passages the injection scanner flags, drop passages that mostly repeat one already chosen, cap how
many passages one source document may contribute, and stop at `top_k` passages or `max_words`.
Overlapping chunks are common (the fixed and recursive chunkers use overlap), and sending the same
text twice wastes the budget that other evidence needs.

The scan and the per-source cap are security defences. The scan skips a flagged passage and the
next candidate takes its place. The cap stops one document, or many copies of one text, from
filling the context (a flooding attack). A chunk's source is `meta["source"]`; chunks without one,
such as the book's own, are not capped. Upload code must set it to the document id.
"""

from dataclasses import dataclass
from typing import Dict, List, Sequence

from rag.security.scan import scan_text
from rag.common.types import Chunk, Hit


@dataclass
class ContextConfig:
    top_k: int = 5
    max_words: int = 1500
    overlap_threshold: float = 0.5  # drop a passage if this share of it is already selected
    use_parents: bool = True
    scan: bool = True  # skip passages that look like injected instructions
    max_per_source: int = 2  # passages one source may add; 0 turns the cap and exact-copy drop off


def _overlap(a: Chunk, b: Chunk) -> float:
    a_start, a_end = a.meta["span"]
    b_start, b_end = b.meta["span"]
    shared = max(0, min(a_end, b_end) - max(a_start, b_start))
    return shared / max(1, min(a_end - a_start, b_end - b_start))


def hit_from_chunk(chunk: Chunk, rank: int, score: float, keep_text: bool = True) -> Hit:
    return Hit(
        chunk_id=chunk.chunk_id,
        rank=rank,
        score=score,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        text=chunk.text if keep_text else chunk.text[:200],
    )


def select_context(
    ranked: Sequence[Hit],
    chunks: Dict[str, Chunk],
    parents: Dict[str, Chunk],
    config: ContextConfig,
) -> List[Hit]:
    chosen: List[Chunk] = []
    scores: List[float] = []
    words = 0
    per_source: Dict[str, int] = {}
    seen_text = set()
    for hit in ranked:
        chunk = chunks[hit.chunk_id]
        if config.use_parents and "parent_id" in chunk.meta:
            chunk = parents[chunk.meta["parent_id"]]
        if any(c.chunk_id == chunk.chunk_id for c in chosen):
            continue
        if config.scan and scan_text(chunk.text).flagged:
            continue
        if any(_overlap(chunk, c) >= config.overlap_threshold for c in chosen):
            continue
        source = chunk.meta.get("source")
        key = " ".join(chunk.text.split()).lower()
        if config.max_per_source:
            if key in seen_text:
                continue
            if source is not None and per_source.get(source, 0) >= config.max_per_source:
                continue
        size = len(chunk.text.split())
        if chosen and words + size > config.max_words:
            continue
        chosen.append(chunk)
        seen_text.add(key)
        if source is not None:
            per_source[source] = per_source.get(source, 0) + 1
        scores.append(hit.score)
        words += size
        if len(chosen) == config.top_k:
            break
    return [hit_from_chunk(c, i, s) for i, (c, s) in enumerate(zip(chosen, scores), start=1)]
