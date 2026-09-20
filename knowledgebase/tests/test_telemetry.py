"""kb_librarian/chat/telemetry.py and the one call POST /api/chat makes after every turn.

A line holds exactly the agreed keys and never the question, the answer, the client or the reader.
"""

import json
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kb_librarian.api.app import create_app
from kb_librarian.chat import telemetry
from kb_librarian.chat.runner import ChatAnswer
from kb_librarian.config import LibrarianSettings
from tests.fake_idp import FakeIdp
from tests.test_auth_routes import _finish_login, _settings, _start_login

KEYS = ["ts", "mode", "lang", "persona", "sources", "refused", "cost_usd", "duration_ms"]
QUESTION = "how do I rotate the signing key for the payments gateway?"
ANSWER = "Rotate it from the operator console; never by hand."
SOURCE = {"path": "onboarding/README.md", "title": "Onboarding"}


def _lines(root: Path) -> list[dict]:
    return [json.loads(line) for line in telemetry.log_path(root).read_text(encoding="utf-8").splitlines()]


def _record(root: Path, **over) -> None:
    line = dict(mode="ask", lang=None, persona=None, sources=[], refused=True, cost_usd=None, duration_ms=1)
    telemetry.record(root, **{**line, **over})


def test_record_appends_exactly_the_agreed_keys_and_nothing_else(kb_root: Path):
    _record(kb_root, lang="es", persona="engineer", sources=["a.md", "b.md"], refused=False, cost_usd=0.01)
    _record(kb_root, mode="quiz", duration_ms=5)
    lines = _lines(kb_root)
    assert [list(line) for line in lines] == [KEYS, KEYS]
    assert lines[0]["sources"] == ["a.md", "b.md"] and lines[0]["refused"] is False
    assert lines[0]["persona"] == "engineer" and lines[0]["lang"] == "es" and lines[0]["duration_ms"] == 1
    assert lines[1] == {**lines[1], "mode": "quiz", "lang": None, "persona": None, "sources": [], "refused": True}
    assert lines[1]["cost_usd"] is None and lines[1]["duration_ms"] == 5
    assert datetime.fromisoformat(lines[0]["ts"]).tzinfo is not None


def test_read_skips_malformed_lines_and_applies_since(kb_root: Path):
    now = datetime.now(UTC)
    _record(kb_root, sources=["a.md"], refused=False, cost_usd=0.0)
    path = telemetry.log_path(kb_root)
    old = {**json.loads(path.read_text().splitlines()[0]), "ts": (now - timedelta(days=40)).isoformat()}
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
        handle.write("[1, 2]\n")
        handle.write(json.dumps({"mode": "ask"}) + "\n")  # no timestamp
        handle.write(json.dumps({**old, "ts": "yesterday"}) + "\n")  # unparseable timestamp
        handle.write(json.dumps(old) + "\n")
    assert len(list(telemetry.read(kb_root, now - timedelta(days=90)))) == 2
    assert [line["sources"] for line in telemetry.read(kb_root, now - timedelta(days=1))] == [["a.md"]]
    assert list(telemetry.read(kb_root / "elsewhere", now)) == []  # no log at all


def test_prune_rewrites_the_file_without_old_or_malformed_lines(kb_root: Path):
    now = datetime.now(UTC)
    _record(kb_root)
    path = telemetry.log_path(kb_root)
    fresh = path.read_text(encoding="utf-8")
    old = {**json.loads(fresh), "ts": (now - timedelta(days=91)).isoformat()}
    path.write_text(json.dumps(old) + "\n" + "garbage\n" + fresh, encoding="utf-8")
    assert telemetry.prune(kb_root, 90) == 2
    assert path.read_text(encoding="utf-8") == fresh
    assert telemetry.prune(kb_root, 90) == 0
    assert telemetry.prune(kb_root / "elsewhere", 90) == 0
    assert not list((kb_root / ".librarian").glob("*.tmp"))  # the rewrite leaves no temp file behind


