"""Fail-first tests for the round-2 panel findings (API, console-facing API, actions)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from kb_librarian.actions import ActionLog
from kb_librarian.api.app import create_app
from kb_librarian.catalog.catalog import load_catalog
from kb_librarian.config import LibrarianSettings
from kb_librarian.models import AuditReport, Finding
from kb_librarian.reports import ReportStore
from kb_librarian.tools.context import ToolContext
from kb_librarian.tools.write_tools import build_write_tools
from tests.conftest import TODAY

KEY = "operator-secret-key-123"
AUTH = {"Authorization": f"Bearer {KEY}"}
AKIA = "AKIAIOSFODNN7EXAMPLE"


def _client(kb_root, **settings):
    return TestClient(create_app(kb_root, LibrarianSettings(api_key=KEY, **settings)))


def _sensitive_report(kb_root, path="onboarding/stale.md", when=None):
    store = ReportStore(kb_root / ".librarian/reports")
    report = AuditReport(audit_type="offline")
    if when:
        report.audit_date = when
    report.findings.append(
        Finding(check="sensitive", severity="critical", path=path, message="possible aws access key")
    )
    report.finish("completed")
    store.save(report)
    return report


# --- security 1 / auditor 1: search never exposes withheld bodies ----------------------------------
def test_search_never_leaks_withheld_page_body(kb_root):
    client = _client(kb_root)
    _sensitive_report(kb_root)
    result = client.get("/api/search", params={"q": AKIA[:8]}).json()
    assert result["total"] == 0
    by_title = client.get("/api/search", params={"q": "Stale page"}).json()
    assert all(i["path"] != "onboarding/stale.md" for i in by_title["items"])  # not even by its own title
    listed = next(i for i in client.get("/api/search").json()["items"] if i["path"] == "onboarding/stale.md")
    assert listed["snippet"] is None and AKIA not in str(listed)


# --- security 2: withhold is decided at request time too --------------------------------------------
def test_page_is_withheld_by_request_time_scan_without_any_audit(kb_root):
    page = _client(kb_root).get("/api/pages/onboarding/stale.md").json()
    assert page["withheld"] is True and page["body_markdown"] is None


# --- code review 9 / auditor 6: latest audit follows audit_date, not file mtime ---------------------
def test_latest_audit_is_by_audit_date_not_mtime(kb_root):
    client = _client(kb_root)
    old = _sensitive_report(kb_root, path="onboarding/README.md", when=datetime.now(UTC) - timedelta(days=2))
    store = ReportStore(kb_root / ".librarian/reports")
    new = AuditReport(audit_type="offline")
    new.finish("completed")
    store.save(new)
    store.save(old)  # a rollback re-save touches the old file last
    assert client.get("/api/audits").json()["items"][0]["audit_id"] == new.audit_id
    assert client.get("/api/pages/onboarding/README.md/findings").json()["items"] == []


# --- auditor 2: the real lost-update window ---------------------------------------------------------
async def test_write_refuses_when_page_changed_since_catalog_load(kb_root, kb_config):
    ctx = ToolContext(
        root=kb_root,
        config=kb_config,
        catalog=load_catalog(kb_root, kb_config),
        report=AuditReport(audit_type="agent", dry_run=False),
        today=TODAY,
    )
    tools = {t.name: t.handler for t in build_write_tools(ctx)}
    page = kb_root / "docs/onboarding/README.md"
    page.write_text(page.read_text() + "\nOWNER EDIT\n")
    out = await tools["set_frontmatter_field"](
        {"path": "onboarding/README.md", "field": "status", "value": "draft", "reason": "r"}
    )
    assert out.get("is_error") is True and "OWNER EDIT" in page.read_text()


# --- auditor 16: rollback verifies the snapshot -----------------------------------------------------
def test_rollback_refuses_tampered_snapshot(kb_root):
    report = AuditReport(audit_type="agent", dry_run=False)
    log = ActionLog(kb_root / "docs", report, kb_root / ".librarian/snapshots")
    action = log.write_page("edit", "onboarding/README.md", "v2", "why")
    (kb_root / ".librarian/snapshots" / f"{action.action_id}.before").write_text("tampered")
    with pytest.raises(ValueError, match="snapshot"):
        log.rollback(action.action_id, "undo")


# --- auditor 7: non-ASCII bearer token ---------------------------------------------------------------
def test_non_ascii_bearer_is_a_viewer_not_a_500(kb_root):
    raw = [(b"authorization", "Bearer ключ".encode())]  # the bytes a client puts on the wire
    response = _client(kb_root).get("/api/me", headers=raw)
    assert response.status_code == 200 and response.json()["role"] == "viewer"
