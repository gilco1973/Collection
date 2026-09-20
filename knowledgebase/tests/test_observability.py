"""Request ids, the access log line and structured logging (kb_librarian/api/observability.py)."""

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kb_librarian.api.app import create_app
from kb_librarian.api.observability import (
    ACCESS_LOGGER,
    JsonFormatter,
    TextFormatter,
    configure_logging,
    request_id_for,
)
from kb_librarian.config import LibrarianSettings


@pytest.fixture
def client(kb_root: Path) -> TestClient:
    return TestClient(create_app(kb_root, LibrarianSettings()), raise_server_exceptions=False)


def test_request_id_is_accepted_only_when_well_formed():
    assert request_id_for("abc-123.X_y") == "abc-123.X_y"
    assert request_id_for(b"from-bytes") == "from-bytes"
    assert request_id_for("a" * 64) == "a" * 64
    for bad in (
        None,
        "",
        "a" * 65,
        "has space",
        "semi;colon",
        "tab\tx",
        "ünïcode",
        "<script>",
        "a/b",
        "abc\n",
        "abc\r\n",
    ):
        generated = request_id_for(bad)
        assert generated != bad and len(generated) == 16 and generated.isalnum()
    assert request_id_for(None) != request_id_for(None)


def test_client_request_id_is_echoed_and_a_bad_one_is_replaced(client):
    good = client.get("/api/health", headers={"X-Request-ID": "trace-42"})
    assert good.headers["x-request-id"] == "trace-42"
    bad = client.get("/api/health", headers={"X-Request-ID": "not valid!"})
    echoed = bad.headers["x-request-id"]
    assert echoed != "not valid!" and len(echoed) == 16 and echoed.isalnum()
    assert len(client.get("/api/health").headers["x-request-id"]) == 16


def test_error_envelope_carries_the_request_id(client):
    response = client.get("/api/pages/nope.md", headers={"X-Request-ID": "trace-404"})
    assert response.status_code == 404
    assert response.json()["error"]["request_id"] == "trace-404" and response.headers["x-request-id"] == "trace-404"
    headers = {"X-Request-ID": "trace-413", "content-type": "application/json"}
    huge = client.post("/api/chat", content=b"x" * (64 * 1024 + 1), headers=headers)
    assert huge.status_code == 413 and huge.json()["error"]["request_id"] == "trace-413"
    assert huge.headers["x-request-id"] == "trace-413"


def test_unhandled_error_keeps_the_request_id_and_is_logged(kb_root: Path, caplog):
    app = create_app(kb_root, LibrarianSettings())

    @app.get("/api/boom")
    def boom():
        raise RuntimeError("secret detail")

    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.INFO, logger=ACCESS_LOGGER):
        response = client.get("/api/boom", headers={"X-Request-ID": "trace-500"})
    assert response.status_code == 500
    body = response.json()["error"]
    assert body == {"code": "internal_error", "message": "internal error", "request_id": "trace-500"}
    assert response.headers["x-request-id"] == "trace-500"
    record = next(r for r in caplog.records if r.name == ACCESS_LOGGER)
    assert record.status == 500 and record.request_id == "trace-500"


def test_access_log_line_has_the_agreed_fields_and_no_query_string(client, caplog):
    with caplog.at_level(logging.INFO, logger=ACCESS_LOGGER):
        client.get("/api/health?token=do-not-log", headers={"X-Request-ID": "trace-log", "Cookie": "kb_session=nope"})
    records = [r for r in caplog.records if r.name == ACCESS_LOGGER]
    assert len(records) == 1
    record = records[0]
    assert (record.method, record.path, record.status, record.request_id) == ("GET", "/api/health", 200, "trace-log")
    assert isinstance(record.duration_ms, float) and record.client == "testclient"
    line = JsonFormatter().format(record)
    data = json.loads(line)
    agreed = {"ts", "level", "logger", "msg", "method", "path", "status", "duration_ms", "request_id", "client"}
    assert agreed <= set(data) and data["logger"] == ACCESS_LOGGER and data["level"] == "INFO"
    assert "do-not-log" not in line and "kb_session" not in line and "nope" not in line


@pytest.fixture
def _root_logger_restored():
    root = logging.getLogger()
    level, handlers, formatters = root.level, list(root.handlers), [h.formatter for h in root.handlers]
    yield
    root.setLevel(level)
    root.handlers[:] = handlers
    for handler, formatter in zip(handlers, formatters, strict=True):
        handler.setFormatter(formatter)


def test_text_format_cannot_be_forged_through_the_request_path(kb_root: Path):
    record = logging.LogRecord(ACCESS_LOGGER, logging.INFO, __file__, 1, "GET %s 404", ("/x\nFORGED ERROR line",), None)
    record.path = "/x\nFORGED ERROR line\r"
    text = TextFormatter().format(record)
    assert "\n" not in text and "\r" not in text and "FORGED" in text
    assert JsonFormatter().format(record).count("\n") == 0


def test_configure_logging_is_idempotent_and_honours_format_and_level(_root_logger_restored):
    root = logging.getLogger()
    first = configure_logging(LibrarianSettings(log_level="debug", log_format="json"))
    assert root.handlers.count(first) == 1 and root.level == logging.DEBUG
    second = configure_logging(LibrarianSettings(log_level="WARNING", log_format="text"))
    assert second is first and root.handlers.count(first) == 1 and root.level == logging.WARNING
    assert isinstance(first.formatter, TextFormatter)
    third = configure_logging(LibrarianSettings())  # back to the defaults for the other tests
    assert third is first and isinstance(first.formatter, JsonFormatter) and root.level == logging.INFO


def test_json_and_text_formatters_carry_message_extras_and_exceptions():
    record = logging.LogRecord("kb_librarian.test", logging.WARNING, __file__, 1, "hello %s", ("world",), None)
    record.request_id = "r1"
    data = json.loads(JsonFormatter().format(record))
    assert data["msg"] == "hello world" and data["level"] == "WARNING" and data["logger"] == "kb_librarian.test"
    assert data["request_id"] == "r1" and data["ts"].endswith("Z") and "exc" not in data
    text = TextFormatter().format(record)
    assert "WARNING kb_librarian.test hello world" in text and text.endswith("request_id=r1")
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        failing = logging.LogRecord("x", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())
    assert "ValueError: boom" in json.loads(JsonFormatter().format(failing))["exc"]
