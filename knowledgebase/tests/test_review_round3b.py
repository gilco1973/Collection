"""Round-3 review fixes, part 2: live reason persistence, problem reports, conflicts, ceilings, mounts, headers."""

import asyncio
import json

from fastapi.testclient import TestClient

from kb_librarian.actions import ActionLog
from kb_librarian.api import routes_audits
from kb_librarian.api.app import create_app
from kb_librarian.catalog.catalog import extract_links
from kb_librarian.config import LibrarianSettings
from kb_librarian.models import AuditReport
from kb_librarian.reports import ReportStore
from tests.test_review_round3 import AKIA, AUTH, KEY, _client


def test_live_reason_and_requester_are_persisted_and_capabilities_validated(kb_root, monkeypatch):
    async def fake_agent(settings, root, **kwargs):
        report = AuditReport(
            audit_type="agent",
            dry_run=kwargs["dry_run"],
            reason=kwargs.get("reason"),
            requested_by=kwargs.get("requested_by"),
        )
        kwargs["manager"].register(report.audit_id)
        kwargs["on_registered"](report.audit_id)
        report.finish("completed")
        ReportStore(root / settings.reports_dir).save(report)
        kwargs["manager"].unregister(report.audit_id)
        return report

    monkeypatch.setattr(routes_audits, "run_agent_audit", fake_agent)
    client = _client(kb_root, allow_live=True)
    assert (
        client.post("/api/audits", json={"type": "agent", "capabilities": ["bogus"]}, headers=AUTH).status_code == 422
    )
    started = client.post(
        "/api/audits", json={"type": "agent", "dry_run": False, "reason": "quarterly clean-up"}, headers=AUTH
    )
    assert started.status_code == 202
    detail = client.get(f"/api/audits/{started.json()['audit_id']}").json()
    assert detail["reason"] == "quarterly clean-up" and detail["requested_by"] == "key"  # the bearer path


# --- security 6 / auditor 5: problem reports redacted, capped ---------------------------------------
def test_problem_reports_are_redacted_and_capped(kb_root):
    client = _client(kb_root, max_problem_reports=3)
    body = {"category": "sensitive-content", "message": f"found key {AKIA} on this page"}
    created = client.post("/api/pages/onboarding/README.md/reports", json=body)
    assert created.status_code == 201
    stored = json.loads(next((kb_root / ".librarian/problems").glob("problem-*.json")).read_text())
    assert AKIA not in stored["message"]
    for _ in range(2):
        assert client.post("/api/pages/onboarding/README.md/reports", json=body).status_code == 201
    assert client.post("/api/pages/onboarding/README.md/reports", json=body).status_code == 429


# --- security 8 / auditor 4: rollback refused while running; single-flight audits -------------------
def test_rollback_refused_while_audit_in_progress_and_second_audit_conflicts(kb_root, monkeypatch):
    store = ReportStore(kb_root / ".librarian/reports")
    client = _client(kb_root)
    running = AuditReport(audit_type="agent", dry_run=False)
    log = ActionLog(kb_root / "docs", running, kb_root / ".librarian/snapshots")
    action = log.write_page("edit", "onboarding/README.md", "v2", "why")
    store.save(running)
    client.app.state.kb.manager.register(running.audit_id)  # genuinely running in this process
    url = f"/api/audits/{running.audit_id}/actions/{action.action_id}/rollback"
    assert client.post(url, json={"reason": "undo this please"}, headers=AUTH).status_code == 409

    async def slow_agent(settings, root, **kwargs):
        report = AuditReport(audit_type="agent", dry_run=True)
        kwargs["manager"].register(report.audit_id)
        kwargs["on_registered"](report.audit_id)
        ReportStore(root / settings.reports_dir).save(report)
        await asyncio.sleep(0.3)
        report.finish("completed")
        kwargs["manager"].unregister(report.audit_id)
        ReportStore(root / settings.reports_dir).save(report)
        return report

    monkeypatch.setattr(routes_audits, "run_agent_audit", slow_agent)
    with TestClient(create_app(kb_root, LibrarianSettings(api_key=KEY))) as live:
        assert live.post("/api/audits", json={"type": "agent"}, headers=AUTH).status_code == 202
        assert live.post("/api/audits", json={"type": "agent"}, headers=AUTH).status_code == 409


# --- security 5: request budget capped by settings ----------------------------------------------------
def test_request_budget_cannot_exceed_server_ceiling(kb_root):
    client = _client(kb_root, max_budget_usd=1.0)
    assert client.post("/api/audits", json={"type": "agent", "max_budget_usd": 5.0}, headers=AUTH).status_code == 422


# --- product D3: catalog files readable through the API -----------------------------------------------
def test_catalog_yaml_is_served_read_only(kb_root):
    client = _client(kb_root)
    response = client.get("/api/files/onboarding/catalog.yaml")
    assert response.status_code == 200 and "entries" in response.text
    assert client.get("/api/files/onboarding/README.md").status_code == 404


# --- auditor 12: mounting the router installs the error envelope -------------------------------------
def test_router_mount_uses_the_error_envelope(kb_root):
    from fastapi import FastAPI

    from kb_librarian.api.app import install_error_handlers, router
    from kb_librarian.api.deps import build_state

    platform = FastAPI()
    platform.state.kb = build_state(kb_root, LibrarianSettings())
    platform.include_router(router, prefix="/knowledge-base/api")
    install_error_handlers(platform)
    response = TestClient(platform).get("/knowledge-base/api/pages/nope.md")
    assert response.status_code == 404 and "request_id" in response.json()["error"]


# --- security 10: response hardening ------------------------------------------------------------------
def test_api_responses_carry_security_headers(kb_root):
    headers = _client(kb_root).get("/api/health").headers
    assert headers["cache-control"] == "no-store" and headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY" and "referrer-policy" in headers


# --- security 7 / product D6: orphaned in-progress reports are reconciled at startup ----------------
def test_orphaned_in_progress_reports_are_marked_failed_on_startup(kb_root):
    store = ReportStore(kb_root / ".librarian/reports")
    orphan = AuditReport(audit_type="agent")
    store.save(orphan)
    client = _client(kb_root)
    assert client.get(f"/api/audits/{orphan.audit_id}").json()["status"] == "failed"
    assert client.post(f"/api/audits/{orphan.audit_id}/cancel", headers=AUTH).status_code == 409


# --- auditor 19: more fence styles and parenthesised URLs ----------------------------------------------
def test_link_extraction_handles_tilde_fences_indented_code_and_parens():
    body = "~~~\n[a](x.md)\n~~~\n    [b](y.md)\n[c](https://e.example/Foo_(bar))\n"
    assert [link.target for link in extract_links(body)] == ["https://e.example/Foo_(bar)"]
