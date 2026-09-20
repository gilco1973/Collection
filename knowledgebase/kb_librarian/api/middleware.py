"""Security middleware: a body cap that counts received bytes, and response hardening headers."""

from collections.abc import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

MAX_BODY_BYTES = 64 * 1024
CSP = "default-src 'self'; frame-ancestors 'none'; img-src 'self' data:; base-uri 'none'; form-action 'self'"
Rejecter = Callable[[Request, str, str, int], JSONResponse]


class BodyTooLarge(HTTPException):
    """Raised from ``receive``; an HTTPException so FastAPI's body parser re-raises it instead of a 400."""

    def __init__(self) -> None:
        super().__init__(status_code=413, detail="request body too large")


class BodyCap:
    """Refuse bodies over the cap before the app parses them, counting chunked bodies as they arrive."""

    def __init__(self, app: ASGIApp, on_reject: Rejecter, prefix: str = "") -> None:
        self.app = app
        self.on_reject = on_reject
        self.prefix = prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self.prefix):
            await self.app(scope, receive, send)
            return
        length = dict(scope["headers"]).get(b"content-length", b"")
        if length.isdigit() and int(length) > MAX_BODY_BYTES:
            await self._reject(scope, receive, send)
            return
        received = 0

        async def counted() -> dict:
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > MAX_BODY_BYTES:
                raise BodyTooLarge()
            return message

        try:
            await self.app(scope, counted, send)
        except BodyTooLarge:
            await self._reject(scope, receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = self.on_reject(Request(scope), "payload_too_large", "request body too large", 413)
        await response(scope, receive, send)


class SecurityHeaders(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, prefix: str = "") -> None:
        super().__init__(app)
        self.prefix = prefix

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith(self.prefix):
            return response  # a host application's own routes keep their own headers
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path.startswith("/api") or "/api/" in request.url.path:
            response.headers["Cache-Control"] = "no-store"
        elif "text/html" in response.headers.get("content-type", ""):
            response.headers.setdefault("Content-Security-Policy", CSP)
        return response
