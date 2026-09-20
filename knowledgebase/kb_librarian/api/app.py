"""FastAPI application factory. Platforms mount ``router`` under their own app; ``main`` serves it alone."""

import logging
import os
from importlib import metadata
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from kb_librarian.api.deps import AppState, build_state, get_state
from kb_librarian.api.middleware import BodyCap, SecurityHeaders
from kb_librarian.api.observability import (
    REQUEST_ID_HEADER,
    RequestLog,
    configure_logging,
    probe_writable,
    request_id_for,
)
from kb_librarian.api.routes_audits import router as audits_router
from kb_librarian.api.routes_auth import router as auth_router
from kb_librarian.api.routes_chat import router as chat_router
from kb_librarian.api.routes_insights import router as insights_router
from kb_librarian.api.routes_pages import router as pages_router
from kb_librarian.api.routes_profile import router as profile_router
from kb_librarian.config import LibrarianSettings
from kb_librarian.kbconfig import find_kb_root

log = logging.getLogger(__name__)
STATE_DIR = ".librarian"
router = APIRouter()
router.include_router(pages_router)
router.include_router(audits_router)
router.include_router(chat_router)
router.include_router(auth_router)
router.include_router(profile_router)
router.include_router(insights_router)


def package_version() -> str:
    """The installed distribution's version; the source tree's when the package is not installed."""
    try:
        return metadata.version("kb-librarian")
    except metadata.PackageNotFoundError:
        return "0.1.0"


@router.get("/health")
def health() -> dict:
    """Liveness: the process answers. No disk, no dependencies — it never fails while the process is up."""
    return {"status": "ok", "version": package_version(), "checks": {"process": True}}


def readiness_checks(state: AppState) -> dict[str, bool]:
    """Booleans only: nothing here may hand a path, a hostname or a secret to an unauthenticated caller."""
    try:
        state.catalog()
        catalog = True
    except Exception:  # any failure to load is "not ready"; the reason goes to the log, never the response
        log.exception("readiness: the catalog does not load")
        catalog = False
    return {"catalog": catalog, "state_writable": probe_writable(state.root / STATE_DIR)}


@router.get("/health/ready")
def ready(state: AppState = Depends(get_state)) -> JSONResponse:
    """Readiness: the catalog loads and ``.librarian/`` takes a file; 503 otherwise so a probe stops routing."""
    checks = readiness_checks(state)
    ok = all(checks.values())
    body = {"status": "ok" if ok else "not_ready", "version": package_version(), "checks": checks}
    return JSONResponse(body, status_code=200 if ok else 503)


def _error(request: Request, code: str, message: str, status_code: int) -> JSONResponse:
    """The envelope. Its ``request_id`` is the one ``RequestLog`` assigned (on a mount without it: the
    caller's well-formed id or a fresh one) and is echoed in the response header as well."""
    request_id = getattr(request.state, "request_id", None) or request_id_for(request.headers.get(REQUEST_ID_HEADER))
    return JSONResponse(
        {"error": {"code": code, "message": message, "request_id": request_id}},
        status_code=status_code,
        headers={REQUEST_ID_HEADER: request_id},
    )


def install_error_handlers(app: FastAPI) -> None:
    """The ``{error: {code, message, request_id}}`` envelope; call this on any app that mounts ``router``."""

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return _error(request, "http_error", str(exc.detail), exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        where = ".".join(str(part) for part in first.get("loc", []) if part != "body")
        message = (
            f"{where}: {first.get('msg', 'invalid request')}" if where else str(first.get("msg", "invalid request"))
        )
        return _error(request, "validation_error", message, 422)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        return _error(request, "internal_error", "internal error", 500)


def install_security_headers(app: FastAPI, prefix: str = "") -> None:
    """Body cap, ``no-store`` on the API, nosniff/frame/referrer headers, the console CSP and — outermost,
    so rejections and error responses are covered too — the request id and access line (``RequestLog``).

    On a platform mount pass the mount ``prefix`` so the host application's own routes are untouched,
    and call this after any middleware of the host that reads request bodies.
    """
    app.add_middleware(BodyCap, on_reject=_error, prefix=prefix)  # innermost: rejects before the app reads
    app.add_middleware(SecurityHeaders, prefix=prefix)
    app.add_middleware(RequestLog, prefix=prefix)


def create_app(
    root: Path | None = None, settings: LibrarianSettings | None = None, cors_origins: list[str] | None = None
) -> FastAPI:
    app = FastAPI(
        title="KnowledgeBase Librarian API", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json"
    )
    app.state.kb = build_state((root or find_kb_root()).resolve(), settings)
    configure_logging(app.state.kb.settings)
    if cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=cors_origins, allow_methods=["*"], allow_headers=["*"])
    install_security_headers(app)
    app.include_router(router, prefix="/api")
    install_error_handlers(app)
    return app


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    origins = [o for o in os.environ.get("KB_API_CORS_ORIGINS", "").split(",") if o]
    uvicorn.run(
        create_app(cors_origins=origins),
        host=os.environ.get("KB_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("KB_API_PORT", "8765")),
        log_config=None,  # uvicorn's own lines go through the root logger create_app configured
        access_log=False,  # RequestLog writes the one access line per request
    )
