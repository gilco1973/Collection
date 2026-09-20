"""API tests through the FastAPI test client (no network, no LLM)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kb_librarian.api.app import create_app
from kb_librarian.config import LibrarianSettings
from kb_librarian.models import AuditReport, Finding
from kb_librarian.reports import ReportStore

KEY = "operator-secret-key-123"
AUTH = {"Authorization": f"Bearer {KEY}"}


@pytest.fixture
def client(kb_root: Path):
    app = create_app(kb_root, LibrarianSettings(api_key=KEY), cors_origins=["http://localhost:5173"])
    return TestClient(app)


def test_health_me_and_contract(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/me").json()["role"] == "viewer"
    me = client.get("/api/me", headers=AUTH).json()
    assert me["role"] == "operator" and me["live_allowed"] is False
    assert client.get("/api/me", headers={"Authorization": "Bearer wrong"}).json()["role"] == "viewer"
    contract = client.get("/api/contract").json()
    assert contract["sections"][0]["id"] == "onboarding" and "freshness" in contract["capabilities"]
    assert contract["defaults"]["max_turns"] == 40


def test_sections_pages_and_search(client):
    sections = client.get("/api/sections").json()
    assert sections[0]["id"] == "onboarding" and sections[0]["page_count"] == 2 and sections[0]["stale_count"] == 1
    pages = client.get("/api/sections/onboarding/pages").json()["items"]
    assert {p["path"] for p in pages} == {"onboarding/README.md", "onboarding/stale.md"}
    assert client.get("/api/sections/nope/pages").status_code == 404
    stale = client.get("/api/pages", params={"stale": "true"}).json()["items"]
    assert [p["path"] for p in stale] == ["onboarding/stale.md"]
    result = client.get("/api/search", params={"q": "Healthy page"}).json()
    assert result["total"] == 1 and "Healthy" in result["items"][0]["snippet"] and result["facets"]["section"]
    filtered = client.get("/api/search", params={"q": "", "section": "governance"}).json()
    assert [i["path"] for i in filtered["items"]] == ["governance/README.md"]
    assert (
        client.get(
            "/api/search", params={"q": "", "audience": "new-hire", "status": "active", "stale": "false"}
        ).json()["total"]
        == 1
    )
    assert client.get("/api/pages", params={"stale": "maybe"}).status_code == 422


def test_pages_listing_filters_by_audience(client):
    """A persona's reading list: `/api/pages?audience=` narrows by audience like `/api/search` does."""
    for_new_hires = client.get("/api/pages", params={"audience": "new-hire"}).json()["items"]
    assert {p["path"] for p in for_new_hires} == {"onboarding/README.md", "onboarding/stale.md"}
    assert client.get("/api/pages", params={"audience": "leadership"}).json()["items"] == []
    combined = client.get("/api/pages", params={"audience": "new-hire", "stale": "true"}).json()["items"]
    assert [p["path"] for p in combined] == ["onboarding/stale.md"]
    everyone = {p["path"] for p in client.get("/api/pages", params={"audience": "everyone"}).json()["items"]}
    assert "index.md" in everyone and "onboarding/README.md" not in everyone
    unfiltered = client.get("/api/pages").json()["items"]  # the filter is opt-in; the plain listing is unchanged
    assert len(unfiltered) > len(for_new_hires)


def test_page_view_withholds_sensitive_pages_and_reports_problems(client, kb_root):
    page = client.get("/api/pages/onboarding/README.md").json()
    assert (
        page["withheld"] is False
        and page["body_markdown"].startswith("# Onboarding")
        and page["section"]["id"] == "onboarding"
    )
    assert client.get("/api/pages/nope.md").status_code == 404
    store = ReportStore(kb_root / ".librarian/reports")
    report = AuditReport(audit_type="offline")
    report.findings.append(
        Finding(check="sensitive", severity="critical", path="onboarding/stale.md", message="possible aws access key")
    )
    report.finish("completed")
    store.save(report)
    withheld = client.get("/api/pages/onboarding/stale.md").json()
    assert withheld["withheld"] is True and withheld["body_markdown"] is None
    assert client.get("/api/pages/onboarding/stale.md/findings").json()["items"][0]["check"] == "sensitive"
    assert client.get("/api/pages/onboarding/README.md/findings").json()["items"] == []
    created = client.post(
        "/api/pages/onboarding/stale.md/reports",
        json={"category": "outdated", "message": "This page is stale and wrong."},
    )
    assert created.status_code == 201 and created.json()["owner"] == "enablement"
    assert list((kb_root / ".librarian/problems").glob("problem-*.json"))
    missing = client.post("/api/pages/nope.md/reports", json={"category": "other", "message": "long enough message"})
    assert missing.status_code == 404
    assert (
        client.post("/api/pages/onboarding/stale.md/reports", json={"category": "x", "message": "short"}).status_code
        == 422
    )


