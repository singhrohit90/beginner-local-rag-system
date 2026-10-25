"""The HTTP API and the page that uses it. Routes only: the work is in service.py.

    uvicorn rag.api.main:app --port 8000        then open http://127.0.0.1:8000

Endpoints (the API is /v1; the page at / is only one client of it)
    POST   /v1/documents              upload a PDF, ingestion runs in the background (202); the same
                                      file again by the same owner returns that document with duplicate=true (200)
    GET    /v1/documents              list documents with their status
    GET    /v1/documents/{id}         one document's status (queued, processing, ready, failed)
    POST   /v1/documents/{id}/ask     {"question": "..."} -> answer, passages, trace stages
    POST   /v1/ask                    {"question": "...", "doc_ids": [...] or null}: several or all of your documents
                                      The four ask routes (these two and their /stream forms) take an optional
                                      "conversation_id" and return "conversation_id" and "turn"
    DELETE /v1/documents/{id}
    GET    /v1/health

Request checks (see docs/auth_plan.md): the Host header must be on an allowlist, which stops DNS
rebinding, and a state-changing request that carries an Origin header must come from the server's
own origin or an allowed one, which stops other web pages from driving the API through a browser.
A request with no Origin header is a program (a scraper, an MCP server), not a browser, and passes.
There is no login yet.
"""

from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence

import json
import logging
import re
import threading
import time
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import anyio
from starlette.types import ASGIApp, Receive, Scope, Send
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import iterate_in_threadpool, run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field

from rag.api.conversations import ConversationBusy, ConversationFull, NoSuchConversation
from rag.api.service import DEFAULT_MAX_UPLOAD_BYTES, LOCAL_OWNER, BadUpload, DocumentService, NotFound, TooLarge
from rag.ingestion.chunk import STRATEGIES
from rag.query.configs import CONFIGS

STATIC = Path(__file__).parent / "static"
logger = logging.getLogger("rag.api")
# The service has no reranker loaded, so only the configs that do not need one are offered.
USABLE_CONFIGS = sorted(name for name, c in CONFIGS.items() if not c.rerank)
DEFAULT_HOSTS = ("127.0.0.1", "localhost")
STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}


def current_owner() -> str:
    """Who is calling. There is no login yet, so everyone is the one local user. Keycloak will
    replace this function and nothing else (docs/auth_plan.md); tests override it to act as two
    users. It must never read the owner from a header or a field the caller controls."""
    return LOCAL_OWNER


def _close_when_idle(generator: Iterator, seconds: float = 5.0) -> None:
    """Close a generator that a worker thread may still be running. Python refuses to close a running
    generator (ValueError), so wait until it pauses, which for a stream is at its next piece."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            generator.close()
            return
        except ValueError:
            if time.monotonic() >= deadline:
                return
            time.sleep(0.02)


def _sse(event: str, data: Dict[str, Any]) -> bytes:
    """One server-sent event. json.dumps keeps the data on one line, so text with line breaks cannot end the frame."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")


class LimitUploadBody:
    """Refuses an upload that is too big, whether or not the client says how big it is.

    A declared Content-Length over the limit is refused before any of the body is read. A chunked
    upload declares nothing, and Starlette would write the whole form to a temporary file before the
    route could look at its size, so the bytes are counted as they arrive and the request is refused
    with 413 the moment the limit is passed."""

    def __init__(self, app: ASGIApp, limit: int, path: str = "/v1/documents") -> None:
        self.app, self.limit, self.path = app, limit, path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != self.path:
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > self.limit:
            await self._refuse(scope, receive, send)
            return
        received = 0
        refused = False

        async def counting_receive():
            nonlocal received, refused
            message = await receive()
            if message["type"] == "http.request" and not refused:
                received += len(message.get("body", b""))
                if received > self.limit:
                    refused = True
                    await self._refuse(scope, receive, send)
                    return {"type": "http.disconnect"}  # the route stops reading; its own reply is dropped below
            return message

        async def quiet_send(message):
            if not refused:
                await send(message)

        await self.app(scope, counting_receive, quiet_send)

    @staticmethod
    async def _refuse(scope: Scope, receive: Receive, send: Send) -> None:
        await JSONResponse({"detail": "file is too large"}, status_code=413)(scope, receive, send)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    config: str = "weighted"
    style: str = "standard"
    # A server-issued id; absent or null starts a new conversation. The store checks its 32-hex shape,
    # so every malformed id up to 512 characters gets the same 404 as an unknown one (D-04 refined for
    # CONV-02); a longer one is a 422 from validation.
    conversation_id: Optional[str] = Field(None, max_length=512)


class AboutRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    doc_ids: Optional[List[str]] = Field(None, max_length=50)  # null: every ready document you own


class AskAcrossRequest(AskRequest):
    doc_ids: Optional[List[str]] = Field(None, max_length=50)  # null: every ready document you own


_EMBEDDERS: Dict[str, Any] = {}  # embedder spec -> the loaded model


def build_default_service() -> DocumentService:
    """Real models, chosen by .env: RAG_LLM, RAG_EMBEDDER. Heavy, so only built when serving."""
    from rag.common.config import DATA_DIR
    from rag.common.embed import get_embedder
    from rag.common.llm import get_llm
    from rag.common.secrets import setting

    spec = setting("RAG_EMBEDDER", "st:sentence-transformers/all-mpnet-base-v2")
    # Kept once loaded: if the database is not up yet and this function is run again, the model is not loaded again.
    embedder = _EMBEDDERS.get(spec) or _EMBEDDERS.setdefault(spec, get_embedder(spec))
    kind = setting("RAG_STORE", "memory")
    if kind == "opensearch":  # vectors and text live in the database and survive a restart
        from rag.common.opensearch_store import OpenSearchChunkStore

        store = OpenSearchChunkStore(embedder.name, embedder.dim,
                                     url=setting("RAG_OPENSEARCH_URL", "http://127.0.0.1:9200"))
    elif kind == "memory":
        store = None  # rebuilt from the files in data/uploads at the first question
    else:
        raise ValueError(f"RAG_STORE must be 'memory' or 'opensearch', not {kind!r}")
    return DocumentService(
        root=DATA_DIR / "uploads",
        embedder=embedder,
        store=store,
        embedder_spec=spec,
        # no cache: it would keep every uploaded passage and question on disk after a delete
        llm=get_llm(setting("RAG_LLM", "vllm:/models/gpt-oss-20b"), cache_dir=None),
    )


