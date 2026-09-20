"""Operational plumbing shared by the API and the CLI: structured logging, request ids, the access
log line and the state-directory probe that readiness and ``doctor`` both use.

Nothing here copies a header value, a cookie, a bearer token or a query string into a log line:
the access record carries the method, the path, the status, the duration, the request id and the
client address, and a request id is taken from the caller only when it is short, plain ASCII.
"""

import json
import logging
import re
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from kb_librarian.config import LibrarianSettings

ACCESS_LOGGER = "kb_librarian.api.access"
REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_RECORD_FIELDS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
MAX_LOGGED_PATH = 512


def clean(text: str) -> str:
    """A request-supplied string as one printable line: control characters (a newline would forge a log
    line in text format) become ``?`` and the length is bounded."""
    return _CONTROL.sub("?", text)[:MAX_LOGGED_PATH]


def request_id_for(supplied: str | bytes | None) -> str:
    """The caller's id when it is well-formed (so a trace joins across a proxy), otherwise a fresh one."""
    if isinstance(supplied, bytes):
        supplied = supplied.decode("latin-1")
    if supplied and _REQUEST_ID.fullmatch(supplied):  # fullmatch: `$` alone would admit a trailing newline
        return supplied
    return uuid.uuid4().hex[:16]


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    """What the call passed as ``extra=``: everything on the record that is not a standard field."""
    return {
        k: v
        for k, v in record.__dict__.items()
        if k not in _RECORD_FIELDS and not k.startswith("_") and k != "color_message"  # uvicorn's ANSI duplicate
    }


class JsonFormatter(logging.Formatter):
    """One JSON object per line: ``ts, level, logger, msg`` plus the record's extras (and ``exc``)."""

    def format(self, record: logging.LogRecord) -> str:
        stamp = datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds")
        payload: dict[str, Any] = {
            "ts": stamp.replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update(_extras(record))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    """The same record as one readable line, extras appended as ``key=value``."""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        extras = " ".join(f"{k}={v}" for k, v in _extras(record).items())
        return (
            clean(f"{line} {extras}" if extras else line)
            if record.exc_info is None
            else (f"{line} {extras}" if extras else line)
        )


def configure_logging(settings: LibrarianSettings) -> logging.Handler:
    """Configure the root logger from ``KB_LOG_LEVEL`` / ``KB_LOG_FORMAT``. Idempotent: a second call
    re-targets the same handler instead of adding one, so the API factory and the CLI can both call it."""
    root = logging.getLogger()
    handler = next((h for h in root.handlers if getattr(h, "kb_librarian", False)), None)
    if handler is None:
        handler = logging.StreamHandler()
        handler.kb_librarian = True  # type: ignore[attr-defined]  # the marker that makes this idempotent
        root.addHandler(handler)
    handler.setFormatter(JsonFormatter() if settings.log_format == "json" else TextFormatter())
    root.setLevel(settings.log_level)
    return handler


def probe_writable(directory: Path) -> bool:
    """Whether this process can create (and remove) a file in ``directory``, creating it when absent."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".probe-", suffix=".tmp"):
            pass
    except OSError:
        return False
    return True


class RequestLog:
    """Pure ASGI: assigns or validates the request id, stores it on ``request.state``, echoes it on the
    response and writes one access line per request — including rejections and failures."""

    def __init__(self, app: ASGIApp, prefix: str = "") -> None:
        self.app, self.prefix = app, prefix
        self.log = logging.getLogger(ACCESS_LOGGER)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self.prefix):
            await self.app(scope, receive, send)
            return
        header = REQUEST_ID_HEADER.lower().encode("latin-1")
        request_id = request_id_for(dict(scope["headers"]).get(header))
        path = clean(scope["path"])  # the only request-supplied text that reaches a log line
        scope.setdefault("state", {})["request_id"] = request_id
        status, started = 500, time.perf_counter()

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != header]
                headers.append((header, request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            client = scope.get("client")
            fields = {
                "method": scope["method"],
                "path": path,
                "status": status,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "request_id": request_id,
                "client": client[0] if client else None,
            }
            self.log.info("%s %s %s", scope["method"], path, status, extra=fields)