def test_page_view_serves_a_translation_when_one_exists(client, kb_root):
    contract = client.get("/api/contract").json()
    assert contract["i18n"]["languages"] == ["es", "he"]
    english = client.get("/api/pages/onboarding/README.md").json()
    assert english["translated"] is False and english["meta"]["title"] == "Onboarding"
    not_yet = client.get("/api/pages/onboarding/README.md", params={"lang": "es"}).json()
    assert not_yet["translated"] is False and not_yet["meta"]["title"] == "Onboarding"  # falls back to English
    (kb_root / "docs/i18n/es/onboarding").mkdir(parents=True)
    (kb_root / "docs/i18n/es/onboarding/README.md").write_text(
        "---\ntitle: Inicio\nowner: enablement\nstatus: active\nreviewed: 2026-09-01\n"
        "tags: [onboarding]\naudience: [new-hire]\n---\n# Inicio\n\nContenido traducido.\n",
        encoding="utf-8",
    )
    translated = client.get("/api/pages/onboarding/README.md", params={"lang": "es"}).json()
    assert translated["translated"] is True
    assert translated["meta"]["title"] == "Inicio" and translated["meta"]["owner"] == "enablement"
    assert translated["body_markdown"].strip() == "# Inicio\n\nContenido traducido."
    # an unconfigured language code is ignored, never used to read outside docs/i18n/<lang>/
    escape = client.get("/api/pages/onboarding/README.md", params={"lang": "../../etc"}).json()
    assert escape["translated"] is False and escape["meta"]["title"] == "Onboarding"


def test_lang_translates_listings_search_and_section_titles(client, kb_root):
    def write(rel_path, title, body):
        target = kb_root / "docs/i18n/es" / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            f"---\ntitle: {title}\nowner: enablement\nstatus: active\nreviewed: 2026-09-01\n"
            f"tags: [onboarding]\naudience: [new-hire]\n---\n{body}\n",
            encoding="utf-8",
        )

    write("onboarding/README.md", "Incorporación", "# Incorporación\n\nPágina saludable con palabra clave única.")

    # sections: the README's translated title becomes the section's title
    sections = client.get("/api/sections", params={"lang": "es"}).json()
    onboarding = next(s for s in sections if s["id"] == "onboarding")
    assert onboarding["title"] == "Incorporación"
    other = next(s for s in sections if s["id"] == "governance")
    assert other["title"] == "Governance"  # no translated README yet: unchanged

    # section pages / pages listing: translated titles, English pages fall back unchanged
    section_pages = client.get("/api/sections/onboarding/pages", params={"lang": "es"}).json()["items"]
    titles = {p["path"]: p["title"] for p in section_pages}
    assert titles["onboarding/README.md"] == "Incorporación"
    assert titles["onboarding/stale.md"] == "Stale page"

    # search: matches and snippets the translated body text, not the English one
    result = client.get("/api/search", params={"q": "palabra clave única", "lang": "es"}).json()
    assert result["total"] == 1 and result["items"][0]["path"] == "onboarding/README.md"
    assert result["items"][0]["title"] == "Incorporación"
    miss = client.get("/api/search", params={"q": "palabra clave única"}).json()  # no lang: English body only
    assert miss["total"] == 0

    # the single-page breadcrumb section title is translated too
    page = client.get("/api/pages/onboarding/README.md", params={"lang": "es"}).json()
    assert page["section"]["title"] == "Incorporación"
    page_en = client.get("/api/pages/onboarding/README.md").json()
    assert page_en["section"]["title"] == "Onboarding"
