"""Everything the API does, with no web code. Routes in main.py call these methods.

One upload = one workspace folder:

    data/uploads/<doc_id>/source.pdf, status.json, pages.jsonl, toc.json, chunks/, index/

so documents never share an index and deleting one is deleting its folder. The existing
pipelines are used as they are: ingest() builds the workspace, RagPipeline answers from it.
"""

import hashlib
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from rag.common.embed import Embedder
from rag.common.llm import LLM
from rag.common.chunk_store import ChunkStore, MemoryChunkStore, Scope
from rag.ingestion.chunking.base import load_chunkset
from rag.ingestion.index import get_index, index_document
from rag.ingestion.pipeline import ingest
from rag.ingestion.sandbox import DEFAULT_MEMORY_MB, DEFAULT_TIMEOUT_SECONDS, extract_in_sandbox
from rag.query.configs import CONFIGS
from rag.query.guard import scan_chunks
from rag.query.pipeline import RagPipeline, RetrievalPipeline
from rag.query.rerank import Reranker

logger = logging.getLogger("rag.api")
DOC_ID = re.compile(r"^[0-9a-f]{12}$")
DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_PAGES = 2000  # the DDIA book is about 600 pages
LOCAL_OWNER = "local"  # the owner until real users arrive, and of any upload made before owners existed
STATES = ("queued", "processing", "ready", "failed")


class NotFound(Exception):
    pass


class BadUpload(Exception):
    pass


class TooLarge(BadUpload):
    """The file is over the size limit; the API reports it as 413."""


