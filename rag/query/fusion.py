"""Two ways to merge ranked lists from different retrievers.

Both take lists of (row index, score) from each retriever, best first.

rrf: Reciprocal Rank Fusion uses only the rank, never the score:  sum over lists of 1 / (k + rank).
     BM25 scores and cosine similarities live on different scales, so ignoring scores is its
     strength. k = 60 is the usual default; a larger k flattens the advantage of the top ranks.

weighted: min-max scale each list's scores to 0..1, then take a weighted sum. This is what the
     original repo's OpenSearch pipeline did (0.3 keyword, 0.7 vector). Anything missing from a
     list scores 0 there. It is sensitive to outliers because the best score defines the scale.
"""

from collections import defaultdict
from typing import Dict, List, Sequence, Tuple

Scored = Sequence[Tuple[int, float]]


def rrf(lists: Sequence[Scored], k: int = 60) -> List[Tuple[int, float]]:
    fused: Dict[int, float] = defaultdict(float)
    for ranked in lists:
        for rank, (row, _score) in enumerate(ranked, start=1):
            fused[row] += 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda item: item[1], reverse=True)


def _minmax(scored: Scored) -> Dict[int, float]:
    if not scored:
        return {}
    values = [s for _, s in scored]
    low, high = min(values), max(values)
    if high == low:
        return {row: 1.0 for row, _ in scored}
    return {row: (s - low) / (high - low) for row, s in scored}


def weighted(lists: Sequence[Scored], weights: Sequence[float]) -> List[Tuple[int, float]]:
    if len(lists) != len(weights):
        raise ValueError("one weight per list")
    fused: Dict[int, float] = defaultdict(float)
    for scored, weight in zip(lists, weights):
        for row, value in _minmax(scored).items():
            fused[row] += weight * value
    return sorted(fused.items(), key=lambda item: item[1], reverse=True)
