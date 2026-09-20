"""API tests for the audit endpoints (operator side)."""

import asyncio
import contextlib
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kb_librarian.actions import ActionLog
from kb_librarian.api import routes_audits
from kb_librarian.api.app import create_app
from kb_librarian.config import LibrarianSettings
from kb_librarian.models import AuditReport
from kb_librarian.reports import ReportStore

KEY = "operator-secret-key-123"
AUTH = {"Authorization": f"Bearer {KEY}"}


@pytest.fixture
def client(kb_root: Path):
    return TestClient(create_app(kb_root, LibrarianSettings(api_key=KEY)))


def test_audits_require_operator_and_offline_runs_inline(client, kb_root):
    assert client.post("/api/audits", json={"type": "offline"}).status_code == 403
    started = client.post("/api/audits", json={"type": "offline", "dry_run": False}, headers=AUTH)
    assert started.status_code == 202 and started.json()["forced_dry_run"] is True
    audit_id = started.json()["audit_id"]
    listing = client.get("/api/audits", params={"mode": "dry"}).json()
    assert listing["total"] == 1 and listing["items"][0]["audit_id"] == audit_id
    assert client.get("/api/audits", params={"status": "failed"}).json()["total"] == 0
    detail = client.get(f"/api/audits/{audit_id}").json()
    assert detail["summary"]["issues_found"] > 0 and detail["status"] == "completed"
    assert client.get("/api/audits/nope").status_code == 404
    assert client.post(f"/api/audits/{audit_id}/cancel", headers=AUTH).status_code == 409
    exported = client.get(f"/api/audits/{audit_id}/export", params={"format": "md"})
    assert exported.status_code == 200 and exported.text.startswith("# Librarian audit")


def test_live_audit_requires_reason(kb_root):
    client = TestClient(create_app(kb_root, LibrarianSettings(api_key=KEY, allow_live=True)))
    response = client.post("/api/audits", json={"type": "agent", "dry_run": False}, headers=AUTH)
    assert response.status_code == 422 and "reason" in response.json()["error"]["message"]
    assert client.get("/api/me", headers=AUTH).json()["live_allowed"] is True


def test_agent_audit_runs_in_background_and_can_be_cancelled(kb_root, monkeypatch):
    async def fake_agent(settings, root, **kwargs):
        report = AuditReport(audit_type="agent", dry_run=kwargs["dry_run"])
        kwargs["manager"].register(report.audit_id)
        ReportStore(root / settings.reports_dir).save(report)
        kwargs["on_registered"](report.audit_id)
        with contextlib.suppress(asyncio.CancelledError):  # the real runner persists `cancelled` on cancellation
            await asyncio.sleep(0.05)
        report.finish("cancelled" if kwargs["manager"].is_cancelled(report.audit_id) else "completed")
        kwargs["manager"].unregister(report.audit_id)
        ReportStore(root / settings.reports_dir).save(report)
        return report

    monkeypatch.setattr(routes_audits, "run_agent_audit", fake_agent)
    app = create_app(kb_root, LibrarianSettings(api_key=KEY))
    with TestClient(app) as client:
        started = client.post("/api/audits", json={"type": "agent", "capabilities": ["links"]}, headers=AUTH)
        assert started.status_code == 202
        audit_id = started.json()["audit_id"]
        assert client.post(f"/api/audits/{audit_id}/cancel", headers=AUTH).status_code == 202
        assert client.post(f"/api/audits/{audit_id}/cancel").status_code == 403
        for _ in range(50):
            status = client.get(f"/api/audits/{audit_id}").json()["status"]
            if status != "in_progress":
                break
            time.sleep(0.02)
        assert status == "cancelled"


def test_rollback_endpoint(client, kb_root):
    store = ReportStore(kb_root / ".librarian/reports")
    report = AuditReport(audit_type="agent", dry_run=False)
    log = ActionLog(kb_root / "docs", report, kb_root / ".librarian/snapshots")
    page = kb_root / "docs/onboarding/README.md"
    before = page.read_text()
    action = log.write_page("edit", "onboarding/README.md", "edited", "why")
    report.finish("completed")
    proposal = AuditReport(audit_type="agent", dry_run=True)
    proposal.finish("completed")
    dry = ActionLog(kb_root / "docs", proposal, kb_root / ".librarian/snapshots").write_page(
        "edit", "onboarding/README.md", "x", "why"
    )
    store.save(report)
    store.save(proposal)
    url = f"/api/audits/{report.audit_id}/actions/{action.action_id}/rollback"
    assert client.post(url, json={"reason": "undo this please"}).status_code == 403
    assert client.post(url, json={"reason": "short"}, headers=AUTH).status_code == 422
    assert (
        client.post(
            f"/api/audits/{proposal.audit_id}/actions/{dry.action_id}/rollback",
            json={"reason": "undo this please"},
            headers=AUTH,
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/audits/{report.audit_id}/actions/nope/rollback", json={"reason": "undo this please"}, headers=AUTH
        ).status_code
        == 404
    )
    page.write_text("owner edit")
    assert client.post(url, json={"reason": "undo this please"}, headers=AUTH).status_code == 409
    done = client.post(url, json={"reason": "undo this please", "force": True}, headers=AUTH)
    assert done.status_code == 200 and done.json()["action"]["rollback_forced"] is True and page.read_text() == before
    assert client.get("/api/nope").status_code == 404 and "request_id" in client.get("/api/nope").json()["error"]


def test_console_mount_serves_spa_fallback(kb_root, tmp_path):
    from kb_librarian.api.static import mount_console

    app = create_app(kb_root, LibrarianSettings())
    assert mount_console(app, tmp_path / "missing") is False
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>console</html>")
    (dist / "assets" / "app.js").write_text("js")
    (dist / "favicon.svg").write_text("<svg/>")
    assert mount_console(app, dist) is True
    client = TestClient(app)
    assert client.get("/").text == "<html>console</html>"
    assert client.get("/search?q=x").text == "<html>console</html>"
    assert client.get("/audits/audit-1/actions/a/rollback").text == "<html>console</html>"
    assert client.get("/assets/app.js").text == "js"
    assert client.get("/favicon.svg").text == "<svg/>"
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/nope").status_code == 404
    assert client.get("/../pyproject.toml").text == "<html>console</html>"
