"""Fail-first tests for the panel findings, part 2 (reports, rollback, index, catalogs, env, gate, symlinks)."""

from pathlib import Path

import pytest
from claude_agent_sdk.types import _get_can_use_tool_shadowed_warning

from kb_librarian.catalog.catalog import load_catalog, render_index
from kb_librarian.checks import run_all_checks
from kb_librarian.checks import sensitive as sensitive_mod
from kb_librarian.checks.structure import check_structure
from kb_librarian.config import LibrarianSettings
from kb_librarian.models import AuditReport, ToolCall
from kb_librarian.reports import ReportStore
from kb_librarian.tools.context import ToolContext
from tests.conftest import TODAY

AKIA = "AKIAIOSFODNN7EXAMPLE"


def _ctx(kb_root, kb_config, dry_run=False):
    catalog = load_catalog(kb_root, kb_config)
    report = AuditReport(audit_type="agent", dry_run=dry_run)
    return ToolContext(root=kb_root, config=kb_config, catalog=catalog, report=report, today=TODAY)


# --- security I1 / code review I6: reports never persist secrets ---------------------------------
def test_redact_and_report_store_never_persist_secret(tmp_path: Path):
    assert AKIA not in sensitive_mod.redact(f"key {AKIA} here")
    report = AuditReport(audit_type="agent", ai_summary=f"found {AKIA}")
    report.tool_calls.append(ToolCall(tool="get_document", input={"markdown": AKIA}, summary=AKIA))
    store = ReportStore(tmp_path / "r")
    path = store.save(report)
    assert AKIA not in path.read_text() and AKIA not in (tmp_path / "r" / f"{report.audit_id}.md").read_text()


def test_action_snapshots_live_outside_the_report(kb_root, kb_config):
    ctx = _ctx(kb_root, kb_config)
    store = ReportStore(kb_root / ".librarian/reports")
    ctx.actions.write_page("edit", "onboarding/stale.md", "# replaced\n", "why")
    path = store.save(ctx.report)
    assert AKIA not in path.read_text()
    assert ctx.report.fixes_applied[0].before_sha256 and not hasattr(ctx.report.fixes_applied[0], "before_state")


# --- architect I3 / code review I2: rollback refuses when the page changed ------------------------
def test_rollback_refuses_when_page_changed_unless_forced(kb_root, kb_config):
    ctx = _ctx(kb_root, kb_config)
    action = ctx.actions.write_page("edit", "onboarding/README.md", "# v2\n", "why")
    (kb_root / "docs/onboarding/README.md").write_text("# owner edit\n")
    with pytest.raises(ValueError, match="changed"):
        ctx.actions.rollback(action.action_id, "undo")
    ctx.actions.rollback(action.action_id, "undo", force=True)
    assert (kb_root / "docs/onboarding/README.md").read_text().startswith("---")


# --- architect I2: index drift finding, idempotent reviewed --------------------------------------
def test_index_drift_is_a_finding_and_render_is_idempotent(kb_root, kb_config):
    catalog = load_catalog(kb_root, kb_config)
    first = render_index(catalog, kb_config, today=TODAY)
    (kb_root / "docs/index.md").write_text(first)
    catalog = load_catalog(kb_root, kb_config)
    from datetime import date

    assert render_index(catalog, kb_config, today=date(2030, 1, 1)) == first
    assert not [f for f in check_structure(catalog, kb_config) if "out of date" in f.message]
    (kb_root / "docs/onboarding/new.md").write_text(
        "---\ntitle: New\nowner: e\nstatus: active\nreviewed: 2026-09-01\n"
        "tags: [onboarding]\naudience: [everyone]\n---\n# New\n"
    )
    findings = check_structure(load_catalog(kb_root, kb_config), kb_config)
    assert any("out of date" in f.message and f.path == "index.md" for f in findings)


# --- architect I6 / product 3: catalogs are checked -----------------------------------------------
def test_catalog_yaml_is_validated_and_scanned(kb_root, kb_config):
    (kb_root / "docs/onboarding/catalog.yaml").write_text(f"version: 1\nentries:\n  - title: x\n    owner: {AKIA}\n")
    findings = run_all_checks(load_catalog(kb_root, kb_config), kb_config, today=TODAY)
    assert any(f.check == "catalogs" and f.path == "onboarding/catalog.yaml" for f in findings)
    assert any(f.check == "sensitive" and f.path == "onboarding/catalog.yaml" for f in findings)


# --- security I3: .env cannot flip the gates -------------------------------------------------------
def test_env_file_is_ignored(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("KB_ALLOW_LIVE=true\n")
    monkeypatch.delenv("KB_ALLOW_LIVE", raising=False)
    assert LibrarianSettings().resolve_dry_run(False) is True


# --- SDK 1 / security C1 regression: no shadowing, ever -------------------------------------------
def test_real_options_do_not_shadow_the_gate(tmp_path: Path):
    from kb_librarian.agent.gate import GatePolicy, make_can_use_tool
    from kb_librarian.agent.options import build_options
    from kb_librarian.tools.server import build_kb_server

    gate = make_can_use_tool(GatePolicy(True, [], set()))
    options = build_options(LibrarianSettings(), build_kb_server([]), cwd=tmp_path, can_use_tool=gate, hooks={})
    assert _get_can_use_tool_shadowed_warning(options.permission_mode, options.allowed_tools) is None


# --- security M5: symlinks are not read into the catalog ------------------------------------------
def test_symlinked_pages_are_skipped(kb_root, kb_config):
    (kb_root / "docs/onboarding/leak.md").symlink_to(kb_root / "kb.config.yaml")
    assert load_catalog(kb_root, kb_config).get("onboarding/leak.md") is None
