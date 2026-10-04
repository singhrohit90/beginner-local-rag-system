from typing import Callable, Dict

from rag.chunking.base import ChunkSet, load_chunks
from rag.chunking.document import Document
from rag.chunking.fixed import FixedChunker
from rag.chunking.heading import HeadingChunker
from rag.chunking.parent_child import ParentChildChunker
from rag.chunking.recursive import RecursiveChunker
from rag.chunking.semantic import SemanticChunker

# Strategies that need no embedder. Semantic is built separately because it needs one.
SIMPLE_CHUNKERS: Dict[str, Callable[[], object]] = {
    "fixed": FixedChunker,
    "recursive": RecursiveChunker,
    "heading": HeadingChunker,
    "parent_child": ParentChildChunker,
}

__all__ = [
    "ChunkSet",
    "Document",
    "FixedChunker",
    "HeadingChunker",
    "ParentChildChunker",
    "RecursiveChunker",
    "SemanticChunker",
    "SIMPLE_CHUNKERS",
    "load_chunks",
]