def create_app(
    service: Optional[DocumentService] = None,
    service_factory: Callable[[], DocumentService] = build_default_service,
    allowed_hosts: Sequence[str] = DEFAULT_HOSTS,
    allowed_origins: Sequence[str] = (),
    uploads_root: Optional[Path] = None,
    warm_up: bool = True,
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
    retry_seconds: float = 5.0,
) -> FastAPI:
    """allowed_hosts: host names the server answers to (no port). allowed_origins: extra browser
    origins, as "scheme://host:port", besides the server's own. uploads_root: where the document
    folders are, so the list can be read before the models have loaded. warm_up: load the models in
    the background at startup, and if that fails (the database is not up yet, a bad setting), keep the
    reason for /v1/health and /v1/status and try again every retry_seconds. max_upload_bytes: the
    largest file an upload may carry (the request is refused as soon as the bytes pass it)."""
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Loading the models takes a while, so start it now, in the background, instead of on the first
        # request. The page and the document list work meanwhile.
        if warm_up and state["service"] is None:
            threading.Thread(target=warm, daemon=True, name="warm-up").start()
        yield

    app = FastAPI(title="RAG document chat", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))
    # a little headroom covers the multipart framing around the file; the service checks the file itself again
    app.add_middleware(LimitUploadBody, limit=max_upload_bytes + 1024 * 1024)
    ingest_gate = anyio.Lock()  # one ingestion at a time, waiting without holding a worker thread

    @app.middleware("http")
    async def reject_foreign_origins(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin is not None and request.method in STATE_CHANGING:
            same_origin = urlparse(origin).netloc == request.headers.get("host")
            if not (same_origin or origin in allowed_origins):
                return JSONResponse({"detail": "origin not allowed"}, status_code=403)
        return await call_next(request)

    v1 = APIRouter(prefix="/v1")
    state: Dict[str, Any] = {"service": service, "error": None}  # error: why the models are not loaded yet

    build_lock = threading.Lock()

    def svc() -> DocumentService:
        if state["service"] is None:  # load the models on first use, not at import
            with build_lock:  # two first requests must not each load the models
                if state["service"] is None:
                    try:
                        state["service"] = service_factory()
                        state["error"] = None
                    except Exception as err:
                        state["error"] = public_reason(err)  # health and status say why, instead of "loading" for ever
                        raise
        return state["service"]

    def warm() -> None:
        """Build the service in the background, trying again until it works."""
        first = True
        while state["service"] is None:
            try:
                svc()
                return
            except Exception as err:
                if first:
                    logger.exception("could not start the models; trying again every %.0f s", retry_seconds)
                    first = False
                else:
                    logger.error("still cannot start the models: %s", err)
                time.sleep(retry_seconds)

    @app.get("/")
    def page() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @v1.get("/health")
    def health() -> Dict[str, Any]:
        # ready: the models are loaded, so questions and uploads will not wait
        return {"ok": True, "ready": state["service"] is not None, "error": state["error"],
                "chunkers": list(STRATEGIES), "configs": USABLE_CONFIGS}

    @v1.get("/status")
    async def status(owner: str = Depends(current_owner)) -> Dict[str, Any]:
        """For the page's light: is the model server reachable, is the database up."""
        if state["service"] is None:  # still loading: report that, do not wait for it
            return {"models_loaded": False, "llm": None, "search": None, "error": state["error"]}
        return await run_in_threadpool(state["service"].status)

    async def run_ingestion_in_turn(service: DocumentService, doc_id: str) -> None:
        """Ingestions run one at a time (they share the GPU). A queued one waits here, on an async lock,
        which costs no thread: waiting inside the service would hold one of the shared worker threads
        per queued upload, and a batch of uploads would leave none for the other routes."""
        async with ingest_gate:
            await run_in_threadpool(service.run_ingestion, doc_id)

    @v1.post("/documents", status_code=202)
    async def upload(background: BackgroundTasks, file: UploadFile = File(...),
                     chunker: str = Form("recursive"), owner: str = Depends(current_owner)) -> Dict[str, Any]:
        if chunker not in STRATEGIES:
            raise HTTPException(422, f"chunker must be one of {list(STRATEGIES)}")
        service = await run_in_threadpool(svc)  # may load models: keep it off the event loop
        data = await file.read(service.max_upload_bytes + 1)
        try:
            status = await run_in_threadpool(service.create, file.filename or "document.pdf", data, owner, chunker)
        except TooLarge as err:
            raise HTTPException(413, str(err))
        except BadUpload as err:
            raise HTTPException(400, str(err))
        if status.get("duplicate"):  # already uploaded by this owner: nothing new to index
            return JSONResponse(status, status_code=200)
        background.add_task(run_ingestion_in_turn, service, status["id"])
        return status

    @v1.get("/documents")
    def list_documents(owner: str = Depends(current_owner)) -> List[Dict[str, Any]]:
        if state["service"] is None and uploads_root is not None:
            return DocumentService.list_in(uploads_root, owner)  # no need to wait for the models
        return svc().list(owner)

    @v1.get("/documents/{doc_id}")
    def get_document(doc_id: str, owner: str = Depends(current_owner)) -> Dict[str, Any]:
        try:
            return svc().get(doc_id, owner)
        except NotFound:
            raise HTTPException(404, "no such document")

    @v1.delete("/documents/{doc_id}", status_code=204)
    def delete_document(doc_id: str, owner: str = Depends(current_owner)) -> None:
        try:
            svc().delete(doc_id, owner)
        except NotFound:
            raise HTTPException(404, "no such document")

    def answer_request(request: AskRequest, call: Callable[[], Dict[str, Any]], what: str) -> Dict[str, Any]:
        """Validate the options, run the question, and map failures to HTTP errors. Shared by the ask routes."""
        check_options(request)
        return guarded(call, what)

    def check_options(request: AskRequest) -> None:
        """The one place that decides which configs and styles a caller may ask for (ask and ask/stream)."""
        if request.config not in USABLE_CONFIGS:
            raise HTTPException(422, f"config must be one of {USABLE_CONFIGS}")
        if request.style not in ("standard", "spotlight"):
            raise HTTPException(422, "style must be standard or spotlight")

    def guarded(call: Callable[[], Dict[str, Any]], what: str) -> Dict[str, Any]:
        """Run a question and map its failures to HTTP errors."""
        try:
            return call()
        except NotFound:
            raise HTTPException(404, "no such document")
        except BadUpload as err:
            raise HTTPException(409, str(err))
        except NoSuchConversation:  # unknown, malformed, another owner's or another scope's: one answer
            raise HTTPException(404, "no such conversation")
        except ConversationBusy:
            raise HTTPException(409, "conversation is busy, retry when the previous answer is finished")
        except ConversationFull:
            raise HTTPException(409, "this conversation is full; start a new conversation")
        except Exception as err:  # most often the model server being unreachable
            logger.exception("ask failed for %s", what)
            raise HTTPException(502, public_reason(err))

    def public_reason(err: Exception) -> str:
        """What the caller is told about a failure: the reason without internal addresses or file paths
        (the full error is in the server log). The same sanitizer as for a failed upload, so no route
        shows more than another; the page folds a long text behind "more", this only stops a huge dump."""
        return DocumentService._public_error(err, limit=4000)

    def stream_request(request: AskRequest, start: Callable[[], Any], what: str) -> StreamingResponse:
        """Validate, run retrieval (errors become proper HTTP statuses here), then stream the answer as
        server-sent events: "token" events with text that passed the stream guard, then one "final"
        event with the whole response, or one "error" event if the model fails part-way."""
        check_options(request)
        events = guarded(start, what)  # NotFound, BadUpload and retrieval failures end here, before any byte is sent

        def frames() -> Iterator[bytes]:
            try:
                for event in events:
                    yield _sse(event["event"], event["data"])
            except Exception as err:  # the model server failed part-way
                logger.exception("stream failed for %s", what)
                yield _sse("error", {"detail": public_reason(err)})
            finally:
                events.close()  # closing the events closes the model connection, so the server stops generating

        frame_iter = frames()

        async def body():
            try:
                async for frame in iterate_in_threadpool(frame_iter):
                    yield frame
            finally:
                # The browser went away, or the stream ended. Close the generator explicitly so the model
                # stops now and not whenever Python collects it; shielded, because a disconnect cancels
                # this task and an unshielded await here would be cancelled at once.
                with anyio.CancelScope(shield=True):
                    await run_in_threadpool(_close_when_idle, frame_iter)

        return StreamingResponse(body(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @v1.post("/documents/{doc_id}/ask")
    def ask(doc_id: str, request: AskRequest, owner: str = Depends(current_owner)) -> Dict[str, Any]:
        return answer_request(
            request, lambda: svc().ask(doc_id, owner, request.question, request.config, request.style,
                                       conversation_id=request.conversation_id),
            f"document {doc_id}")

    @v1.post("/ask")
    def ask_across(request: AskAcrossRequest, owner: str = Depends(current_owner)) -> Dict[str, Any]:
        return answer_request(
            request, lambda: svc().ask_documents(owner, request.doc_ids, request.question, request.config, request.style),
            "several documents")

    @v1.post("/documents/{doc_id}/ask/stream")
    def ask_stream(doc_id: str, request: AskRequest, owner: str = Depends(current_owner)) -> StreamingResponse:
        return stream_request(
            request, lambda: svc().ask_documents_stream(owner, [doc_id], request.question, request.config, request.style),
            f"document {doc_id}")

    @v1.post("/ask/stream")
    def ask_across_stream(request: AskAcrossRequest, owner: str = Depends(current_owner)) -> StreamingResponse:
        return stream_request(
            request, lambda: svc().ask_documents_stream(owner, request.doc_ids, request.question, request.config, request.style),
            "several documents")

    @v1.post("/ask-about")
    def ask_about(request: AboutRequest, owner: str = Depends(current_owner)) -> Dict[str, Any]:
        """Questions about the documents themselves (what they are, how they differ), answered from
        their profiles. A separate route from /ask: the caller chooses it, nothing is routed."""
        return guarded(lambda: svc().ask_about(owner, request.doc_ids, request.question), "about the documents")

    app.include_router(v1)
    return app


def _csv(name: str, default: str = "") -> List[str]:
    from rag.common.secrets import setting

    return [part.strip() for part in setting(name, default).split(",") if part.strip()]


# RAG_ALLOWED_HOSTS: host names this server answers to; RAG_ALLOWED_ORIGINS: extra browser origins.
from rag.common.config import DATA_DIR  # noqa: E402  (paths only, nothing heavy)

app = create_app(allowed_hosts=_csv("RAG_ALLOWED_HOSTS", ",".join(DEFAULT_HOSTS)),
                 allowed_origins=_csv("RAG_ALLOWED_ORIGINS"), uploads_root=DATA_DIR / "uploads")
