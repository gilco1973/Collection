import json
from pathlib import Path

import pytest

from kb_librarian.actions import ActionLog
from kb_librarian.models import AuditReport
from kb_librarian.tools.context import ToolContext, text_result
from kb_librarian.tools.read_tools import build_read_tools
from kb_librarian.tools.server import MUTATING_TOOLS, build_kb_server, build_kb_tools, qualified, unqualify
from kb_librarian.tools.write_tools import build_write_tools
from tests.conftest import TODAY
from tests.helpers import payload


def _ctx(kb_root: Path, kb_config, catalog, dry_run: bool) -> ToolContext:
    report = AuditReport(audit_type="agent", dry_run=dry_run)
    return ToolContext(root=kb_root, config=kb_config, catalog=catalog, report=report, today=TODAY)


def _tools(built) -> dict:
    return {t.name: t.handler for t in built}


def test_action_log_dry_run_records_but_does_not_write(catalog, kb_root, kb_config):
    ctx = _ctx(kb_root, kb_config, catalog, dry_run=True)
    page = kb_root / "docs" / "onboarding" / "README.md"
    before = page.read_text()
    action = ctx.actions.write_page("edit", "onboarding/README.md", "changed", "why")
    assert page.read_text() == before
    assert action.dry_run and action.after_sha256 and action.before_sha256
    assert (kb_root / ".librarian/snapshots" / f"{action.action_id}.after").read_text() == "changed"
    with pytest.raises(ValueError):
        ctx.actions.rollback(action.action_id, "no")


def test_action_log_live_writes_and_rolls_back(catalog, kb_root, kb_config):
    ctx = _ctx(kb_root, kb_config, catalog, dry_run=False)
    page = kb_root / "docs" / "onboarding" / "README.md"
    before = page.read_text()
    action = ctx.actions.write_page("edit", "onboarding/README.md", "changed", "why")
    assert page.read_text() == "changed"
    rolled = ctx.actions.rollback(action.action_id, "oops")
    assert page.read_text() == before and rolled.rolled_back and rolled.rollback_reason == "oops"
    with pytest.raises(ValueError):
        ctx.actions.rollback(action.action_id, "twice")
    with pytest.raises(KeyError):
        ctx.actions.rollback("nope", "x")


def test_action_log_rollback_of_created_file_deletes_it(kb_root, kb_config, catalog):
    ctx = _ctx(kb_root, kb_config, catalog, dry_run=False)
    action = ctx.actions.write_page("create", "onboarding/new.md", "new", "why")
    assert (kb_root / "docs" / "onboarding" / "new.md").exists()
    ctx.actions.rollback(action.action_id, "undo")
    assert not (kb_root / "docs" / "onboarding" / "new.md").exists()


def test_action_log_refuses_paths_outside_docs(kb_root, kb_config, catalog):
    log = ActionLog(catalog.docs_root, AuditReport(audit_type="agent", dry_run=False), kb_root / ".librarian/snapshots")
    with pytest.raises(ValueError):
        log.write_page("edit", "../kb.config.yaml", "x", "escape")


def test_text_result_and_name_helpers():
    assert text_result("hi") == {"content": [{"type": "text", "text": "hi"}]}
    assert text_result("no", is_error=True)["is_error"] is True
    assert unqualify(qualified("run_checks")) == "run_checks"
    assert unqualify("Bash") == "Bash"
    assert "set_frontmatter_field" in MUTATING_TOOLS and "run_checks" not in MUTATING_TOOLS


