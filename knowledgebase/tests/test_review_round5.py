"""Fail-first tests for the round-4 findings: search oracles, foreign cancel, offline admission, scoped headers."""

import asyncio
from datetime import UTC, datetime

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kb_librarian.agent.gate import GatePolicy
from kb_librarian.api import routes_audits
from kb_librarian.api.app import create_app, install_error_handlers, install_security_headers, router
from kb_librarian.api.deps import build_state
from kb_librarian.config import LibrarianSettings
from kb_librarian.models import AuditReport
from kb_librarian.reports import ReportStore
from tests.test_review_round3 import AKIA, AUTH, KEY, _client


def _withheld_page(kb_root):
    page = kb_root / "docs/onboarding/stale.md"
    page.write_text(page.read_text().replace("owner: enablement", f"owner: {AKIA}"))


# --- code-review 1: no extraction or confirmation oracle on withheld metadata ---------------------
def test_withheld_metadata_never_matches_queries_or_filters(kb_root):
    _withheld_page(kb_root)
    client = _client(kb_root)
    assert client.get("/api/search", params={"q": AKIA[:8]}).json()["total"] == 0
    by_title = client.get("/api/search", params={"q": "Stale page"}).json()["items"]
    assert all(i["path"] != "onboarding/stale.md" for i in by_title)  # not even by its own title
    assert client.get("/api/search", params={"owner": AKIA}).json()["total"] == 0
    assert client.get("/api/pages", params={"owner": AKIA}).json()["items"] == []
    listed = client.get("/api/search").json()["items"]
    assert any(i["path"] == "onboarding/stale.md" and AKIA not in i["owner"] for i in listed)


# --- code-review 2: cancelling a foreign in-progress run still leaves the marker ------------------
def test_cancel_of_foreign_run_touches_the_marker(kb_root):
    client = _client(kb_root)
    report = AuditReport(audit_type="agent")
    ReportStore(kb_root / ".librarian/reports").save(report)
    assert client.post(f"/api/audits/{report.audit_id}/cancel", headers=AUTH).status_code == 202
    assert (kb_root / ".librarian/cancel" / report.audit_id).exists()


# --- code-review 3: concurrent offline starts are rejected, not queued ----------------------------
def test_concurrent_offline_starts_admit_exactly_one(kb_root, monkeypatch):
    real = routes_audits.run_offline_audit

    def slow_offline(*args, **kwargs):
        import time

        time.sleep(0.3)
        return real(*args, **kwargs)

    monkeypatch.setattr(routes_audits, "run_offline_audit", slow_offline)
    app = create_app(kb_root, LibrarianSettings(api_key=KEY))

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return await asyncio.gather(
                *(c.post("/api/audits", json={"type": "offline"}, headers=AUTH) for _ in range(3))
            )

    assert sorted(r.status_code for r in asyncio.run(go())) == [202, 409, 409]


# --- code-review 5: hardening middleware scoped to the mount prefix ------------------------------
def test_security_headers_are_scoped_to_the_mount_prefix(kb_root):
    platform = FastAPI()
    platform.state.kb = build_state(kb_root, LibrarianSettings(api_key=KEY))
    platform.include_router(router, prefix="/knowledge-base/api")
    install_error_handlers(platform)
    install_security_headers(platform, prefix="/knowledge-base")

    @platform.post("/uploads")
    async def upload(body: dict) -> dict:
        return {"ok": True}

    with TestClient(platform) as client:
        big = {"blob": "x" * 100_000}
        assert client.post("/uploads", json=big).status_code == 200  # the host app keeps its own limits
        assert "cache-control" not in client.post("/uploads", json={"a": 1}).headers
        kb = client.get("/knowledge-base/api/me")
        assert kb.headers["cache-control"] == "no-store" and kb.headers["x-frame-options"] == "DENY"
        assert client.post("/knowledge-base/api/pages/onboarding/README.md/reports", json=big).status_code == 413


# --- code-review 7: the latest report is parsed once per index stamp -------------------------------
def test_latest_completed_is_memoised(kb_root, monkeypatch):
    store = ReportStore(kb_root / ".librarian/reports")
    report = AuditReport(audit_type="offline")
    report.finish("completed")
    store.save(report)
    assert store.latest_completed() is not None
    monkeypatch.setattr(store, "load", lambda _id: (_ for _ in ()).throw(AssertionError("parsed again")))
    assert store.latest_completed().audit_id == report.audit_id


# --- security N8: the gate fails closed on a malformed input -------------------------------------
def test_gate_denies_non_mapping_input():
    policy = GatePolicy(dry_run=False, allowed_tools={"mcp__kb__write"}, mutating={"write"})
    assert policy.deny_reason("mcp__kb__write", "not a mapping") is not None  # type: ignore[arg-type]


# --- code-review 11: a corrupt report file never breaks the index --------------------------------
def test_report_index_skips_unreadable_files(kb_root):
    store = ReportStore(kb_root / ".librarian/reports")
    good = AuditReport(audit_type="offline")
    good.finish("completed")
    store.save(good)
    (store.reports_dir / "audit-broken.json").write_text("{not json")
    assert [e.audit_id for e in store.entries()] == [good.audit_id]
    assert store.entries()[0].stamp[1] > 0 and datetime.now(UTC) > store.entries()[0].audit_date


# --- auditor 4 / 8: throttle is thread-safe; category is validated ------------------------------
def test_problem_reports_are_thread_safe_and_category_validated(kb_root):
    from concurrent.futures import ThreadPoolExecutor

    import kb_librarian.api.routes_pages as pages

    pages._recent_reports.clear()
    with ThreadPoolExecutor(8) as pool:
        for _ in range(4):
            outcomes = list(pool.map(lambda i: pages._throttle(f"10.0.{i % 3}.{i}"), range(40)))
        assert all(o is None for o in outcomes)
    client = _client(kb_root)
    bad = {"category": "AKIA-something-else", "message": "category must come from the list"}
    assert client.post("/api/pages/onboarding/README.md/reports", json=bad).status_code == 422


# --- auditor 7: an edit is seen even when another file carries a future mtime -------------------
def test_catalog_reloads_after_edit_despite_future_mtime(kb_root):
    import os
    import time

    client = _client(kb_root)
    assert client.get("/api/pages/onboarding/README.md").json()["withheld"] is False
    future = time.time() + 3600
    os.utime(kb_root / "docs/onboarding/stale.md", (future, future))
    page = kb_root / "docs/onboarding/README.md"
    page.write_text(page.read_text() + f"\nkey: {AKIA}\n")
    assert client.get("/api/pages/onboarding/README.md").json()["withheld"] is True


# --- auditor 12: mutating-tool summaries are capped at 300 chars ---------------------------------
def test_mutating_summaries_are_capped():
    from kb_librarian.agent.hooks import build_hooks
    from kb_librarian.agent.task_manager import AuditTaskManager

    report = AuditReport(audit_type="agent")
    record = build_hooks(report, AuditTaskManager(), mutating={"write_page"})["PostToolUse"][0].hooks[0]
    asyncio.run(record({"tool_name": "mcp__kb__write_page", "tool_input": {}, "tool_response": "w" * 500}, None, None))
    assert len(report.tool_calls[0].summary) == 300
