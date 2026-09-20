"""Fail-first tests for the round-3 panel findings (admission, withholding, trail, cancel, links)."""

import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from kb_librarian.agent.hooks import build_hooks
from kb_librarian.agent.task_manager import AuditTaskManager
from kb_librarian.api import routes_audits, routes_pages
from kb_librarian.api.app import create_app
from kb_librarian.catalog.catalog import extract_links
from kb_librarian.checks.links import _probe_allowed
from kb_librarian.config import LibrarianSettings
from kb_librarian.models import AuditReport
from kb_librarian.reports import ReportStore
from tests.test_review_round3 import AKIA, AUTH, KEY, _client


async def _slow_agent(settings, root, **kwargs):
    await asyncio.sleep(0.05)  # both handlers pass validation before either task registers
    report = AuditReport(audit_type="agent", dry_run=kwargs["dry_run"])
    kwargs["manager"].register(report.audit_id)
    ReportStore(root / settings.reports_dir).save(report)
    kwargs["on_registered"](report.audit_id)
    await asyncio.sleep(0.2)
    report.finish("completed")
    kwargs["manager"].unregister(report.audit_id)
    ReportStore(root / settings.reports_dir).save(report)
    return report


# --- security N1 / auditor 1: single-flight under concurrency ------------------------------------
def test_concurrent_starts_admit_exactly_one_audit(kb_root, monkeypatch):
    monkeypatch.setattr(routes_audits, "run_agent_audit", _slow_agent)
    app = create_app(kb_root, LibrarianSettings(api_key=KEY))

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            body = {"type": "agent", "capabilities": ["links"]}
            return await asyncio.gather(*(client.post("/api/audits", json=body, headers=AUTH) for _ in range(4)))

    statuses = sorted(r.status_code for r in asyncio.run(go()))
    assert statuses == [202, 409, 409, 409]


# --- auditor 2 / security N10: catalog files are withheld and never served through symlinks ----
def test_catalog_file_with_secret_is_withheld_and_symlinks_refused(kb_root):
    catalog = kb_root / "docs/onboarding/catalog.yaml"
    catalog.write_text(catalog.read_text() + f"\nnote: {AKIA}\n")
    client = _client(kb_root)
    response = client.get("/api/files/onboarding/catalog.yaml")
    assert response.status_code == 404 and AKIA not in response.text and "withheld" in response.text
    catalog.unlink()
    catalog.symlink_to(kb_root / "kb.config.yaml")
    assert client.get("/api/files/onboarding/catalog.yaml").status_code == 404
    with pytest.raises(HTTPException) as exc:
        routes_pages.catalog_file("../kb.config.yaml", client.app.state.kb)
    assert exc.value.status_code == 404
    # a catalog whose parent directory is a symlink out of the docs root is refused by the resolve() guard
    (kb_root / "outside").mkdir()
    (kb_root / "outside/catalog.yaml").write_text("entries: []\n")
    (kb_root / "docs/onboarding").rename(kb_root / "docs/onboarding.real")
    (kb_root / "docs/onboarding").symlink_to(kb_root / "outside")
    with pytest.raises(HTTPException):
        routes_pages.catalog_file("onboarding/catalog.yaml", client.app.state.kb)


# --- security N2 / N3: withheld pages expose no metadata; error-severity hits withhold too ------
def test_withheld_page_metadata_is_redacted_everywhere(kb_root):
    page = kb_root / "docs/onboarding/stale.md"
    page.write_text(page.read_text().replace("owner: enablement", f"owner: {AKIA}"))
    client = _client(kb_root)
    detail = client.get("/api/pages/onboarding/stale.md").json()
    assert detail["withheld"] is True and AKIA not in json.dumps(detail)
    listing = client.get("/api/pages").json()
    assert AKIA not in json.dumps(listing)
    search = client.get("/api/search", params={"q": ""}).json()
    assert AKIA not in json.dumps(search)
    assert all(f["value"] != AKIA for f in search["facets"]["owner"])


def test_error_severity_hits_withhold_the_page(kb_root):
    page = kb_root / "docs/onboarding/stale.md"
    page.write_text(page.read_text() + "\npassword: hunter2secretvalue\n")
    client = _client(kb_root)
    assert client.get("/api/pages/onboarding/stale.md").json()["withheld"] is True
    assert client.get("/api/search", params={"q": "hunter2"}).json()["total"] == 0


