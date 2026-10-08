"""BM25 keyword search, written out so every term of the formula is visible.

    score(q, d) = sum over query terms t of  idf(t) * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(d) / avg_len))
    idf(t)      = ln(1 + (N - df + 0.5) / (df + 0.5))

k1 limits how much repeating a word helps, and b controls how much long documents are penalised.
There is no stemming, so 'index' and 'indexes' are different terms. That is a known weakness to
test, not an oversight.
"""

import math
import re
from collections import Counter, defaultdict
from typing import Dict, List, Sequence, Tuple

import numpy as np

from rag.common.types import Chunk

_TOKEN = re.compile(r"[a-z0-9_]+")
_STOP = frozenset(
    "a an the of to in is are was were be been and or for on at by with as it its this that from "
    "how what why which does do can".split()
)


def tokenize(text: str, drop_stopwords: bool = True) -> List[str]:
    tokens = _TOKEN.findall(text.lower().replace("’", "'"))
    return [t for t in tokens if not (drop_stopwords and t in _STOP)]


class BM25Index:
    def __init__(self, chunks: Sequence[Chunk], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.postings: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
        lengths = []
        for row, chunk in enumerate(chunks):
            tokens = tokenize(chunk.text)
            lengths.append(len(tokens))
            for term, tf in Counter(tokens).items():
                self.postings[term].append((row, tf))
        self.n = len(chunks)
        self.lengths = np.array(lengths, dtype=np.float32)
        self.avg_len = float(self.lengths.mean()) if self.n else 0.0

    def idf(self, term: str) -> float:
        df = len(self.postings.get(term, ()))
        return math.log(1.0 + (self.n - df + 0.5) / (df + 0.5))

    def search(self, query: str, k: int) -> List[Tuple[int, float]]:
        if self.n == 0:
            return []
        scores = np.zeros(self.n, dtype=np.float32)
        for term in set(tokenize(query)):
            weight = self.idf(term)
            for row, tf in self.postings.get(term, ()):
                norm = tf + self.k1 * (1 - self.b + self.b * self.lengths[row] / self.avg_len)
                scores[row] += weight * tf * (self.k1 + 1) / norm
        k = min(k, self.n)
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [(int(i), float(scores[i])) for i in top if scores[i] > 0]