async def test_read_tools(catalog, kb_root, kb_config):
    ctx = _ctx(kb_root, kb_config, catalog, dry_run=True)
    tools = _tools(build_read_tools(ctx))
    listed = payload(await tools["list_documents"]({"section": "onboarding"}))
    assert {row["path"] for row in listed} == {"onboarding/README.md", "onboarding/stale.md"}
    everything = payload(await tools["list_documents"]({}))
    assert len(everything) == 4
    got = payload(await tools["get_document"]({"path": "onboarding/stale.md"}))
    assert got["meta"]["title"] == "Stale page"
    assert (await tools["get_document"]({"path": "nope.md"})).get("is_error") is True
    hits = payload(await tools["search_documents"]({"query": "fake key"}))
    assert hits == [{"path": "onboarding/stale.md", "title": "Stale page"}]
    findings = payload(await tools["run_checks"]({"check": "sensitive"}))
    assert [f["check"] for f in findings] == ["sensitive"]
    assert len(payload(await tools["run_checks"]({}))) > 1
    contract = json.loads((await tools["get_contract"]({}))["content"][0]["text"])
    assert contract["sections"][0]["id"] == "onboarding"


async def test_write_tools_dry_run_proposes_only(catalog, kb_root, kb_config):
    ctx = _ctx(kb_root, kb_config, catalog, dry_run=True)
    tools = _tools(build_write_tools(ctx))
    out = await tools["set_frontmatter_field"](
        {"path": "onboarding/stale.md", "field": "status", "value": "draft", "reason": "r"}
    )
    assert "DRY RUN" in out["content"][0]["text"]
    assert "reviewed: 2025-01-01" in (kb_root / "docs" / "onboarding" / "stale.md").read_text()
    assert ctx.report.fixes_applied[0].dry_run is True
    assert (await tools["set_frontmatter_field"]({"path": "nope.md", "field": "a", "value": "b", "reason": "r"}))[
        "is_error"
    ]


async def test_write_tools_live_apply_and_rollback(catalog, kb_root, kb_config):
    ctx = _ctx(kb_root, kb_config, catalog, dry_run=False)
    tools = _tools(build_write_tools(ctx))
    await tools["set_frontmatter_field"](
        {"path": "onboarding/stale.md", "field": "tags", "value": '["onboarding"]', "reason": "fix tag"}
    )
    assert ctx.catalog.get("onboarding/stale.md").meta["tags"] == ["onboarding"]
    out = await tools["add_frontmatter"](
        {"path": "governance/README.md", "fields": '{"title": "Governance", "owner": "risk"}', "reason": "add"}
    )
    assert "applied" in out["content"][0]["text"]
    assert ctx.catalog.get("governance/README.md").meta["owner"] == "risk"
    assert (await tools["add_frontmatter"]({"path": "governance/README.md", "fields": "{}", "reason": "again"}))[
        "is_error"
    ]
    assert (await tools["add_frontmatter"]({"path": "onboarding/stale.md", "fields": "not json", "reason": "x"}))[
        "is_error"
    ]
    assert (await tools["add_frontmatter"]({"path": "nope.md", "fields": "{}", "reason": "x"}))["is_error"]
    (kb_root / "docs" / "governance" / "README.md").write_text("# Governance\n")
    ctx.reload()
    assert (await tools["add_frontmatter"]({"path": "governance/README.md", "fields": "[1]", "reason": "x"}))[
        "is_error"
    ]
    await tools["regenerate_index"]({"reason": "orphans"})
    assert "onboarding/stale.md" in (kb_root / "docs" / "index.md").read_text()
    flagged = await tools["flag_for_review"]({"path": "onboarding/stale.md", "reason": "old", "severity": "error"})
    assert "flagged" in flagged["content"][0]["text"] and ctx.report.manual_review_needed[0].severity == "error"
    action_id = ctx.report.fixes_applied[0].action_id
    rolled = await tools["rollback_action"]({"action_id": action_id, "reason": "undo"})
    assert "rolled back" in rolled["content"][0]["text"]
    assert (await tools["rollback_action"]({"action_id": "nope", "reason": "x"}))["is_error"]


def test_server_assembles_all_tools(catalog, kb_root, kb_config):
    ctx = _ctx(kb_root, kb_config, catalog, dry_run=True)
    tools = build_kb_tools(ctx)
    assert {t.name for t in tools} >= {"list_documents", "run_checks", "set_frontmatter_field", "flag_for_review"}
    server = build_kb_server(tools)
    assert server["type"] == "sdk" and server["name"] == "kb"
