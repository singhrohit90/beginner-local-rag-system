"""The HTTP API and the page that uses it. Routes only: the work is in service.py.

    uvicorn rag.api.main:app --port 8000        then open http://127.0.0.1:8000

Endpoints (the API is /v1; the page at / is only one client of it)
    POST   /v1/documents              upload a PDF, ingestion runs in the background (202); the same
                                      file again by the same owner returns that document with duplicate=true (200)
    GET    /v1/documents              list documents with their status
    GET    /v1/documents/{id}         one document's status (queued, processing, ready, failed)
    POST   /v1/documents/{id}/ask     {"question": "..."} -> answer, passages, trace stages
    POST   /v1/ask                    {"question": "...", "doc_ids": [...] or null}: several or all of your documents
    DELETE /v1/documents/{id}
    GET    /v1/health

Request checks (see docs/auth_plan.md): the Host header must be on an allowlist, which stops DNS
rebinding, and a state-changing request that carries an Origin header must come from the server's
own origin or an allowed one, which stops other web pages from driving the API through a browser.
A request with no Origin header is a program (a scraper, an MCP server), not a browser, and passes.
There is no login yet.
"""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import logging
import re
import threading
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field

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


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    config: str = "weighted"
    style: str = "standard"


class AskAcrossRequest(AskRequest):
    doc_ids: Optional[List[str]] = Field(None, max_length=50)  # null: every ready document you own


def build_default_service() -> DocumentService:
    """Real models, chosen by .env: RAG_LLM, RAG_EMBEDDER. Heavy, so only built when serving."""
    from rag.common.config import DATA_DIR
    from rag.common.embed import get_embedder
    from rag.common.llm import get_llm
    from rag.common.secrets import setting

    spec = setting("RAG_EMBEDDER", "st:sentence-transformers/all-mpnet-base-v2")
    embedder = get_embedder(spec)
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
) -> FastAPI:
    """allowed_hosts: host names the server answers to (no port). allowed_origins: extra browser
    origins, as "scheme://host:port", besides the server's own. uploads_root: where the document
    folders are, so the list can be read before the models have loaded. warm_up: load the models in
    the background at startup."""
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Loading the models takes a while, so start it now, in the background, instead of on the first
        # request. The page and the document list work meanwhile.
        if warm_up and state["service"] is None:
            threading.Thread(target=svc, daemon=True, name="warm-up").start()
        yield

    app = FastAPI(title="RAG document chat", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))

    @app.middleware("http")
    async def reject_oversize_uploads(request: Request, call_next):
        # Refuse on the declared size before the body is read. The service checks again for clients that
        # send no Content-Length. A little headroom covers the multipart framing around the file.
        declared = request.headers.get("content-length", "")
        if (request.method == "POST" and request.url.path == "/v1/documents" and declared.isdigit()
                and int(declared) > DEFAULT_MAX_UPLOAD_BYTES + 1024 * 1024):
            return JSONResponse({"detail": "file is too large"}, status_code=413)
        return await call_next(request)

    @app.middleware("http")
    async def reject_foreign_origins(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin is not None and request.method in STATE_CHANGING:
            same_origin = urlparse(origin).netloc == request.headers.get("host")
            if not (same_origin or origin in allowed_origins):
                return JSONResponse({"detail": "origin not allowed"}, status_code=403)
        return await call_next(request)

    v1 = APIRouter(prefix="/v1")
    state: Dict[str, Optional[DocumentService]] = {"service": service}

    build_lock = threading.Lock()

    def svc() -> DocumentService:
        if state["service"] is None:  # load the models on first use, not at import
            with build_lock:  # two first requests must not each load the models
                if state["service"] is None:
                    state["service"] = service_factory()
        return state["service"]

    @app.get("/")
    def page() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @v1.get("/health")
    def health() -> Dict[str, Any]:
        # ready: the models are loaded, so questions and uploads will not wait
        return {"ok": True, "ready": state["service"] is not None, "chunkers": list(STRATEGIES),
                "configs": USABLE_CONFIGS}

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
        background.add_task(service.run_ingestion, status["id"])
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
        """Validate the options, run the question, and map failures to HTTP errors. Shared by both ask routes."""
        if request.config not in USABLE_CONFIGS:
            raise HTTPException(422, f"config must be one of {USABLE_CONFIGS}")
        if request.style not in ("standard", "spotlight"):
            raise HTTPException(422, "style must be standard or spotlight")
        try:
            return call()
        except NotFound:
            raise HTTPException(404, "no such document")
        except BadUpload as err:
            raise HTTPException(409, str(err))
        except Exception as err:  # most often the model server being unreachable
            logger.exception("ask failed for %s", what)
            # the caller gets the reason without internal addresses; the full error is in the server log
            reason = re.sub(r"https?://\S+", "<url>", str(err))
            if len(reason) > 4000:  # the page folds long text behind "more"; this only stops a huge dump
                reason = reason[:4000].rsplit(" ", 1)[0] + " ..."
            raise HTTPException(502, f"{type(err).__name__}: {reason}")

    @v1.post("/documents/{doc_id}/ask")
    def ask(doc_id: str, request: AskRequest, owner: str = Depends(current_owner)) -> Dict[str, Any]:
        return answer_request(request, lambda: svc().ask(doc_id, owner, request.question, request.config, request.style),
                              f"document {doc_id}")

    @v1.post("/ask")
    def ask_across(request: AskAcrossRequest, owner: str = Depends(current_owner)) -> Dict[str, Any]:
        return answer_request(
            request, lambda: svc().ask_documents(owner, request.doc_ids, request.question, request.config, request.style),
            "several documents")

    app.include_router(v1)
    return app


def _csv(name: str, default: str = "") -> List[str]:
    from rag.common.secrets import setting

    return [part.strip() for part in setting(name, default).split(",") if part.strip()]


# RAG_ALLOWED_HOSTS: host names this server answers to; RAG_ALLOWED_ORIGINS: extra browser origins.
from rag.common.config import DATA_DIR  # noqa: E402  (paths only, nothing heavy)

app = create_app(allowed_hosts=_csv("RAG_ALLOWED_HOSTS", ",".join(DEFAULT_HOSTS)),
                 allowed_origins=_csv("RAG_ALLOWED_ORIGINS"), uploads_root=DATA_DIR / "uploads")
