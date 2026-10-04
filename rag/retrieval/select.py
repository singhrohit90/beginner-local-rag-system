"""Context selection: turn a ranked candidate list into the passages the LLM will actually see.

Steps, in order: swap a retrieved child for its parent (parent-child strategy only), drop
passages that mostly repeat one already chosen, and stop at `top_k` passages or `max_words`.
Overlapping chunks are common (the fixed and recursive chunkers use overlap), and sending the same
text twice wastes the budget that other evidence needs.
"""

from dataclasses import dataclass
from typing import Dict, List, Sequence

from rag.types import Chunk, Hit


@dataclass
class ContextConfig:
    top_k: int = 5
    max_words: int = 1500
    overlap_threshold: float = 0.5  # drop a passage if this share of it is already selected
    use_parents: bool = True


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
    for hit in ranked:
        chunk = chunks[hit.chunk_id]
        if config.use_parents and "parent_id" in chunk.meta:
            chunk = parents[chunk.meta["parent_id"]]
        if any(c.chunk_id == chunk.chunk_id for c in chosen):
            continue
        if any(_overlap(chunk, c) >= config.overlap_threshold for c in chosen):
            continue
        size = len(chunk.text.split())
        if chosen and words + size > config.max_words:
            continue
        chosen.append(chunk)
        scores.append(hit.score)
        words += size
        if len(chosen) == config.top_k:
            break
    return [hit_from_chunk(c, i, s) for i, (c, s) in enumerate(zip(chosen, scores), start=1)]
