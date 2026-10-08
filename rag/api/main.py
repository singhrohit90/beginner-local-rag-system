"""The HTTP API and the page that uses it. Routes only: the work is in service.py.

    uvicorn rag.api.main:app --port 8000        then open http://127.0.0.1:8000

Endpoints
    POST   /documents              upload a PDF, ingestion runs in the background
    GET    /documents              list documents with their status
    GET    /documents/{id}         one document's status (queued, processing, ready, failed)
    POST   /documents/{id}/ask     {"question": "..."} -> answer, passages, trace stages
    DELETE /documents/{id}
    GET    /health
"""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from rag.api.service import BadUpload, DocumentService, NotFound
from rag.ingestion.chunk import STRATEGIES
from rag.query.configs import CONFIGS

STATIC = Path(__file__).parent / "static"
# The service has no reranker loaded, so only the configs that do not need one are offered.
USABLE_CONFIGS = sorted(name for name, c in CONFIGS.items() if not c.rerank)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    config: str = "weighted"
    style: str = "standard"


def build_default_service() -> DocumentService:
    """Real models, chosen by .env: RAG_LLM, RAG_EMBEDDER. Heavy, so only built when serving."""
    from rag.common.config import DATA_DIR, RUNS_DIR
    from rag.common.embed import get_embedder
    from rag.common.llm import get_llm
    from rag.common.secrets import setting

    spec = setting("RAG_EMBEDDER", "st:sentence-transformers/all-mpnet-base-v2")
    return DocumentService(
        root=DATA_DIR / "uploads",
        embedder=get_embedder(spec),
        embedder_spec=spec,
        llm=get_llm(setting("RAG_LLM", "vllm:/models/gpt-oss-20b")),
        traces_dir=RUNS_DIR / "chat",
    )


def create_app(service: Optional[DocumentService] = None,
               service_factory: Callable[[], DocumentService] = build_default_service) -> FastAPI:
    app = FastAPI(title="RAG document chat")
    state: Dict[str, Optional[DocumentService]] = {"service": service}

    def svc() -> DocumentService:
        if state["service"] is None:  # load the models on first use, not at import
            state["service"] = service_factory()
        return state["service"]

    @app.get("/")
    def page() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/health")
    def health() -> Dict[str, Any]:
        return {"ok": True, "chunkers": list(STRATEGIES), "configs": USABLE_CONFIGS}

    @app.post("/documents", status_code=202)
    async def upload(background: BackgroundTasks, file: UploadFile = File(...),
                     chunker: str = Form("recursive")) -> Dict[str, Any]:
        if chunker not in STRATEGIES:
            raise HTTPException(422, f"chunker must be one of {list(STRATEGIES)}")
        service = svc()
        data = await file.read(service.max_upload_bytes + 1)
        try:
            status = service.create(file.filename or "document.pdf", data, chunker)
        except BadUpload as err:
            raise HTTPException(400, str(err))
        background.add_task(service.run_ingestion, status["id"])
        return status

    @app.get("/documents")
    def list_documents() -> List[Dict[str, Any]]:
        return svc().list()

    @app.get("/documents/{doc_id}")
    def get_document(doc_id: str) -> Dict[str, Any]:
        try:
            return svc().get(doc_id)
        except NotFound:
            raise HTTPException(404, "no such document")

    @app.delete("/documents/{doc_id}", status_code=204)
    def delete_document(doc_id: str) -> None:
        try:
            svc().delete(doc_id)
        except NotFound:
            raise HTTPException(404, "no such document")

    @app.post("/documents/{doc_id}/ask")
    def ask(doc_id: str, request: AskRequest) -> Dict[str, Any]:
        if request.config not in USABLE_CONFIGS:
            raise HTTPException(422, f"config must be one of {USABLE_CONFIGS}")
        if request.style not in ("standard", "spotlight"):
            raise HTTPException(422, "style must be standard or spotlight")
        try:
            return svc().ask(doc_id, request.question, request.config, request.style)
        except NotFound:
            raise HTTPException(404, "no such document")
        except BadUpload as err:
            raise HTTPException(409, str(err))
        except Exception as err:  # most often the model server being unreachable
            raise HTTPException(502, f"{type(err).__name__}: {err}")

    return app


app = create_app()
