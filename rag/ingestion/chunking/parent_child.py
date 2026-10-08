from typing import Any, Dict

from rag.ingestion.chunking.base import ChunkSet, collect
from rag.ingestion.chunking.document import Document
from rag.ingestion.chunking.heading import HeadingChunker
from rag.ingestion.chunking.units import atomic_units, pack


class ParentChildChunker:
    """Retrieve small, answer with big. Parents are heading sections of up to `parent_max` words.
    Children are small recursive chunks cut inside one parent. Only children are embedded and
    searched; after a child is retrieved, its parent text is what the LLM sees. Small chunks match
    a query precisely, large ones give the model enough context to answer."""

    name = "parent_child"

    def __init__(
        self,
        parent_min: int = 120,
        parent_max: int = 600,
        child_size: int = 100,
        child_overlap: int = 20,
        code_max: int = 400,
    ):
        self.parents = HeadingChunker(
            min_words=parent_min, max_words=parent_max, overlap=0, code_max=code_max
        )
        self.parent_max = parent_max
        self.child_size = child_size
        self.child_overlap = child_overlap
        self.code_max = code_max

    def params(self) -> Dict[str, Any]:
        return {
            "parent_min": self.parents.min_words,
            "parent_max": self.parent_max,
            "child_size": self.child_size,
            "child_overlap": self.child_overlap,
            "code_max": self.code_max,
        }

    def chunk(self, doc: Document) -> ChunkSet:
        parent_chunks = []
        children = []
        for section in self.parents.merged_sections(doc):
            spans = self.parents.split(doc, section, self.parent_max, 0)
            for parent in collect(
                doc, "parent", spans, section.title, start_index=len(parent_chunks)
            ):
                parent_chunks.append(parent)
                start, end = parent.meta["span"]
                units = atomic_units(doc, start, end, self.child_size, self.code_max)
                children.extend(
                    collect(
                        doc,
                        self.name,
                        pack(units, self.child_size, self.child_overlap),
                        section.title,
                        start_index=len(children),
                        parent_id=parent.chunk_id,
                    )
                )
        return ChunkSet(
            self.name, self.params(), children, {p.chunk_id: p for p in parent_chunks}
        )
