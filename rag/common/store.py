"""A deliberately simple vector store: a numpy matrix on disk and exact cosine search.

For a few thousand chunks, brute force takes milliseconds and is exact, so any ranking mistake is
the embedding's fault and not an approximate index's. A real vector database can replace this
class later without touching the stages that call `search`.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence, Tuple

import numpy as np

from rag.common.config import PROCESSED_DIR
from rag.common.embed import Embedder
from rag.common.types import Chunk


def index_dir(chunker: str, embedder_name: str, variant: str = "plain") -> Path:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", embedder_name).strip("-")
    return PROCESSED_DIR / "index" / f"{chunker}__{slug}__{variant}"


@dataclass
class VectorIndex:
    chunk_ids: List[str]
    vectors: np.ndarray  # one L2-normalised row per chunk
    embedder_name: str
    meta: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        chunks: Sequence[Chunk],
        embedder: Embedder,
        text_of: Callable[[Chunk], str] = lambda c: c.text,
        **meta: Any,
    ) -> "VectorIndex":
        texts = [text_of(c) for c in chunks]
        info: Dict[str, Any] = dict(meta)
        count_tokens = getattr(embedder, "count_tokens", None)
        if count_tokens:
            lengths = count_tokens(texts)
            limit = embedder.max_tokens  # type: ignore[attr-defined]
            info["max_tokens"] = limit
            info["truncated_pct"] = round(100 * sum(n > limit for n in lengths) / len(lengths), 1)
            info["median_tokens"] = int(np.median(lengths))
        return cls([c.chunk_id for c in chunks], embedder.embed_documents(texts), embedder.name, info)

    def search(self, query_vector: np.ndarray, k: int) -> List[Tuple[int, float]]:
        """Top-k (row index, cosine similarity), best first."""
        scores = self.vectors @ query_vector
        k = min(k, len(scores))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [(int(i), float(scores[i])) for i in top]

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / "vectors.npy", self.vectors)
        (directory / "index.json").write_text(
            json.dumps(
                {"chunk_ids": self.chunk_ids, "embedder": self.embedder_name, "meta": self.meta}
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, directory: Path) -> "VectorIndex":
        info = json.loads((directory / "index.json").read_text(encoding="utf-8"))
        return cls(
            info["chunk_ids"], np.load(directory / "vectors.npy"), info["embedder"], info["meta"]
        )

    def matches(self, chunks: Sequence[Chunk]) -> bool:
        """True if this index was built from exactly these chunks, in this order."""
        return self.chunk_ids == [c.chunk_id for c in chunks]
