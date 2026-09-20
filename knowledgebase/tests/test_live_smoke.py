"""scripts/live-smoke.py against a fake ``urlopen`` (no server, no model)."""

import importlib.util
import io
import json
import urllib.error
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "live-smoke.py"
HEALTHY = {"status": "ok", "version": "0.1.0", "checks": {"process": True}}
READY = {"status": "ok", "version": "0.1.0", "checks": {"catalog": True, "state_writable": True}}
ANSWERED = {"answer": "It documents the AI platform.", "sources": []}


@pytest.fixture
def smoke():
    spec = importlib.util.spec_from_file_location("live_smoke", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, status: int, body) -> None:
        self.status, self._body = status, json.dumps(body).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _server(routes: dict, monkeypatch, smoke) -> list:
    """``routes``: {(method, path): (status, body)}; returns the list of requests seen."""
    seen = []

    def urlopen(request, timeout=0):
        path = "/" + request.full_url.split("://", 1)[1].split("/", 1)[1]
        seen.append((request.get_method(), path, request.data, dict(request.header_items())))
        status, body = routes[(request.get_method(), path)]
        if status >= 400:
            raise urllib.error.HTTPError(request.full_url, status, "error", {}, io.BytesIO(json.dumps(body).encode()))
        return FakeResponse(status, body)

    monkeypatch.setattr(smoke, "urlopen", urlopen)
    return seen


def test_all_checks_pass_and_main_exits_zero(smoke, monkeypatch, capsys):
    routes = {
        ("GET", "/api/health"): (200, HEALTHY),
        ("GET", "/api/health/ready"): (200, READY),
        ("POST", "/api/chat"): (200, ANSWERED),
    }
    seen = _server(routes, monkeypatch, smoke)
    assert smoke.main(["--base", "http://kb.test/", "--question", "What is this?"]) == 0
    assert capsys.readouterr().out.splitlines() == ["PASS health", "PASS ready", "PASS chat"]
    method, path, data, headers = seen[2]
    assert (method, path, json.loads(data)) == ("POST", "/api/chat", {"message": "What is this?"})
    assert headers["Content-type"] == "application/json" and headers["X-request-id"].startswith("live-smoke-")


def test_failures_are_reported_per_check_and_main_exits_one(smoke, monkeypatch, capsys):
    not_ready = {"status": "not_ready", "checks": {"catalog": True, "state_writable": False}}
    routes = {
        ("GET", "/api/health"): (200, HEALTHY),
        ("GET", "/api/health/ready"): (503, not_ready),
        ("POST", "/api/chat"): (429, {"error": {"code": "http_error", "message": "spent", "request_id": "x"}}),
    }
    _server(routes, monkeypatch, smoke)
    assert smoke.main([]) == 1
    assert capsys.readouterr().out.splitlines() == ["PASS health", "FAIL ready", "FAIL chat"]


def test_an_unreachable_server_fails_every_check(smoke, monkeypatch, capsys):
    def refuse(request, timeout=0):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(smoke, "urlopen", refuse)
    assert smoke.main(["--base", "http://127.0.0.1:1"]) == 1
    out, err = capsys.readouterr()
    assert out.splitlines() == ["FAIL health", "FAIL ready", "FAIL chat"] and "URLError" in err


def test_check_functions_judge_the_body_not_only_the_status(smoke, monkeypatch):
    routes = {
        ("GET", "/api/health"): (200, {"status": "degraded"}),
        ("GET", "/api/health/ready"): (200, {"status": "ok", "checks": {}}),
        ("POST", "/api/chat"): (200, {"answer": "   ", "sources": []}),
    }
    _server(routes, monkeypatch, smoke)
    assert smoke.check_health("http://kb.test") is False
    assert smoke.check_ready("http://kb.test") is False
    assert smoke.check_chat("http://kb.test", "q") is False
    routes[("GET", "/api/health")] = (200, "not an object")
    assert smoke.check_health("http://kb.test") is False
    assert smoke.DEFAULT_BASE == "http://127.0.0.1:8765"
