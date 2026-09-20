"""GET /api/insights and POST /api/insights/refresh: operator-only, 404 until generated, same-origin on refresh."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kb_librarian.api.app import create_app
from kb_librarian.api.routes_insights import NO_INSIGHTS
from kb_librarian.auth.session import SESSION_COOKIE, sign
from kb_librarian.config import LibrarianSettings
from kb_librarian.insights import store
from kb_librarian.models import AuditReport, Finding
from kb_librarian.reports import ReportStore
from tests.fake_idp import CLIENT_ID, ISSUER, REDIRECT_URI
from tests.test_insights import WITHHELD, A, B, populated  # noqa: F401  (the shared fixture)

KEY = "operator-secret-key-123"
AUTH = {"Authorization": f"Bearer {KEY}"}
SECRET = "session-secret-for-tests-0123456789abcdef"


@pytest.fixture
def client(populated: Path) -> TestClient:  # noqa: F811
    settings = LibrarianSettings(
        api_key=KEY, oidc_issuer=ISSUER, oidc_client_id=CLIENT_ID, oidc_redirect_uri=REDIRECT_URI, session_secret=SECRET
    )
    return TestClient(create_app(populated, settings), base_url="https://testserver")


def test_viewers_are_refused_anonymous_and_signed_in(client: TestClient):
    assert client.get("/api/insights").status_code == 403
    assert client.post("/api/insights/refresh").status_code == 403
    client.cookies.set(SESSION_COOKIE, sign({"sub": "u-1", "iss": ISSUER, "name": "Ada"}, SECRET, 3600, "session"))
    assert client.get("/api/me").json()["user"]["sub"] == "u-1"  # signed in, but a viewer
    assert client.get("/api/insights").status_code == 403
    assert client.post("/api/insights/refresh").status_code == 403


def test_404_before_generation_then_refresh_then_200(client: TestClient, populated: Path):  # noqa: F811
    missing = client.get("/api/insights", headers=AUTH)
    assert missing.status_code == 404 and missing.json()["error"]["message"] == NO_INSIGHTS
    refreshed = client.post("/api/insights/refresh", headers=AUTH)
    assert refreshed.status_code == 200
    data = refreshed.json()
    assert set(data) == {"generated_at", "k", "window_days", "pages", "unanswered", "suppressed"}
    assert data["k"] == 5 and data["pages"][A]["readers"] == 6 and data["pages"][B]["readers"] is None
    assert WITHHELD not in data["pages"] and store.read(populated) is not None
    assert client.get("/api/insights", headers=AUTH).json() == data


def test_refresh_refuses_a_cross_site_request_even_with_a_key(client: TestClient):
    foreign = client.post("/api/insights/refresh", headers={**AUTH, "Origin": "https://evil.example"})
    assert foreign.status_code == 403 and "cross-site" in foreign.json()["error"]["message"]
    fetch_site = client.post("/api/insights/refresh", headers={**AUTH, "Sec-Fetch-Site": "cross-site"})
    assert fetch_site.status_code == 403
    assert client.get("/api/insights", headers=AUTH).status_code == 404  # nothing was generated
    ours = client.post("/api/insights/refresh", headers={**AUTH, "Origin": "https://testserver"})
    assert ours.status_code == 200


def test_get_drops_a_page_withheld_after_generation(client: TestClient, populated: Path):  # noqa: F811
    assert client.post("/api/insights/refresh", headers=AUTH).status_code == 200
    assert A in client.get("/api/insights", headers=AUTH).json()["pages"]
    reports = ReportStore(populated / ".librarian/reports")
    report = AuditReport(audit_type="offline")
    report.findings.append(Finding(check="sensitive", severity="critical", path=A, message="possible aws access key"))
    report.finish("completed")
    reports.save(report)
    served = client.get("/api/insights", headers=AUTH).json()
    assert A not in served["pages"] and B in served["pages"]
    assert A not in client.post("/api/insights/refresh", headers=AUTH).json()["pages"]
