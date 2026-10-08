from typing import Callable, Dict

from rag.ingestion.chunking.base import ChunkSet, load_chunks
from rag.ingestion.chunking.document import Document
from rag.ingestion.chunking.fixed import FixedChunker
from rag.ingestion.chunking.heading import HeadingChunker
from rag.ingestion.chunking.parent_child import ParentChildChunker
from rag.ingestion.chunking.recursive import RecursiveChunker
from rag.ingestion.chunking.semantic import SemanticChunker

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
