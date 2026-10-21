from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import CopilotError, Settings
from .service import Copilot

STATIC = Path(__file__).parent / "static"


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    generate: bool = True
    mode: Literal["keyword", "vector", "hybrid"] = "hybrid"


class Feedback(BaseModel):
    helpful: bool


def create_app(settings: Settings, copilot=None):
    service = copilot or Copilot(settings)
    generation = Lock()

    @asynccontextmanager
    async def lifespan(app):
        yield
        service.close()

    app = FastAPI(
        title="OriginChainDB Support Copilot",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        if request.method == "POST":
            origin = request.headers.get("origin")
            if request.headers.get("x-copilot-request") != "1" or (
                origin and urlsplit(origin).netloc != request.headers.get("host")
            ):
                return JSONResponse({"error": "Use the local copilot interface."}, status_code=403)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(CopilotError)
    async def error_handler(request, error):
        return JSONResponse({"error": str(error)}, status_code=503)

    @app.get("/", response_class=HTMLResponse)
    def home():
        return (STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/api/status")
    def status():
        manifest = service.read_manifest()
        return {
            key: manifest[key]
            for key in ("chunk_count", "document_count", "embedding_model", "snapshot")
        }

    @app.post("/api/ask")
    def ask(question: Question):
        if not question.generate:
            return service.ask(question.question, generate=False, mode=question.mode)
        if not generation.acquire(blocking=False):
            return JSONResponse(
                {"error": "An answer is being drafted. Try again shortly."},
                status_code=429,
                headers={"Retry-After": "5"},
            )
        try:
            return service.ask(question.question, mode=question.mode)
        finally:
            generation.release()

    @app.get("/api/documents")
    def documents():
        return service.documents()

    @app.get("/api/recent")
    def recent():
        return service.recent()

    @app.get("/api/settings")
    def configured_settings():
        return service.public_settings()

    @app.get("/healthz")
    def health():
        return {"status": "ok"}  # Process liveness, not dependency readiness.

    @app.get("/api/queue")
    def queue():
        return service.queue()

    @app.post("/api/feedback/{event_id}")
    def feedback(event_id: str, data: Feedback):
        return service.feedback(event_id, data.helpful)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
