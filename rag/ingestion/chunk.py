"""Ingestion step 2: split the cleaned document into chunks.

    make_chunker("heading", max_words=300).chunk(document)  ->  ChunkSet

The strategies themselves are in rag/ingestion/chunking/. This module only picks one by name, so an
orchestrator or an experiment can choose a strategy from a string.
"""

from typing import Optional

from rag.common.embed import Embedder
from rag.ingestion.chunking import (
    FixedChunker,
    HeadingChunker,
    ParentChildChunker,
    RecursiveChunker,
    SemanticChunker,
)

STRATEGIES = ("fixed", "recursive", "heading", "parent_child", "semantic")


def make_chunker(
    name: str,
    *,
    size: int = 200,  # words per chunk, fixed and recursive
    overlap: int = 40,
    max_words: int = 300,  # heading and semantic
    child_size: int = 100,  # parent_child
    embedder: Optional[Embedder] = None,  # semantic only
):
    if name == "fixed":
        return FixedChunker(size=size, overlap=overlap)
    if name == "recursive":
        return RecursiveChunker(size=size, overlap=overlap)
    if name == "heading":
        return HeadingChunker(max_words=max_words)
    if name == "parent_child":
        return ParentChildChunker(child_size=child_size)
    if name == "semantic":
        if embedder is None:
            raise ValueError("the semantic chunker needs an embedder")
        return SemanticChunker(embedder, max_words=max_words)
    raise ValueError(f"unknown chunking strategy {name!r}; choose from {STRATEGIES}")