class DocumentService:
    def __init__(
        self,
        root: Path,
        embedder: Embedder,
        llm: LLM,
        embedder_spec: str,
        keep_traces: bool = True,
        reranker: Optional[Reranker] = None,
        max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
        store: Optional[ChunkStore] = None,
        max_pages: int = DEFAULT_MAX_PAGES,
        extract_timeout: float = DEFAULT_TIMEOUT_SECONDS,
        extract_memory_mb: int = DEFAULT_MEMORY_MB,
    ):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder
        self.embedder_spec = embedder_spec
        self.llm = llm
        self.reranker = reranker
        self.keep_traces = keep_traces  # one JSON file per question, inside the document's folder
        self.max_upload_bytes = max_upload_bytes
        self.max_pages = max_pages
        self.extract_timeout = extract_timeout
        self.extract_memory_mb = extract_memory_mb
        self._ingest_lock = threading.Lock()  # one ingestion at a time: the embedder shares the GPU
        self._status_lock = threading.Lock()  # one status.json writer at a time
        self._load_lock = threading.Lock()  # a document is loaded into the store once
        self._create_lock = threading.Lock()  # two identical uploads at once must not both pass the duplicate check
        self._running: Set[str] = set()  # documents being ingested right now
        self._deleting: Set[str] = set()  # documents deleted while an ingestion was still running
        self.store: ChunkStore = store or MemoryChunkStore()  # a vector database plugs in here
        self._recover_interrupted()

    # ---- paths and status ---------------------------------------------------------------

    def _dir(self, doc_id: str) -> Path:
        if not DOC_ID.match(doc_id):  # the id becomes part of a path, so only our own format passes
            raise NotFound(doc_id)
        path = self.root / doc_id
        if doc_id in self._deleting or not path.is_dir():
            raise NotFound(doc_id)
        return path

    @staticmethod
    def _retry(action, errors, seconds: float = 2.0):
        """Windows briefly refuses to open a file that another thread is replacing, so retry
        for a short while instead of failing the request."""
        deadline = time.monotonic() + seconds
        while True:
            try:
                return action()
            except errors:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.02)

    @classmethod
    def _read_json(cls, path: Path) -> Dict[str, Any]:
        return cls._retry(lambda: json.loads(path.read_text(encoding="utf-8")), (PermissionError, json.JSONDecodeError))

    @classmethod
    def _atomic_write(cls, path: Path, text: str) -> None:
        """Write to a temporary file and swap it in, so a reader sees the old or new file, never half."""
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        cls._retry(lambda: os.replace(temporary, path), PermissionError)

    def _write_status(self, doc_id: str, **changes: Any) -> Dict[str, Any]:
        directory = self._dir(doc_id)  # raises NotFound if the document was deleted meanwhile
        path = directory / "status.json"
        with self._status_lock:
            status = self._read_json(path) if path.exists() else {}
            status.update(changes)
            self._atomic_write(path, json.dumps(status, indent=2))
        return status

    def _recover_interrupted(self) -> None:
        """A server restart kills background ingestion, so mark what was in flight as failed."""
        for path in self.root.iterdir():
            status_file = path / "status.json"
            if DOC_ID.match(path.name) and status_file.exists():
                try:
                    status = self._read_json(status_file)
                    if status.get("state") in ("queued", "processing"):
                        status.update(state="failed", error="interrupted by a server restart; upload the file again")
                        self._atomic_write(status_file, json.dumps(status, indent=2))
                except (OSError, ValueError):  # one damaged folder must not stop the whole service starting
                    logger.warning("could not read %s; skipping it", status_file)

    def _status(self, doc_id: str) -> Dict[str, Any]:
        """A document's status with no owner check. Internal: background work and recovery use it."""
        return self._read_json(self._dir(doc_id) / "status.json")

    def get(self, doc_id: str, owner: str) -> Dict[str, Any]:
        """Another owner's document is reported as not found, so its existence does not leak."""
        status = self._status(doc_id)
        if status.get("owner", LOCAL_OWNER) != owner:
            raise NotFound(doc_id)
        return status

    def list(self, owner: str) -> List[Dict[str, Any]]:
        found = []
        for path in self.root.iterdir():
            if DOC_ID.match(path.name):
                try:
                    found.append(self.get(path.name, owner))
                except (NotFound, OSError, ValueError):
                    continue  # not this owner's, deleted, or not yet written, while we were listing
        return sorted(found, key=lambda s: s.get("created", 0), reverse=True)

    # ---- upload and ingestion -----------------------------------------------------------

    def create(self, filename: str, data: bytes, owner: str, chunker: str = "recursive") -> Dict[str, Any]:
        """Validate and store an upload. Ingestion runs separately (run_ingestion)."""
        if len(data) > self.max_upload_bytes:
            raise TooLarge(f"file is larger than {self.max_upload_bytes // (1024 * 1024)} MB")
        if not data.startswith(b"%PDF"):  # trust the content, not the extension
            raise BadUpload("not a PDF file")
        digest = hashlib.sha256(data).hexdigest()
        with self._create_lock:
            # The same file with the same chunker uploaded again by the same owner is the same document.
            # Another chunker is a different document (that is how chunkers are compared), a failed one
            # may be retried, and another owner's copy is theirs alone. Uploads made before this check
            # existed have no hash and are not recognised.
            for existing in self.list(owner):
                if (existing.get("sha256") == digest and existing.get("chunker") == chunker
                        and existing["state"] != "failed"):
                    return {**existing, "duplicate": True}
            doc_id = uuid.uuid4().hex[:12]
            directory = self.root / doc_id
            directory.mkdir(parents=True)
            (directory / "source.pdf").write_bytes(data)
            # the user's filename is only a label; it never becomes a path
            label = re.sub(r"[^\w .()\-]", "_", Path(filename).name)[:120] or "document.pdf"
            return self._write_status(
                doc_id, id=doc_id, name=label, owner=owner, sha256=digest, chunker=chunker, state="queued",
                stage=None, error=None, chunks=0, flagged_chunks=0, created=time.time(),
            )

    def run_ingestion(self, doc_id: str) -> None:
        self._running.add(doc_id)
        try:
            status = self._status(doc_id)
            directory = self._dir(doc_id)
            with self._ingest_lock:
                self._write_status(doc_id, state="processing")
                # ingest names its outputs after the PDF file, so the stored name is fixed
                # on_stage keeps status.json current; if the document is deleted meanwhile it raises
                # NotFound, which stops the ingestion here
                result = ingest(directory / "source.pdf", status["chunker"], self.embedder_spec,
                                out_dir=directory, embedder=self.embedder, extractor=self._extract,
                                on_stage=lambda name: self._write_status(doc_id, stage=name))
            flagged = sum(r.flagged for r in scan_chunks(result.chunkset.chunks).values())
            self._write_status(doc_id, state="ready", stage=None, chunks=len(result.chunkset.chunks),
                               flagged_chunks=flagged)
        except NotFound:
            pass  # deleted before or during ingestion: nothing left to report to
        except Exception as err:  # the status carries the reason; the server keeps running
            logger.exception("ingestion of %s failed", doc_id)  # the full traceback stays in the server log
            try:
                self._write_status(doc_id, state="failed", error=self._public_error(err))
            except NotFound:
                pass
        finally:
            self._running.discard(doc_id)
            if doc_id in self._deleting:  # ingestion may have recreated files after the delete
                self._remove_tree(self.root / doc_id)
                self.store.delete_document(doc_id)
                self._deleting.discard(doc_id)

    def _extract(self, pdf: Path, pages_path: Path, toc_path: Path) -> None:
        """PDF -> pages in a child process with a time and memory limit (see sandbox.py)."""
        extract_in_sandbox(pdf, pages_path, toc_path, self.extract_timeout, self.extract_memory_mb,
                           max_pages=self.max_pages)

    @staticmethod
    def _public_error(err: Exception) -> str:
        """The reason shown to the owner. File paths and URLs inside an error message describe the
        server, so they are replaced; the full text stays in the server log."""
        text = str(err) or "no details, see the server log"
        text = re.sub(r"[A-Za-z][A-Za-z0-9+.-]*://\S+", "<url>", text)
        text = re.sub(r"[A-Za-z]:[\\/][^'\"\r\n]*", "<path>", text)  # a Windows path, which may hold spaces
        text = re.sub(r"\S*[\\/]\S*", "<path>", text)  # any other word with a separator in it
        return f"{type(err).__name__}: {text[:300]}"

    @staticmethod
    def _remove_tree(path: Path) -> None:
        for attempt in range(5):  # Windows refuses while a file is still open; wait and retry
            try:
                shutil.rmtree(path)
                return
            except FileNotFoundError:
                return
            except OSError:
                time.sleep(0.2)
        shutil.rmtree(path, ignore_errors=True)

    def delete(self, doc_id: str, owner: str) -> None:
        self.get(doc_id, owner)  # NotFound unless it is this owner's
        directory = self._dir(doc_id)
        if doc_id in self._running:  # the ingestion thread finishes the cleanup when it stops
            self._deleting.add(doc_id)
        self.store.delete_document(doc_id)
        self._remove_tree(directory)

    # ---- asking -------------------------------------------------------------------------

    def _ready_documents(self, owner: str, doc_ids: Optional[Sequence[str]]) -> List[Dict[str, Any]]:
        """The caller's documents that a question may use. None means every ready document they own.
        An id that is not theirs is NotFound, exactly as if it did not exist."""
        if doc_ids is None:
            ready = [status for status in self.list(owner) if status["state"] == "ready"]
            if not ready:
                raise BadUpload("you have no documents that are ready yet")
            return ready
        statuses: List[Dict[str, Any]] = []
        for doc_id in dict.fromkeys(doc_ids):  # drops repeats, keeps the order
            status = self.get(doc_id, owner)
            if status["state"] != "ready":
                raise BadUpload(f"document {status['name']!r} is {status['state']}, not ready")
            statuses.append(status)
        if not statuses:
            raise BadUpload("choose at least one document")
        return statuses

    def _ensure_loaded(self, status: Dict[str, Any]) -> None:
        doc_id = status["id"]
        if not self.store.has_document(doc_id):  # first question since the server started
            with self._load_lock:
                if not self.store.has_document(doc_id):  # another request may have loaded it meanwhile
                    self._load_into_store(doc_id, status)

    def _load_into_store(self, doc_id: str, status: Dict[str, Any]) -> None:
        directory = self._dir(doc_id)
        chunkset = load_chunkset(directory / "chunks", status["chunker"])
        index = get_index(chunkset, self.embedder, "plain", False, root=directory)
        # chunk ids must be unique across the store, and every upload numbers its chunks from zero
        qualify = lambda cid: f"{doc_id}:{cid}"
        for chunk in chunkset.chunks:
            chunk.chunk_id = qualify(chunk.chunk_id)
            chunk.meta["source"] = doc_id  # lets the scanner and per-source cap treat uploads as sources
            if "parent_id" in chunk.meta:
                chunk.meta["parent_id"] = qualify(chunk.meta["parent_id"])
        parents = {}
        for parent in chunkset.parents.values():
            parent.chunk_id = qualify(parent.chunk_id)
            parent.meta["source"] = doc_id  # a parent replaces its child in the context, so it needs the tag too
            parents[parent.chunk_id] = parent
        chunkset.parents = parents
        index_document(self.store, doc_id, status.get("owner", LOCAL_OWNER), chunkset, index)

    def ask(self, doc_id: str, owner: str, question: str, config: str = "weighted",
            style: str = "standard") -> Dict[str, Any]:
        return self.ask_documents(owner, [doc_id], question, config, style)

    def ask_documents(self, owner: str, doc_ids: Optional[Sequence[str]], question: str,
                      config: str = "weighted", style: str = "standard") -> Dict[str, Any]:
        """Answer from one, several or (doc_ids None) all of the owner's documents."""
        statuses = self._ready_documents(owner, doc_ids)
        for status in statuses:
            self._ensure_loaded(status)
        names = {status["id"]: status["name"] for status in statuses}
        retrieval = RetrievalPipeline(self.store, self.embedder, Scope(owner, tuple(names)), self.reranker)
        single = len(statuses) == 1
        started = time.perf_counter()
        query_id = f"{statuses[0]['id'] if single else 'multi'}-{int(time.time() * 1000)}"
        trace = RagPipeline(retrieval, self.llm, style=style, subject="document").run(query_id, question, CONFIGS[config])
        if self.keep_traces and single:
            # Inside the document's folder, so deleting the document deletes its traces. A question over
            # several documents is not saved: its trace holds passages from all of them, and deleting
            # one document could not remove them.
            try:
                trace.save(self._dir(statuses[0]["id"]) / "chat")
            except NotFound:
                pass  # deleted while the model was answering
        usage = trace.config.get("usage", {})
        context = trace.stage("context").hits
        return {
            "query_id": query_id,
            "answer": trace.answer,
            "abstained": usage.get("abstained", False),
            "blocked": usage.get("blocked", []),
            "citations": trace.citations,
            "documents": [{"id": doc_id, "name": name} for doc_id, name in names.items()],
            "passages": [
                {"label": f"S{i}", "chunk_id": h.chunk_id, "doc_id": h.chunk_id.split(":", 1)[0],
                 "doc_name": names.get(h.chunk_id.split(":", 1)[0], ""), "page_start": h.page_start,
                 "page_end": h.page_end, "score": round(h.score, 4), "text": h.text}
                for i, h in enumerate(context, start=1)
            ],
            "skipped_by_scanner": trace.stage("context").meta.get("skipped_by_scanner", []),
            "stages": [{"name": s.name, "hits": len(s.hits), "ms": s.elapsed_ms} for s in trace.stages],
            "llm": self.llm.name,
            "seconds": round(time.perf_counter() - started, 2),
        }
