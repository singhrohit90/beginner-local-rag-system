"""Embedding backends behind one small interface, so the stage that needs vectors never knows
which model made them.

    get_embedder("hash")                              offline, deterministic, for tests only
    get_embedder("st:sentence-transformers/all-mpnet-base-v2")   local model, needs the extras

Vectors are L2-normalised, so a dot product is cosine similarity.
"""

import re
import zlib
from typing import List, Protocol

import numpy as np


class Embedder(Protocol):
    name: str
    dim: int

    def embed_documents(self, texts: List[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


def _normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class HashingEmbedder:
    """Bag-of-words hashed into a fixed vector. Texts that share words are similar. It has no
    understanding of meaning, so use it only to test plumbing."""

    def __init__(self, dim: int = 256):
        self.name = f"hash-{dim}"
        self.dim = dim

    def embed_documents(self, texts: List[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                matrix[row, zlib.crc32(word.encode()) % self.dim] += 1.0
        return _normalise(matrix)

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str, doc_prefix: str = "", query_prefix: str = ""):
        from sentence_transformers import SentenceTransformer  # heavy import, kept lazy

        self.name = model_name
        self._model = SentenceTransformer(model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension())
        self._doc_prefix = doc_prefix
        self._query_prefix = query_prefix

    def embed_documents(self, texts: List[str]) -> np.ndarray:
        vectors = self._model.encode(
            [self._doc_prefix + t for t in texts],
            batch_size=64,
            show_progress_bar=len(texts) > 500,
            normalize_embeddings=True,
        )
        return np.asarray(vectors, dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        vector = self._model.encode([self._query_prefix + text], normalize_embeddings=True)
        return np.asarray(vector[0], dtype=np.float32)


def get_embedder(spec: str) -> Embedder:
    if spec == "hash":
        return HashingEmbedder()
    if spec.startswith("st:"):
        return SentenceTransformerEmbedder(spec[3:])
    raise ValueError(f"unknown embedder {spec!r}; use 'hash' or 'st:<model name>'")
