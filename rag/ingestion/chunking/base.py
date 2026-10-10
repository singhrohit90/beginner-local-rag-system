import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from rag.ingestion.chunking.document import Document
from rag.common.types import Chunk


@dataclass
class ChunkSet:
    """What a chunker returns. `chunks` are what gets embedded and retrieved. `parents`, when a
    strategy has them, hold the larger text that is handed to the LLM after a child is retrieved."""

    strategy: str
    params: Dict[str, Any]
    chunks: List[Chunk]
    parents: Dict[str, Chunk] = field(default_factory=dict)

    def save(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.strategy}.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"_params": self.params, "_strategy": self.strategy}) + "\n")
            for chunk in self.chunks:
                f.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")
        if self.parents:
            parent_path = directory / f"{self.strategy}.parents.jsonl"
            with open(parent_path, "w", encoding="utf-8") as f:
                for parent in self.parents.values():
                    f.write(json.dumps(parent.to_dict(), ensure_ascii=False) + "\n")
        return path


def load_chunks(path: Path) -> List[Chunk]:
    chunks = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if "_params" in row:
                continue
            chunks.append(Chunk(**row))
    return chunks


def load_chunkset(directory: Path, strategy: str) -> ChunkSet:
    """Read back what ChunkSet.save wrote, including parents for parent_child."""
    path = directory / f"{strategy}.jsonl"
    params: Dict[str, Any] = {}
    with open(path, encoding="utf-8") as f:
        first = json.loads(f.readline())
        if "_params" in first:
            params = first["_params"]
    parents_path = directory / f"{strategy}.parents.jsonl"
    parents = {c.chunk_id: c for c in load_chunks(parents_path)} if parents_path.exists() else {}
    return ChunkSet(strategy, params, load_chunks(path), parents)


class Chunker(Protocol):
    name: str

    def params(self) -> Dict[str, Any]: ...

    def chunk(self, doc: Document) -> ChunkSet: ...


def collect(
    doc: Document,
    name: str,
    spans: List[tuple],
    section: Optional[str] = None,
    start_index: int = 0,
    **meta: Any,
) -> List[Chunk]:
    """Turn (start, end) spans into numbered chunks, skipping empty ones."""
    chunks = []
    for start, end in spans:
        chunk = doc.make_chunk(name, start_index + len(chunks), start, end, section, **meta)
        if chunk:
            chunks.append(chunk)
    return chunks