# --- security N7 / auditor 5: read-tool responses are recorded as lengths only -------------------
def test_read_tool_responses_record_lengths_only():
    report = AuditReport(audit_type="agent")
    hooks = build_hooks(report, AuditTaskManager())
    record = hooks["PostToolUse"][0].hooks[0]
    payload = {"tool_name": "mcp__kb__get_document", "tool_input": {"path": "x.md"}, "tool_response": "s" * 250}
    asyncio.run(record(payload, None, None))
    assert report.tool_calls[0].summary == "250 chars"


# --- auditor 6: cancelling a post-startup orphan resolves it ------------------------------------
def test_cancel_of_stale_in_progress_report_marks_it_failed(kb_root):
    client = _client(kb_root)
    store = ReportStore(kb_root / ".librarian/reports")
    report = AuditReport(audit_type="agent")
    store.save(report)  # in_progress, but no task and no process owns it
    response = client.post(f"/api/audits/{report.audit_id}/cancel", headers=AUTH)
    assert response.status_code == 202 and response.json()["status"] == "failed"
    assert client.get(f"/api/audits/{report.audit_id}").json()["status"] == "failed"


# --- code-review 5 / auditor 3: indented list content is scanned, indented code is not -------
def test_link_extraction_scans_indented_list_content_only():
    nested = "- top\n    - [n](missing.md)\n\n1. step\n\n    [c](cont.md)\n"
    assert [x.target for x in extract_links(nested)] == ["missing.md", "cont.md"]
    code = "para\n\n    [code](skip.md)\n    more [code](skip2.md)\nback [ok](ok.md)\n"
    assert [x.target for x in extract_links(code)] == ["ok.md"]


# --- code-review 4: the audit list never loads a report -----------------------------------------
def test_list_audits_uses_the_index_only(kb_root, monkeypatch):
    client = _client(kb_root)
    for dry in (True, False):
        report = AuditReport(audit_type="offline", dry_run=dry)
        report.finish("completed")
        client.app.state.kb.store.save(report)
    assert client.get("/api/audits").json()["total"] == 2

    def boom(_id):
        raise AssertionError("list must not load reports")

    monkeypatch.setattr(client.app.state.kb.store, "load", boom)
    listing = client.get("/api/audits", params={"mode": "live", "type": "offline"}).json()
    assert listing["total"] == 1 and listing["items"][0]["dry_run"] is False


# --- security N6 / auditor 7: problem report category redacted; throttle buckets pruned ---------
def test_problem_report_category_is_redacted_and_buckets_pruned(kb_root):
    client = _client(kb_root)
    routes_pages._recent_reports.clear()
    body = {"category": "other", "message": f"the message mentions {AKIA} which must not be stored"}
    assert client.post("/api/pages/onboarding/README.md/reports", json=body).status_code == 201
    stored = json.loads(next((kb_root / ".librarian/problems").glob("*.json")).read_text())
    assert AKIA not in stored["message"] and stored["category"] == "other"
    routes_pages._recent_reports["10.0.0.9"].append(-10_000.0)
    routes_pages._throttle("10.0.0.1")
    assert "10.0.0.9" not in routes_pages._recent_reports


# --- auditor 10 / code-review 9: an empty capability list is a client error -------------------
def test_empty_capabilities_rejected(kb_root):
    client = _client(kb_root)
    response = client.post("/api/audits", json={"type": "agent", "capabilities": []}, headers=AUTH)
    assert response.status_code == 422


# --- security N4: NAT64, 6to4 and multicast never probed ------------------------------------------
def test_ssrf_guard_rejects_nat64_6to4_and_multicast(monkeypatch):
    def fake_getaddrinfo(host, *a, **k):
        table = {
            "nat64.example.com": "64:ff9b::7f00:1",
            "sixtofour.example.com": "2002:7f00:1::1",
            "mc.example.com": "224.0.0.1",
        }
        return [(None, None, None, None, (table[host], 443))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)
    assert not any(_probe_allowed(h) for h in ("nat64.example.com", "sixtofour.example.com", "mc.example.com"))


# --- security N5: a chunked body over the cap is refused before parsing ------------------------
def test_chunked_body_over_cap_is_refused(kb_root):
    app = create_app(kb_root, LibrarianSettings(api_key=KEY))
    big = json.dumps({"category": "x" * 10, "message": "y" * 80_000}).encode()

    def chunks():
        yield big[:40_000]
        yield big[40_000:]

    with TestClient(app) as client:
        response = client.post(
            "/api/pages/onboarding/README.md/reports", content=chunks(), headers={"Content-Type": "application/json"}
        )
    assert response.status_code == 413
