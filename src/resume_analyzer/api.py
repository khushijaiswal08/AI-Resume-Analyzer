"""FastAPI application: a static page plus JSON endpoints.

Endpoints: GET / (page), GET /static/* (page assets), GET /api/health, GET /api/roles,
GET /api/sample, POST /api/analyze. Every response gets security headers.
"""

import logging
from importlib import resources
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from resume_analyzer import __version__
from resume_analyzer.config import Settings, get_settings
from resume_analyzer.llm.base import LLMClient
from resume_analyzer.models import AnalysisResult, HealthResponse
from resume_analyzer.parsing import FileTooLargeError, ParseError
from resume_analyzer.ratelimit import RateLimiter, client_key
from resume_analyzer.roles import list_roles
from resume_analyzer.sample import SampleResponse, load_sample
from resume_analyzer.schemas import RoleInfo
from resume_analyzer.service import analyze_document, build_llm_client

logger = logging.getLogger(__name__)

_UNSET = object()
STATIC_DIR = Path(__file__).parent / "static"

# The page and its assets come from this origin only: no inline scripts, no third-party
# requests (this is also the privacy promise). Inline *styles* are allowed because the UI
# sets a few style attributes (gauge angle, bar widths); they cannot run code.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def create_app(settings: Settings | None = None, llm_client: LLMClient | None | object = _UNSET):
    """Build the app. Tests pass their own settings and a FakeLLM; production uses env vars."""
    settings = settings or get_settings()
    client = build_llm_client(settings) if llm_client is _UNSET else llm_client
    limiter = RateLimiter(settings.rate_limit_max, settings.rate_limit_window_seconds)

    app = FastAPI(
        title="AI Resume Analyzer",
        version=__version__,
        description="Deterministic resume scoring with a guarded LLM layer.",
        docs_url=None,  # the interactive docs load scripts from a CDN, which our CSP forbids
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.llm_client = client
    app.state.rate_limiter = limiter

    # CORS stays off unless CORS_ORIGINS is set: the page is served from the same origin.
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware, allow_origins=settings.cors_origin_list, allow_methods=["GET", "POST"]
        )

    @app.middleware("http")
    async def _security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")  # resumes are private
        return response

    @app.exception_handler(ParseError)
    async def _parse_error_handler(_: Request, exc: ParseError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index() -> str:
        return resources.files("resume_analyzer").joinpath("static/index.html").read_text("utf-8")

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", llm_configured=client is not None, version=__version__)

    @app.get("/api/roles", response_model=list[RoleInfo])
    def roles() -> list[RoleInfo]:
        return list_roles()

    @app.get("/api/sample", response_model=SampleResponse)
    def sample() -> SampleResponse:
        return load_sample()

    @app.post("/api/analyze", response_model=AnalysisResult)
    async def analyze(
        request: Request,
        resume: Annotated[UploadFile, File(description="Resume as PDF, DOCX or TXT")],
        job_description: Annotated[str | None, Form()] = None,
        role: Annotated[str | None, Form(description="Role id from GET /api/roles")] = None,
    ) -> AnalysisResult:
        key = client_key(
            request.client.host if request.client else None,
            request.headers.get("x-forwarded-for"),
            settings.trust_proxy,
        )
        retry_after = limiter.check(key)
        if retry_after is not None:
            raise HTTPException(
                status_code=429,
                detail=f"Too many analyses. Please try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )
        # Read at most one byte past the limit: enough to know the file is too big
        # without copying an arbitrarily large upload into memory.
        data = await resume.read(settings.max_upload_bytes + 1)
        await resume.close()
        if len(data) > settings.max_upload_bytes:
            raise FileTooLargeError(f"File is larger than the {settings.max_upload_mb:g} MB limit.")
        # Parsing and the LLM call are blocking, so run them off the event loop.
        return await run_in_threadpool(
            analyze_document,
            data,
            job_description,
            settings=settings,
            llm_client=client,
            role=role,
        )

    # Mounted last so it never shadows the routes above.
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
