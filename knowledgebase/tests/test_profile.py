"""kb_librarian/profile + /api/profile: per-reader progress, persona and forget-me."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kb_librarian.api.app import create_app
from kb_librarian.auth.session import SESSION_COOKIE, sign
from kb_librarian.config import LibrarianSettings
from kb_librarian.models import AuditReport, Finding
from kb_librarian.profile.store import MAX_QUIZZES, MAX_VIEWED, PageVisit, Profile, ProfileStore, QuizResult
from kb_librarian.reports import ReportStore
from tests.fake_idp import CLIENT_ID, ISSUER, REDIRECT_URI

SECRET = "session-secret-for-tests-0123456789abcdef"


def _client(kb_root: Path, sub: str | None = "u-1") -> TestClient:
    settings = LibrarianSettings(
        oidc_issuer=ISSUER, oidc_client_id=CLIENT_ID, oidc_redirect_uri=REDIRECT_URI, session_secret=SECRET
    )
    client = TestClient(create_app(kb_root, settings), base_url="https://testserver")
    if sub:
        client.cookies.set(SESSION_COOKIE, sign({"sub": sub, "iss": ISSUER, "name": "Ada"}, SECRET, 3600, "session"))
    return client


def test_store_records_views_persona_quizzes_and_forgets(kb_root: Path):
    store = ProfileStore(kb_root)
    empty = store.load("u-1")
    assert empty.sub == "u-1" and empty.viewed == {} and empty.persona is None and empty.quizzes == []
    store.record_view("u-1", "onboarding/README.md")
    profile = store.record_view("u-1", "onboarding/README.md")
    assert profile.viewed["onboarding/README.md"].count == 2
    files = list((kb_root / ".librarian" / "users").glob("*.json"))
    assert len(files) == 1 and "u-1" not in files[0].name and "u-1" not in files[0].stem  # subject is hashed
    assert ProfileStore(kb_root)._path(f"{ISSUER}\0u-1") != files[0]  # the same sub at another issuer is someone else
    assert store.set_persona("u-1", "engineer").persona == "engineer"
    assert store.record_quiz("u-1", QuizResult(path="onboarding/README.md", score=2, total=3)).quizzes[0].score == 2
    assert store.load("u-1").persona == "engineer" and store.load("u-2").persona is None
    assert store.delete("u-1") is True and store.delete("u-1") is False and store.load("u-1").viewed == {}


def test_store_caps_history_and_survives_a_corrupt_file(kb_root: Path):
    store = ProfileStore(kb_root)
    profile = Profile(sub="u-1")
    for n in range(MAX_VIEWED):
        profile.viewed[f"p{n}.md"] = PageVisit(
            last_at=datetime(2026, 1, 1, tzinfo=UTC).replace(second=n % 60, minute=n // 60)
        )
    store.save(profile)
    profile = store.record_view("u-1", "newest.md")
    assert len(profile.viewed) == MAX_VIEWED and "newest.md" in profile.viewed and "p0.md" not in profile.viewed
    profile.quizzes = [QuizResult(path=f"q{n}.md", score=1, total=1) for n in range(MAX_QUIZZES)]
    store.save(profile)
    profile = store.record_quiz("u-1", QuizResult(path="newest.md", score=1, total=1))
    assert len(profile.quizzes) == MAX_QUIZZES and profile.quizzes[-1].path == "newest.md"
    assert profile.quizzes[0].path == "q1.md"  # the oldest result made room
    store._path("u-1").write_text("{not json")
    assert store.load("u-1").viewed == {}


def test_profile_routes_require_a_signed_in_reader(kb_root: Path):
    anonymous = _client(kb_root, sub=None)
    assert anonymous.get("/api/profile").status_code == 401
    assert anonymous.post("/api/profile/views", json={"path": "onboarding/README.md"}).status_code == 401
    assert anonymous.put("/api/profile/persona", json={"persona": "engineer"}).status_code == 401
    assert anonymous.delete("/api/profile").status_code == 401


def test_profile_round_trip_with_progress_and_personas(kb_root: Path):
    client = _client(kb_root)
    empty = client.get("/api/profile").json()
    assert empty["persona"] is None and empty["viewed"] == {} and "everyone" not in empty["personas"]
    assert "new-hire" in empty["personas"] and [p["viewed"] for p in empty["progress"]] == [0, 0]
    assert client.post("/api/profile/views", json={"path": "onboarding/README.md"}).status_code == 201
    assert client.post("/api/profile/views", json={"path": "onboarding/README.md"}).json()["count"] == 2
    assert client.post("/api/profile/views", json={"path": "nope.md"}).status_code == 404
    assert client.put("/api/profile/persona", json={"persona": "wizard"}).status_code == 422
    assert client.put("/api/profile/persona", json={"persona": "engineer"}).json()["persona"] == "engineer"
    profile = client.get("/api/profile").json()
    assert profile["viewed"]["onboarding/README.md"]["count"] == 2
    assert profile["viewed"]["onboarding/README.md"]["title"] == "Onboarding"
    onboarding = next(p for p in profile["progress"] if p["section"] == "onboarding")
    assert onboarding == {"section": "onboarding", "title": "Onboarding", "viewed": 1, "total": 2}
    assert _client(kb_root, sub="u-2").get("/api/profile").json()["viewed"] == {}  # another reader sees nothing
    assert client.put("/api/profile/persona", json={"persona": None}).json()["persona"] is None
    assert client.delete("/api/profile").status_code == 204
    assert client.get("/api/profile").json()["viewed"] == {}


def test_a_withheld_page_is_never_recorded_as_read(kb_root: Path):
    client = _client(kb_root)
    assert client.post("/api/profile/views", json={"path": "onboarding/stale.md"}).status_code == 404  # sensitive text
    healthy = kb_root / "docs" / "onboarding" / "README.md"
    report = AuditReport(audit_type="offline", dry_run=True)
    report.findings = [Finding(check="sensitive", severity="critical", path="onboarding/README.md", message="x")]
    report.finish("completed")
    ReportStore(kb_root / ".librarian" / "reports").save(report)
    assert healthy.is_file()
    assert client.post("/api/profile/views", json={"path": "onboarding/README.md"}).status_code == 404  # by finding


def test_a_page_withheld_after_it_was_read_drops_out_of_the_history(kb_root: Path):
    client = _client(kb_root)
    assert client.post("/api/profile/views", json={"path": "onboarding/README.md"}).status_code == 201
    assert "onboarding/README.md" in client.get("/api/profile").json()["viewed"]
    page = kb_root / "docs" / "onboarding" / "README.md"
    page.write_text(page.read_text().replace("title: Onboarding", "title: Onboarding AKIAIOSFODNN7EXAMPLE"))
    profile = client.get("/api/profile").json()
    assert profile["viewed"] == {}  # neither the (now sensitive) title nor the path is echoed
    assert "AKIA" not in json.dumps(profile)


def test_views_of_pages_that_no_longer_exist_are_hidden(kb_root: Path):
    client = _client(kb_root)
    assert client.post("/api/profile/views", json={"path": "onboarding/README.md"}).status_code == 201
    (kb_root / "docs" / "onboarding" / "README.md").unlink()
    assert client.get("/api/profile").json()["viewed"] == {}
    raw = json.loads(next((kb_root / ".librarian" / "users").glob("*.json")).read_text())
    assert "onboarding/README.md" in raw["viewed"]  # still on disk until the reader forgets it


@pytest.mark.parametrize("path", ["", "x" * 401])
def test_view_body_is_validated(kb_root: Path, path: str):
    assert _client(kb_root).post("/api/profile/views", json={"path": path}).status_code == 422


def test_quiz_results_are_recorded_for_a_readable_page_only(kb_root: Path):
    client = _client(kb_root)
    result = {"path": "onboarding/README.md", "score": 2, "total": 3}
    assert _client(kb_root, sub=None).post("/api/profile/quizzes", json=result).status_code == 401
    created = client.post("/api/profile/quizzes", json=result)
    assert created.status_code == 201
    assert {k: created.json()[k] for k in ("path", "score", "total")} == result
    assert created.json()["at"].endswith("Z") or "+00:00" in created.json()["at"]
    assert client.post("/api/profile/quizzes", json={**result, "path": "nope.md"}).status_code == 404
    assert client.post("/api/profile/quizzes", json={**result, "path": "onboarding/stale.md"}).status_code == 404
    quizzes = client.get("/api/profile").json()["quizzes"]
    assert len(quizzes) == 1 and quizzes[0]["score"] == 2 and quizzes[0]["total"] == 3
    raw = json.loads(next((kb_root / ".librarian" / "users").glob("*.json")).read_text())
    assert set(raw["quizzes"][0]) == {"path", "at", "score", "total"}  # no question text, no answers


@pytest.mark.parametrize(
    "body",
    [
        {"path": "onboarding/README.md", "score": 4, "total": 3},
        {"path": "onboarding/README.md", "score": -1, "total": 3},
        {"path": "onboarding/README.md", "score": 0, "total": 0},
        {"path": "onboarding/README.md", "score": 11, "total": 11},
        {"path": "", "score": 1, "total": 3},
        {"path": "onboarding/README.md", "score": 1},
    ],
)
def test_quiz_body_is_validated(kb_root: Path, body: dict):
    assert _client(kb_root).post("/api/profile/quizzes", json=body).status_code == 422