@pytest.fixture
def client(kb_root: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr("kb_librarian.api.routes_chat._recent", defaultdict(deque))
    return TestClient(create_app(kb_root, LibrarianSettings()))


def _fake(monkeypatch, answer: ChatAnswer) -> None:
    async def fake_run_chat(settings, root, message, history, **_):
        return answer

    monkeypatch.setattr("kb_librarian.api.routes_chat.run_chat", fake_run_chat)


def test_route_records_a_successful_turn_without_the_message_or_answer(client: TestClient, kb_root: Path, monkeypatch):
    _fake(monkeypatch, ChatAnswer(answer=ANSWER, sources=[SOURCE], cost_usd=0.02))
    context = {"path": "onboarding/README.md", "selection": "the gateway"}
    body = {"message": QUESTION, "lang": "es", "context": context, "mode": "explain"}
    assert client.post("/api/chat", json=body).status_code == 200
    text = telemetry.log_path(kb_root).read_text(encoding="utf-8")
    assert QUESTION not in text and ANSWER not in text and "gateway" not in text and "testclient" not in text
    (line,) = _lines(kb_root)
    assert list(line) == KEYS
    assert line["mode"] == "explain" and line["lang"] == "es" and line["persona"] is None
    assert line["sources"] == ["onboarding/README.md"] and line["refused"] is False and line["cost_usd"] == 0.02
    assert isinstance(line["duration_ms"], int) and line["duration_ms"] >= 0


def test_route_records_a_refusal_and_a_502_alike(client: TestClient, kb_root: Path, monkeypatch):
    _fake(monkeypatch, ChatAnswer(answer="I cannot find that in the knowledge base."))
    assert client.post("/api/chat", json={"message": QUESTION}).status_code == 200
    _fake(monkeypatch, ChatAnswer(error="agent result error: boom", cost_usd=0.01))
    assert client.post("/api/chat", json={"message": QUESTION}).status_code == 502
    refused, errored = _lines(kb_root)
    assert refused["refused"] is True and refused["sources"] == [] and refused["mode"] == "ask"
    assert errored["refused"] is False and errored["sources"] == [] and errored["cost_usd"] == 0.01
    assert QUESTION not in telemetry.log_path(kb_root).read_text(encoding="utf-8") and "boom" not in json.dumps(errored)


def test_a_telemetry_failure_never_fails_the_request(client: TestClient, kb_root: Path, monkeypatch, caplog):
    _fake(monkeypatch, ChatAnswer(answer="ok"))

    def boom(*_, **__):
        raise OSError("disk full")

    monkeypatch.setattr("kb_librarian.api.routes_chat.telemetry.record", boom)
    with caplog.at_level("WARNING"):
        assert client.post("/api/chat", json={"message": "hi"}).status_code == 200
    assert any("telemetry" in record.getMessage() for record in caplog.records)


def test_route_takes_the_persona_from_the_signed_in_reader(kb_root: Path, monkeypatch):
    monkeypatch.setattr("kb_librarian.api.routes_chat._recent", defaultdict(deque))
    app = create_app(kb_root, _settings())
    app.state.kb.oidc_transport = FakeIdp().transport()
    client = TestClient(app, base_url="https://testserver", follow_redirects=False)
    assert _finish_login(client, _start_login(client)).status_code == 302
    assert client.put("/api/profile/persona", json={"persona": "engineer"}).status_code == 200
    _fake(monkeypatch, ChatAnswer(answer="ok", sources=[SOURCE]))
    assert client.post("/api/chat", json={"message": QUESTION}).status_code == 200
    (line,) = _lines(kb_root)
    text = telemetry.log_path(kb_root).read_text(encoding="utf-8")
    assert line["persona"] == "engineer"
    assert "u-123" not in text and "Ada" not in text and "ada@example.com" not in text  # never the reader


def test_the_route_bounds_the_language_tag_before_it_reaches_the_log(client, kb_root: Path):
    """``lang`` is request-supplied: a long or odd value is refused by the API (422), so the telemetry
    line only ever carries a short language tag."""
    long = client.post("/api/chat", json={"message": "hi", "lang": "x" * 9})
    assert long.status_code == 422
    assert not (kb_root / ".librarian" / "chat-log.jsonl").exists()
