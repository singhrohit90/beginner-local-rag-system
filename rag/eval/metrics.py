"""Retrieval metrics scored against gold page ranges.

A hit is relevant if its page range overlaps a gold range. Each gold range earns credit at most
once (the highest-ranked hit that covers it), so redundant chunks from the same page do not
inflate recall or push nDCG above 1.
"""

import math
from typing import Dict, List, Optional, Sequence, Tuple

from rag.types import Hit

PageRange = Tuple[int, int]


def overlaps(hit: Hit, gold: PageRange) -> bool:
    return hit.page_start <= gold[1] and hit.page_end >= gold[0]


def is_relevant(hit: Hit, gold_pages: Sequence[PageRange]) -> bool:
    return any(overlaps(hit, g) for g in gold_pages)


def first_relevant_rank(hits: Sequence[Hit], gold_pages: Sequence[PageRange]) -> Optional[int]:
    """1-based position of the first relevant hit in the list, None if absent."""
    for position, hit in enumerate(hits, start=1):
        if is_relevant(hit, gold_pages):
            return position
    return None


def _covered_ranges(hits: Sequence[Hit], gold_pages: Sequence[PageRange]) -> List[Optional[int]]:
    """For each gold range, the position of the first hit covering it (None if uncovered)."""
    result: List[Optional[int]] = []
    for gold in gold_pages:
        result.append(next((i for i, h in enumerate(hits, 1) if overlaps(h, gold)), None))
    return result


def hit_rate_at_k(hits: Sequence[Hit], gold_pages: Sequence[PageRange], k: int) -> float:
    return 1.0 if any(is_relevant(h, gold_pages) for h in hits[:k]) else 0.0


def recall_at_k(hits: Sequence[Hit], gold_pages: Sequence[PageRange], k: int) -> float:
    """Share of gold ranges covered by at least one of the top-k hits."""
    if not gold_pages:
        return 0.0
    covered = _covered_ranges(hits, gold_pages)
    return sum(1 for pos in covered if pos is not None and pos <= k) / len(gold_pages)


def reciprocal_rank(hits: Sequence[Hit], gold_pages: Sequence[PageRange]) -> float:
    rank = first_relevant_rank(hits, gold_pages)
    return 1.0 / rank if rank else 0.0


def ndcg_at_k(hits: Sequence[Hit], gold_pages: Sequence[PageRange], k: int) -> float:
    """Binary-gain nDCG where each gold range can be credited once."""
    if not gold_pages:
        return 0.0
    credited: set = set()
    dcg = 0.0
    for position, hit in enumerate(hits[:k], start=1):
        for index, gold in enumerate(gold_pages):
            if index not in credited and overlaps(hit, gold):
                credited.add(index)
                dcg += 1.0 / math.log2(position + 1)
                break
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(k, len(gold_pages)) + 1))
    return dcg / ideal


def score_hits(
    hits: Sequence[Hit], gold_pages: Sequence[PageRange], ks: Sequence[int]
) -> Dict[str, float]:
    scores: Dict[str, float] = {"mrr": reciprocal_rank(hits, gold_pages)}
    for k in ks:
        scores[f"hit@{k}"] = hit_rate_at_k(hits, gold_pages, k)
        scores[f"recall@{k}"] = recall_at_k(hits, gold_pages, k)
        scores[f"ndcg@{k}"] = ndcg_at_k(hits, gold_pages, k)
    return scores
