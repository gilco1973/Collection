"""/api/chat through the FastAPI test client (no network, no LLM: run_chat is monkeypatched)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kb_librarian.api.app import create_app
from kb_librarian.chat.runner import ChatAnswer
from kb_librarian.config import LibrarianSettings


@pytest.fixture
def client(kb_root: Path):
    app = create_app(kb_root, LibrarianSettings(), cors_origins=["http://localhost:5173"])
    return TestClient(app)


def test_chat_answers_and_carries_sources(client, monkeypatch):
    captured = {}

    async def fake_run_chat(settings, root, message, history, *, lang=None, query_fn=None, **_):
        captured.update(message=message, history=history, lang=lang)
        source = {"path": "onboarding/README.md", "title": "Onboarding"}
        return ChatAnswer(answer="Start with the AI policy.", sources=[source])

    monkeypatch.setattr("kb_librarian.api.routes_chat.run_chat", fake_run_chat)
    body = {"message": "how do I get started?", "history": [{"role": "user", "content": "hi"}], "lang": "es"}
    response = client.post("/api/chat", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Start with the AI policy."
    assert data["sources"] == [{"path": "onboarding/README.md", "title": "Onboarding"}]
    assert captured["message"] == "how do I get started?" and captured["lang"] == "es"
    assert captured["history"][0].role == "user" and captured["history"][0].content == "hi"


def test_chat_reports_a_librarian_error_as_502(client, monkeypatch):
    async def fake_run_chat(settings, root, message, history, *, lang=None, query_fn=None, **_):
        return ChatAnswer(error="agent result error: boom")

    monkeypatch.setattr("kb_librarian.api.routes_chat.run_chat", fake_run_chat)
    response = client.post("/api/chat", json={"message": "hi"})
    assert response.status_code == 502 and "boom" in response.json()["error"]["message"]


def test_chat_validates_the_body(client):
    bad_role = {"message": "hi", "history": [{"role": "bot", "content": "x"}]}
    too_long = {"message": "hi", "history": [{"role": "user", "content": "x"} for _ in range(17)]}
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
    assert client.post("/api/chat", json={"message": "x" * 2001}).status_code == 422
    assert client.post("/api/chat", json=bad_role).status_code == 422
    assert client.post("/api/chat", json=too_long).status_code == 422


def test_chat_throttles_a_client_after_ten_messages_in_a_minute(client, monkeypatch):
    from collections import defaultdict, deque

    async def fake_run_chat(settings, root, message, history, *, lang=None, query_fn=None, **_):
        return ChatAnswer(answer="ok")

    monkeypatch.setattr("kb_librarian.api.routes_chat.run_chat", fake_run_chat)
    monkeypatch.setattr("kb_librarian.api.routes_chat._recent", defaultdict(deque))  # a clean bucket for this test
    for _ in range(10):
        assert client.post("/api/chat", json={"message": "hi"}).status_code == 200
    eleventh = client.post("/api/chat", json={"message": "hi"})
    assert eleventh.status_code == 429 and "too many chat messages" in eleventh.json()["error"]["message"]
