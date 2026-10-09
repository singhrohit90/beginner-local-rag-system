"""Ingestion step 3: embed the chunks and store the vectors.

The vector index written here is what the query pipeline reads; it is the only link between the
two pipelines. It is cached on disk and rebuilt only when the chunks changed.
"""

from pathlib import Path

from rag.common.config import PROCESSED_DIR
from rag.common.chunk_store import ChunkStore
from rag.common.embed import Embedder
from rag.common.store import VectorIndex, index_dir
from rag.ingestion.chunking.base import ChunkSet


def get_index(
    chunkset: ChunkSet, embedder: Embedder, variant: str = "plain", rebuild: bool = False,
    root: Path = PROCESSED_DIR,
) -> VectorIndex:
    """variant "plain" embeds the chunk text; "heading" embeds "section path + text".
    The index is cached under root/index; the default keeps the book's index in data/processed."""
    directory = index_dir(chunkset.strategy, embedder.name, variant, root)
    text_of = (
        (lambda c: f"{c.section}\n{c.text}" if c.section else c.text)
        if variant == "heading"
        else (lambda c: c.text)
    )
    if directory.exists() and not rebuild:
        index = VectorIndex.load(directory)
        if index.matches(chunkset.chunks, text_of):
            return index
    index = VectorIndex.build(chunkset.chunks, embedder, text_of, variant=variant)
    index.save(directory)
    return index


def index_document(store: ChunkStore, doc_id: str, owner: str, chunkset: ChunkSet, index: VectorIndex) -> None:
    """Write one document's chunks and vectors into a store, replacing any earlier version."""
    store.upsert(
        doc_id, owner, chunkset.chunks, index.vectors, index.embedder_name, chunkset.parents,
        {"chunker": chunkset.strategy, "chunker_params": chunkset.params},
    )
