"""POST /api/chat under the daily chat ceiling (KB_CHAT_DAILY_BUDGET_USD + kb_librarian/chat/spend.py)."""

import json
from collections import defaultdict, deque
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kb_librarian.api.app import create_app
from kb_librarian.chat.runner import ChatAnswer
from kb_librarian.chat.spend import SPEND_FILE, ledger_for
from kb_librarian.config import LibrarianSettings

SPENT = "the librarian's daily chat budget is spent; try again tomorrow"


@pytest.fixture
def client(kb_root: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr("kb_librarian.api.routes_chat._recent", defaultdict(deque))  # a clean throttle bucket
    return TestClient(create_app(kb_root, LibrarianSettings(chat_daily_budget_usd=1.0)))


def _answer(monkeypatch, answer: ChatAnswer) -> list[str]:
    calls: list[str] = []

    async def fake_run_chat(settings, root, message, history, **_):
        calls.append(message)
        return answer

    monkeypatch.setattr("kb_librarian.api.routes_chat.run_chat", fake_run_chat)
    return calls


def _ledger(kb_root: Path) -> list[float]:
    """Today's totals only — keyed by whatever day the ledger's own clock says, so midnight cannot bite."""
    days = json.loads((kb_root / SPEND_FILE).read_text())
    assert len(days) == 1 and all(len(day) == 10 for day in days)
    return list(days.values())


def test_chat_records_the_turn_cost_in_the_ledger(client, kb_root: Path, monkeypatch):
    _answer(monkeypatch, ChatAnswer(answer="ok", cost_usd=0.02))
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 200
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 200
    assert _ledger(kb_root) == pytest.approx([0.04])


def test_chat_without_a_reported_cost_leaves_the_ledger_alone(client, kb_root: Path, monkeypatch):
    _answer(monkeypatch, ChatAnswer(answer="ok"))
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 200
    assert not (kb_root / SPEND_FILE).exists()


def test_chat_is_429_once_the_daily_budget_is_spent(client, kb_root: Path, monkeypatch):
    calls = _answer(monkeypatch, ChatAnswer(answer="ok", cost_usd=0.5))
    ledger_for(kb_root).add(0.6)  # seeded through the ledger's own clock, never an import-time date
    assert client.post("/api/chat", json={"message": "one"}).status_code == 200  # 0.6 < 1.0: allowed, now 1.1
    response = client.post("/api/chat", json={"message": "two"})
    assert response.status_code == 429 and response.json()["error"]["message"] == SPENT
    assert calls == ["one"]  # the model was never called for the refused turn
    assert _ledger(kb_root) == pytest.approx([1.1])


def test_yesterdays_spend_does_not_count_against_today(client, kb_root: Path, monkeypatch):
    _answer(monkeypatch, ChatAnswer(answer="ok", cost_usd=0.0))
    (kb_root / SPEND_FILE).parent.mkdir(exist_ok=True)
    (kb_root / SPEND_FILE).write_text(json.dumps({"2000-01-01": 99.0}))
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 200


def test_an_errored_turn_still_records_what_it_cost(client, kb_root: Path, monkeypatch):
    _answer(monkeypatch, ChatAnswer(error="agent result error: error_max_turns", cost_usd=0.3))
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 502
    assert _ledger(kb_root) == pytest.approx([0.3])
