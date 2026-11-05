"""FastAPI application: a static page plus two JSON endpoints."""

import logging
from importlib import resources
from typing import Annotated

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse

from resume_analyzer import __version__
from resume_analyzer.config import Settings, get_settings
from resume_analyzer.llm.base import LLMClient
from resume_analyzer.models import AnalysisResult, HealthResponse
from resume_analyzer.parsing import FileTooLargeError, ParseError
from resume_analyzer.service import analyze_document, build_llm_client

logger = logging.getLogger(__name__)

_UNSET = object()


def create_app(settings: Settings | None = None, llm_client: LLMClient | None | object = _UNSET):
    """Build the app. Tests pass their own settings and a FakeLLM; production uses env vars."""
    settings = settings or get_settings()
    client = build_llm_client(settings) if llm_client is _UNSET else llm_client

    app = FastAPI(
        title="AI Resume Analyzer",
        version=__version__,
        description="Deterministic resume scoring with a guarded LLM layer.",
    )
    app.state.settings = settings
    app.state.llm_client = client

    @app.exception_handler(ParseError)
    async def _parse_error_handler(_: Request, exc: ParseError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index() -> str:
        return resources.files("resume_analyzer").joinpath("static/index.html").read_text("utf-8")

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", llm_configured=client is not None)

    @app.post("/api/analyze", response_model=AnalysisResult)
    async def analyze(
        resume: Annotated[UploadFile, File(description="Resume as PDF, DOCX or TXT")],
        job_description: Annotated[str | None, Form()] = None,
    ) -> AnalysisResult:
        # Read at most one byte past the limit: enough to know the file is too big
        # without copying an arbitrarily large upload into memory.
        data = await resume.read(settings.max_upload_bytes + 1)
        await resume.close()
        if len(data) > settings.max_upload_bytes:
            raise FileTooLargeError(f"File is larger than the {settings.max_upload_mb:g} MB limit.")
        # Parsing and the LLM call are blocking, so run them off the event loop.
        return await run_in_threadpool(
            analyze_document, data, job_description, settings=settings, llm_client=client
        )

    return app


app = create_app()
