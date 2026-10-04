"""Per-query trace: what every stage returned. This is the raw material for diagnosis.

Each query run produces one JSON file in runs/<run_name>/traces/<query_id>.json. A stage is
either a "retrieve" stage (dense, bm25: produces candidates from the corpus) or a "transform"
stage (fuse, rerank, select: reorders or trims an existing candidate list).
"""

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from rag.types import Hit


@dataclass
class StageRecord:
    name: str
    kind: str  # "retrieve" or "transform"
    hits: List[Hit]
    elapsed_ms: float = 0.0
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Trace:
    query_id: str
    question: str
    config: Dict[str, Any] = field(default_factory=dict)  # chunker, models, k values, weights
    stages: List[StageRecord] = field(default_factory=list)
    prompt: Optional[str] = None
    answer: Optional[str] = None
    citations: List[str] = field(default_factory=list)
    error: Optional[str] = None
    _t0: float = field(default_factory=time.perf_counter, repr=False)
    _last: float = field(default_factory=time.perf_counter, repr=False)

    def record(
        self, name: str, kind: str, hits: List[Hit], **meta: Any
    ) -> List[Hit]:
        """Log a stage and return its hits so calls can be chained. Time is since the last stage."""
        now = time.perf_counter()
        self.stages.append(
            StageRecord(
                name=name,
                kind=kind,
                hits=hits,
                elapsed_ms=round((now - self._last) * 1000, 2),
                meta=meta,
            )
        )
        self._last = now
        return hits

    def stage(self, name: str) -> Optional[StageRecord]:
        return next((s for s in self.stages if s.name == name), None)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data.pop("_t0")
        data.pop("_last")
        return data

    def save(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.query_id}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path


def load_trace(path: Path) -> Trace:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    stages = [
        StageRecord(
            name=s["name"],
            kind=s["kind"],
            hits=[Hit(**h) for h in s["hits"]],
            elapsed_ms=s["elapsed_ms"],
            meta=s["meta"],
        )
        for s in data.pop("stages")
    ]
    return Trace(stages=stages, **data)
