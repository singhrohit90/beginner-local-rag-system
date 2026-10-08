"""Everything the API does, with no web code. Routes in main.py call these methods.

One upload = one workspace folder:

    data/uploads/<doc_id>/source.pdf, status.json, pages.jsonl, toc.json, chunks/, index/

so documents never share an index and deleting one is deleting its folder. The existing
pipelines are used as they are: ingest() builds the workspace, RagPipeline answers from it.
"""

import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from rag.common.embed import Embedder
from rag.common.llm import LLM
from rag.common.bm25 import BM25Index
from rag.ingestion.chunking.base import load_chunkset
from rag.ingestion.index import get_index
from rag.ingestion.pipeline import ingest
from rag.query.configs import CONFIGS
from rag.query.guard import scan_chunks
from rag.query.pipeline import RagPipeline, RetrievalPipeline
from rag.query.rerank import Reranker

DOC_ID = re.compile(r"^[0-9a-f]{12}$")
STATES = ("queued", "processing", "ready", "failed")


class NotFound(Exception):
    pass


class BadUpload(Exception):
    pass


class DocumentService:
    def __init__(
        self,
        root: Path,
        embedder: Embedder,
        llm: LLM,
        embedder_spec: str,
        traces_dir: Optional[Path] = None,
        reranker: Optional[Reranker] = None,
        max_upload_bytes: int = 50 * 1024 * 1024,
    ):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder
        self.embedder_spec = embedder_spec
        self.llm = llm
        self.reranker = reranker
        self.traces_dir = traces_dir
        self.max_upload_bytes = max_upload_bytes
        self._ingest_lock = threading.Lock()  # one ingestion at a time: the embedder shares the GPU
        self._pipelines: Dict[str, RetrievalPipeline] = {}

    # ---- paths and status ---------------------------------------------------------------

    def _dir(self, doc_id: str) -> Path:
        if not DOC_ID.match(doc_id):  # the id becomes part of a path, so only our own format passes
            raise NotFound(doc_id)
        path = self.root / doc_id
        if not path.is_dir():
            raise NotFound(doc_id)
        return path

    def _write_status(self, doc_id: str, **changes: Any) -> Dict[str, Any]:
        path = self.root / doc_id / "status.json"
        status = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        status.update(changes)
        path.write_text(json.dumps(status, indent=2), encoding="utf-8")
        return status

    def get(self, doc_id: str) -> Dict[str, Any]:
        return json.loads((self._dir(doc_id) / "status.json").read_text(encoding="utf-8"))

    def list(self) -> List[Dict[str, Any]]:
        found = []
        for path in sorted(self.root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if DOC_ID.match(path.name) and (path / "status.json").exists():
                found.append(self.get(path.name))
        return found

    # ---- upload and ingestion -----------------------------------------------------------

    def create(self, filename: str, data: bytes, chunker: str = "recursive") -> Dict[str, Any]:
        """Validate and store an upload. Ingestion runs separately (run_ingestion)."""
        if len(data) > self.max_upload_bytes:
            raise BadUpload(f"file is larger than {self.max_upload_bytes // (1024 * 1024)} MB")
        if not data.startswith(b"%PDF"):  # trust the content, not the extension
            raise BadUpload("not a PDF file")
        doc_id = uuid.uuid4().hex[:12]
        directory = self.root / doc_id
        directory.mkdir(parents=True)
        (directory / "source.pdf").write_bytes(data)
        # the user's filename is only a label; it never becomes a path
        label = re.sub(r"[^\w .()\-]", "_", Path(filename).name)[:120] or "document.pdf"
        return self._write_status(
            doc_id, id=doc_id, name=label, chunker=chunker, state="queued", error=None,
            chunks=0, flagged_chunks=0, created=time.time(),
        )

    def run_ingestion(self, doc_id: str) -> None:
        status = self.get(doc_id)
        directory = self._dir(doc_id)
        try:
            with self._ingest_lock:
                self._write_status(doc_id, state="processing")
                # ingest names its outputs after the PDF file, so the stored name is fixed
                result = ingest(directory / "source.pdf", status["chunker"], self.embedder_spec,
                                out_dir=directory, embedder=self.embedder)
            flagged = sum(r.flagged for r in scan_chunks(result.chunkset.chunks).values())
            self._write_status(doc_id, state="ready", chunks=len(result.chunkset.chunks),
                               flagged_chunks=flagged)
        except Exception as err:  # the status carries the reason; the server keeps running
            self._write_status(doc_id, state="failed", error=f"{type(err).__name__}: {err}")

    def delete(self, doc_id: str) -> None:
        directory = self._dir(doc_id)
        self._pipelines.pop(doc_id, None)
        shutil.rmtree(directory)

    # ---- asking -------------------------------------------------------------------------

    def _retrieval(self, doc_id: str) -> RetrievalPipeline:
        if doc_id in self._pipelines:
            return self._pipelines[doc_id]
        status = self.get(doc_id)
        if status["state"] != "ready":
            raise BadUpload(f"document is {status['state']}, not ready")
        directory = self._dir(doc_id)
        chunkset = load_chunkset(directory / "chunks", status["chunker"])
        for chunk in chunkset.chunks:
            chunk.meta["source"] = doc_id  # lets the per-source cap and the scanner treat uploads as one source
        index = get_index(chunkset, self.embedder, "plain", False, root=directory)
        pipeline = RetrievalPipeline(chunkset, index, BM25Index(chunkset.chunks), self.embedder, self.reranker)
        self._pipelines[doc_id] = pipeline
        return pipeline

    def ask(self, doc_id: str, question: str, config: str = "weighted", style: str = "standard") -> Dict[str, Any]:
        retrieval = self._retrieval(doc_id)
        started = time.perf_counter()
        query_id = f"{doc_id}-{int(time.time() * 1000)}"
        trace = RagPipeline(retrieval, self.llm, style=style).run(query_id, question, CONFIGS[config])
        if self.traces_dir:
            trace.save(self.traces_dir)
        usage = trace.config.get("usage", {})
        context = trace.stage("context").hits
        return {
            "query_id": query_id,
            "answer": trace.answer,
            "abstained": usage.get("abstained", False),
            "blocked": usage.get("blocked", []),
            "citations": trace.citations,
            "passages": [
                {"label": f"S{i}", "chunk_id": h.chunk_id, "page_start": h.page_start,
                 "page_end": h.page_end, "score": round(h.score, 4), "text": h.text}
                for i, h in enumerate(context, start=1)
            ],
            "stages": [{"name": s.name, "hits": len(s.hits), "ms": s.elapsed_ms} for s in trace.stages],
            "llm": self.llm.name,
            "seconds": round(time.perf_counter() - started, 2),
        }
