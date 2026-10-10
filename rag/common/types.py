"""Shared data types. Every stage reads and writes these, nothing else."""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Page:
    page_no: int  # 1-based PDF page index (NOT the printed page number)
    text: str


@dataclass
class Chunk:
    chunk_id: str
    text: str
    page_start: int  # 1-based PDF page index
    page_end: int
    strategy: str  # which chunker produced it, e.g. "fixed", "recursive"
    section: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Hit:
    """One retrieved item at one stage. rank is 1-based."""

    chunk_id: str
    rank: int
    score: float
    page_start: int
    page_end: int
    text: str = ""


Hits = List[Hit]
