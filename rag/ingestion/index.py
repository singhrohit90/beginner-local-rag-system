"""Ingestion step 3: embed the chunks and store the vectors.

The vector index written here is what the query pipeline reads; it is the only link between the
two pipelines. It is cached on disk and rebuilt only when the chunks changed.
"""

from rag.common.embed import Embedder
from rag.common.store import VectorIndex, index_dir
from rag.ingestion.chunking.base import ChunkSet


def get_index(chunkset: ChunkSet, embedder: Embedder, variant: str = "plain", rebuild: bool = False) -> VectorIndex:
    """variant "plain" embeds the chunk text; "heading" embeds "section path + text"."""
    directory = index_dir(chunkset.strategy, embedder.name, variant)
    if directory.exists() and not rebuild:
        index = VectorIndex.load(directory)
        if index.matches(chunkset.chunks):
            return index
    text_of = (
        (lambda c: f"{c.section}\n{c.text}" if c.section else c.text)
        if variant == "heading"
        else (lambda c: c.text)
    )
    index = VectorIndex.build(chunkset.chunks, embedder, text_of, variant=variant)
    index.save(directory)
    return index
