"""Everything the API does, with no web code. Routes in main.py call these methods.

One upload = one workspace folder:

    data/uploads/<doc_id>/source.pdf, status.json, pages.jsonl, toc.json, chunks/, index/

so documents never share an index and deleting one is deleting its folder. The existing
pipelines are used as they are: ingest() builds the workspace, RagPipeline answers from it.

Conversations (rag/api/conversations.py) live under the same root. A conversation over one document
sits in that document's chat/conversations/ folder, so it goes with the folder; a conversation over
several or all documents sits in _conversations/<owner_key>/ and is removed when any document of its
scope is deleted.

With `rewrite` on, a follow-up is rewritten into a standalone question before retrieval, an ambiguous
one gets one clarifying question, and a new topic starts a clean history (rag/query/rewrite.py).
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
import weakref
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Set, Tuple

from rag.api.conversations import (
    ConversationFull, ConversationStore, new_turn, since_topic_start, to_history_turns,
)
from rag.common.embed import Embedder
from rag.common.llm import LLM
from rag.common.chunk_store import ChunkStore, MemoryChunkStore, Scope
from rag.ingestion.chunking.base import load_chunkset
from rag.ingestion.index import get_index, index_document
from rag.ingestion.pipeline import ingest
from rag.ingestion.profile import PROFILE_FILE, PROFILE_VERSION, build_profile
from rag.ingestion.extract import load_pages
from rag.ingestion.sandbox import DEFAULT_MEMORY_MB, DEFAULT_TIMEOUT_SECONDS, extract_in_sandbox
from rag.query.about import answer_about
from rag.query.configs import CONFIGS
from rag.query.guard import filter_output, scan_chunks
from rag.query.generate import build_prompts
from rag.query.history import HISTORY_WINDOW_TURNS, HistoryTurn, block_turns, fits_context, render_block, window
from rag.query.pipeline import RagPipeline, RetrievalPipeline
from rag.query.rerank import Reranker
from rag.query.rewrite import RewriteResult, needs_rewrite, rewrite_question

logger = logging.getLogger("rag.api")
DOC_ID = re.compile(r"^[0-9a-f]{12}$")
DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_PAGES = 2000  # the DDIA book is about 600 pages
LOCAL_OWNER = "local"  # the owner until real users arrive, and of any upload made before owners existed
STATES = ("queued", "processing", "ready", "failed")
# A profile in the prompt is up to about 8,000 characters (title page, opening pages, contents), so 20
# documents is about 160,000 characters, roughly 40,000 tokens: large, but within the model's window.
MAX_ABOUT_DOCUMENTS = 20


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
        conversations: Optional[ConversationStore] = None,
        rewrite: bool = False,
        rewrite_llm: Optional[LLM] = None,
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
        # conversation files live under this root (D-01); a test may pass its own store on the same root
        self.conversations = conversations or ConversationStore(self.root)
        if rewrite and rewrite_llm is None:  # never fall back silently to the answer model
            raise ValueError("rewrite needs a rewrite_llm")
        # One switch for rewrite, clarify and topic switch; off means Phase 2 behaviour exactly.
        self.rewrite = rewrite
        self.rewrite_llm = rewrite_llm  # built with no disk cache: it sees conversation text from uploads
        self._recover_interrupted()

    # ---- paths and status ---------------------------------------------------------------

    def _dir(self, doc_id: str) -> Path:
        if not DOC_ID.match(doc_id):  # the id becomes part of a path, so only our own format passes
            raise NotFound(doc_id)
        path = self.root / doc_id
        if doc_id in self._deleting or not path.is_dir():
            raise NotFound(doc_id)
        return path

    def _alive(self, doc_ids: Sequence[str]) -> bool:
        """The conversation writer's check: True only while every document still exists and is not
        being deleted."""
        try:
            for doc_id in doc_ids:
                self._dir(doc_id)
        except NotFound:
            return False
        return True

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

    @classmethod
    def list_in(cls, root: Path, owner: str) -> List[Dict[str, Any]]:
        """The owner's documents read straight from the upload folders, with no models loaded. The API
        uses it for the list while the service is still starting. Only this owner's status files are
        returned, exactly as in list()."""
        root = Path(root)
        found = []
        for path in root.iterdir() if root.is_dir() else []:
            if DOC_ID.match(path.name):
                try:
                    status = cls._read_json(path / "status.json")
                except (OSError, ValueError):
                    continue
                if status.get("owner", LOCAL_OWNER) == owner:
                    found.append(status)
        return sorted(found, key=lambda s: s.get("created", 0), reverse=True)

    def list(self, owner: str) -> List[Dict[str, Any]]:
        found = []
        for path in self.root.iterdir():
            if DOC_ID.match(path.name):
                try:
                    found.append(self.get(path.name, owner))
                except (NotFound, OSError, ValueError):
                    continue  # not this owner's, deleted, or not yet written, while we were listing
        return sorted(found, key=lambda s: s.get("created", 0), reverse=True)

    # ---- health -------------------------------------------------------------------------

    @staticmethod
    def _probe(check, seconds: float = 3.0) -> Dict[str, Any]:
        """Run check() -> detail text with a time limit. A failure or a silence is reported, not raised."""
        outcome: Dict[str, Any] = {}

        def run() -> None:
            try:
                outcome["detail"] = check()
            except Exception as err:
                outcome["error"] = DocumentService._public_error(err)

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(seconds)
        if worker.is_alive():
            return {"ok": False, "detail": f"no answer within {int(seconds)} seconds"}
        if "error" in outcome:
            return {"ok": False, "detail": outcome["error"]}
        return {"ok": True, "detail": outcome["detail"]}

    def status(self) -> Dict[str, Any]:
        """Is the model server reachable and is the search database up? Cheap: the model check only
        asks which models the server offers, it does not generate anything."""
        def model() -> str:
            offered = getattr(self.llm, "list_models", None)
            if offered is None:
                return "no connection to check for this model"
            wanted = getattr(self.llm, "_model", None)
            models = offered()
            if wanted is not None and wanted not in models:
                raise RuntimeError(f"the server answers but does not offer {wanted}")
            return f"the server answers and offers {wanted}"

        def search() -> str:
            ping = getattr(self.store, "ping", None)
            return "in memory, no database" if ping is None else f"cluster health: {ping()}"

        return {"models_loaded": True,
                "llm": {"name": self.llm.name, **self._probe(model)},
                "search": self._probe(search)}

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
            self._try_profile(doc_id, status)  # what the document is, for questions about the documents
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

    def _try_profile(self, doc_id: str, status: Dict[str, Any]) -> None:
        try:
            self.profile(doc_id, status)
        except NotFound:
            raise
        except Exception:  # a missing profile must not fail the upload; it is built again when first needed
            logger.exception("could not build the profile of %s", doc_id)

    def profile(self, doc_id: str, status: Dict[str, Any]) -> Dict[str, Any]:
        """The document's profile, built from its extracted pages and contents list the first time
        it is needed (uploads made before profiles existed get theirs then)."""
        directory = self._dir(doc_id)
        path = directory / PROFILE_FILE
        if path.exists():
            try:
                stored = self._read_json(path)
                if stored.get("version") == PROFILE_VERSION:
                    return stored
            except (OSError, ValueError):
                pass  # damaged or from an older version: build it again
        pages = load_pages(directory / "source.pages.jsonl")
        toc = self._read_json(directory / "source.toc.json") if (directory / "source.toc.json").exists() else []
        profile = build_profile(status["name"], pages, toc)
        self._atomic_write(path, json.dumps(profile, indent=1))
        return profile

    def _extract(self, pdf: Path, pages_path: Path, toc_path: Path) -> None:
        """PDF -> pages in a child process with a time and memory limit (see sandbox.py)."""
        extract_in_sandbox(pdf, pages_path, toc_path, self.extract_timeout, self.extract_memory_mb,
                           max_pages=self.max_pages)

    @staticmethod
    def _public_error(err: Exception, limit: int = 1500) -> str:
        """The reason shown to a caller, for every failure the API reports (a failed upload, a failed
        question, a failed stream). File paths and URLs inside an error message describe the server, so
        they are replaced; the full text stays in the server log. A message over `limit` characters is
        cut at a word and ends with "...", so the page can fold it instead of showing a wall of text."""
        text = str(err) or "no details, see the server log"
        text = re.sub(r"[A-Za-z][A-Za-z0-9+.-]*://\S+", "<url>", text)
        text = re.sub(r"[A-Za-z]:[\\/][^'\"\r\n]*", "<path>", text)  # a Windows path, which may hold spaces
        text = re.sub(r"\S*[\\/]\S*", "<path>", text)  # any other word with a separator in it
        if len(text) > limit:
            text = text[:limit].rsplit(" ", 1)[0] + " ..."
        return f"{type(err).__name__}: {text}"

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
        # A question may be loading this document into the store right now. Waiting for the load lock lets
        # that load finish first, so delete_document removes what it wrote; a load that starts later
        # finds the id in _deleting and is refused.
        with self._load_lock:
            self._deleting.add(doc_id)
            self.store.delete_document(doc_id)
        # A conversation writer holds the same lock while it checks the documents are alive and writes, so
        # a write either lands before the folder goes (and goes with it, or is purged) or starts after it
        # (and is dropped). The purge runs while the id is still marked as deleting.
        with self.conversations.lock:
            self._remove_tree(directory)
            self.conversations.purge_document(owner, doc_id)
        if doc_id not in self._running:  # otherwise the ingestion thread finishes the cleanup when it stops
            self._deleting.discard(doc_id)

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
        if doc_id in self._deleting or not directory.is_dir():  # deleted while loading: leave nothing behind
            self.store.delete_document(doc_id)
            raise NotFound(doc_id)

    def ask_about(self, owner: str, doc_ids: Optional[Sequence[str]], question: str) -> Dict[str, Any]:
        """Answer a question about the documents themselves (what they are, how they differ) from their
        profiles. No search is involved, and nothing is saved: the question names no passage to keep."""
        statuses = self._ready_documents(owner, doc_ids)
        if len(statuses) > MAX_ABOUT_DOCUMENTS:  # every profile goes into one prompt, so the prompt must stay bounded
            raise BadUpload(f"choose at most {MAX_ABOUT_DOCUMENTS} documents for a question about the documents "
                            f"(you chose {len(statuses)})")
        started = time.perf_counter()
        answer, _prompt, shown = answer_about(self.llm, question, [self.profile(s["id"], s) for s in statuses])
        context = " ".join(f"{p['name']} {p['title_page']} {p['opening']}" for p in shown)
        checked = filter_output(answer.text, context)  # the same output filter as every other answer
        by_label = {p["label"]: s["id"] for p, s in zip(shown, statuses)}
        return {
            "query_id": f"about-{int(time.time() * 1000)}",
            "answer": checked.answer,
            "blocked": checked.reasons,
            "abstained": False,
            "citations": [f"D{n}" for n in answer.cited if f"D{n}" in by_label],
            "documents": [{"id": s["id"], "name": s["name"], "label": p["label"]} for p, s in zip(shown, statuses)],
            "profiles": shown,
            "llm": self.llm.name,
            "seconds": round(time.perf_counter() - started, 2),
        }

    def ask(self, doc_id: str, owner: str, question: str, config: str = "weighted",
            style: str = "standard", conversation_id: Optional[str] = None) -> Dict[str, Any]:
        return self.ask_documents(owner, [doc_id], question, config, style, conversation_id=conversation_id)

    def _rewrite(self, question: str, turns: List[Dict[str, Any]], names: Dict[str, str]) -> Tuple[RewriteResult, List[HistoryTurn]]:
        """The effective question and the earlier turns the answer prompt may show. Never raises:
        rewrite_question is total, so a down rewriter is a "fallback" result, not an error (D-09)."""
        if not self.rewrite:  # Phase 2's window exactly; stored kind and topic_start flags are ignored
            return RewriteResult("off", question), window(to_history_turns(turns), HISTORY_WINDOW_TURNS)
        win = window(to_history_turns(since_topic_start(turns)), HISTORY_WINDOW_TURNS)
        if not needs_rewrite(question, win):
            return RewriteResult("skipped", question), win
        allow = not (turns and turns[-1].get("kind", "answer") == "clarify")  # never two in a row (D-13)
        result = rewrite_question(self.rewrite_llm, question, win, allow_clarify=allow,
                                  doc_names=list(names.values()))
        # a new topic shows no earlier turn in this turn's prompt (D-14)
        return result, [] if result.status == "new_topic" else win

    def _retrieve(self, owner: str, doc_ids: Optional[Sequence[str]], question: str, config: str, style: str,
                  conversation_id: Optional[str] = None):
        """Everything before the model is called: which documents, the conversation, loading the
        documents, and the retrieval trace. Every failure (NotFound, BadUpload, NoSuchConversation,
        ConversationBusy, ConversationFull) raises here, before any model call, so a streaming request
        can still answer with a proper HTTP status before any streaming starts. The documents are
        checked before the conversation, so a request failing both gets the document error. The
        conversation's lease is released on any raise after it was taken; on success the caller owns
        it (info["lease"]). Retrieval runs on the effective question: the rewrite when the rewrite step
        accepted one, else the raw message; the history only reaches the prompt."""
        statuses = self._ready_documents(owner, doc_ids)
        conversation = self.conversations.open(owner, doc_ids, conversation_id)
        lease = self.conversations.lease(conversation)
        try:
            turns = self.conversations.load_turns(conversation)  # read after the lease, so none is missed
            self.conversations.check_room(turns)
            for status in statuses:
                self._ensure_loaded(status)
            names = {status["id"]: status["name"] for status in statuses}
            retrieval = RetrievalPipeline(self.store, self.embedder, Scope(owner, tuple(names)), self.reranker)
            single = len(statuses) == 1
            started = time.perf_counter()
            query_id = f"{statuses[0]['id'] if single else 'multi'}-{int(time.time() * 1000)}"
            rag = RagPipeline(retrieval, self.llm, style=style, subject="document")
            # Built before retrieval, so the rewrite step and the clarify return can use it; the final
            # return hands back this same dict. "question" is the raw message as sent.
            info = {"names": names, "single": single, "started": started, "query_id": query_id,
                    "first": statuses[0]["id"], "conversation": conversation, "lease": lease,
                    "turn": len(turns) + 1, "question": question}
            result, shown_turns = self._rewrite(question, turns, names)
            info["rewrite"] = result
            trace = retrieval.run(query_id, result.question, CONFIGS[config])  # the effective question (D-10)
            block = render_block(shown_turns)  # rendered after the rewrite decision (D-14)
            info["history_block"] = block
            if block:
                # Measured on the real prompt, so spotlight framing counts; never on a first turn, so a
                # single-turn question behaves exactly as today. Not trace.prompt: the stream builds its
                # prompt lazily. The same 409 as the caps; the except below releases the lease.
                system, user = build_prompts(trace.question, trace.stage("context").hits, style, "document",
                                             history_block=block)
                if not fits_context(system, user):
                    raise ConversationFull()
            shown = block_turns(block)
            trace.config["conversation"] = {"id": conversation.id, "turn": len(turns) + 1,
                                            "history_turns": shown, "dropped_turns": len(turns) - shown}
            if self.rewrite:  # with the switch off the dict keeps exactly the four Phase 2 keys
                trace.config["conversation"].update(
                    original_question=question,
                    rewritten_question=result.rewritten_question,
                    rewrite=result.status,
                    fallback_reason=result.reason,
                    rewrite_ms=result.elapsed_ms,
                    rejected_question=result.rejected_question,  # trace only, never the response (A11)
                )
            return rag, trace, info
        except BaseException:
            lease.release()
            raise

    def _describe(self, trace, info: Dict[str, Any]) -> Dict[str, Any]:
        """Save the trace (single-document questions only) and build the response."""
        names, started, query_id = info["names"], info["started"], info["query_id"]
        if self.keep_traces and info["single"]:
            # Inside the document's folder, so deleting the document deletes its traces. A question over
            # several documents is not saved: its trace holds passages from all of them, and deleting
            # one document could not remove them.
            try:
                trace.save(self._dir(info["first"]) / "chat")
            except (NotFound, FileNotFoundError):
                pass  # deleted while the model was answering (or while the trace was being written)
        usage = trace.config.get("usage", {})
        context = trace.stage("context").hits
        return {
            "query_id": query_id,
            "conversation_id": info["conversation"].id,
            "turn": info["turn"],
            "kind": "answer",
            "rewrite": info["rewrite"].as_response(),
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

    def _remember(self, trace, info: Dict[str, Any], result: Dict[str, Any]) -> None:
        """Store the turn as the caller saw it, then free the conversation. Called only on the success
        path, before the answer is returned or the final event is yielded (D-09, D-10); it runs whether
        or not keep_traces is on, because the history is what the next question needs (D-11)."""
        turn = new_turn(info["question"], result["answer"], list(info["names"]), info["query_id"],
                        rewritten=info["rewrite"].rewritten_question)
        try:
            self.conversations.append_turn(info["conversation"], turn, self._alive)
        finally:
            info["lease"].release()

    def ask_documents(self, owner: str, doc_ids: Optional[Sequence[str]], question: str,
                      config: str = "weighted", style: str = "standard",
                      conversation_id: Optional[str] = None) -> Dict[str, Any]:
        """Answer from one, several or (doc_ids None) all of the owner's documents. conversation_id None
        starts a new conversation; the response carries its id and the turn number."""
        rag, trace, info = self._retrieve(owner, doc_ids, question, config, style, conversation_id)
        try:
            rag.answer(trace, history_block=info["history_block"])
            result = self._describe(trace, info)
            self._remember(trace, info, result)
            return result
        finally:
            info["lease"].release()

    def ask_documents_stream(self, owner: str, doc_ids: Optional[Sequence[str]], question: str,
                             config: str = "weighted", style: str = "standard",
                             conversation_id: Optional[str] = None) -> Iterator[Dict[str, Any]]:
        """Like ask_documents, but returns the answer as a stream of events:

            {"event": "token", "data": {"text": ...}}   text that has passed the stream guard
            {"event": "final", "data": {...}}           the same response as ask_documents (with
                                                        "conversation_id" and "turn"), plus
                                                        "replace": true when the text already sent must be
                                                        replaced by data["answer"] (the final check failed)

        Retrieval happens before this returns, so a missing document or a not-ready one, and an unknown,
        busy or full conversation, raises here, not part-way through a stream. Closing the returned
        iterator stops the model."""
        rag, trace, info = self._retrieve(owner, doc_ids, question, config, style, conversation_id)
        lease = info["lease"]
        stream = rag.stream(trace, history_block=info["history_block"])  # a generator: creating it runs nothing

        def events() -> Iterator[Dict[str, Any]]:
            try:
                for kind, value in stream:
                    if kind == "token":
                        yield {"event": "token", "data": {"text": value}}
                    else:
                        result = self._describe(trace, info)
                        result["replace"] = bool(value)
                        # persist, then release, then yield: a client that asks again the moment it sees
                        # final must not get a spurious 409 while this generator waits to be closed
                        self._remember(trace, info, result)
                        yield {"event": "final", "data": result}
            finally:
                stream.close()  # a reader that went away must stop the model, not leave it running
                lease.release()  # idempotent: a model error, a guard stop, a disconnect or an early close

        generator = events()
        # a generator that is never started never runs its finally; dropping it must still free the conversation
        weakref.finalize(generator, lease.release)
        return generator
