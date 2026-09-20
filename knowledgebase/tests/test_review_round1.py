"""Fail-first tests for the panel findings (architect, code review, security, SDK, product)."""

from kb_librarian.catalog.catalog import extract_links, load_catalog
from kb_librarian.catalog.frontmatter import parse_frontmatter, render_frontmatter
from kb_librarian.checks import run_all_checks
from kb_librarian.checks.frontmatter_check import parse_reviewed
from kb_librarian.checks.sensitive import check_sensitive
from kb_librarian.models import AuditReport
from kb_librarian.tools.context import ToolContext
from kb_librarian.tools.write_tools import build_write_tools
from tests.conftest import TODAY

AKIA = "AKIAIOSFODNN7EXAMPLE"


def _ctx(kb_root, kb_config, dry_run=False):
    catalog = load_catalog(kb_root, kb_config)
    return ToolContext(
        root=kb_root,
        config=kb_config,
        catalog=catalog,
        report=AuditReport(audit_type="agent", dry_run=dry_run),
        today=TODAY,
    )


def _write_tools(ctx):
    return {t.name: t.handler for t in build_write_tools(ctx)}


# --- code review C1: set_frontmatter_field must refuse invalid/missing frontmatter -------------
async def test_set_field_refuses_when_frontmatter_invalid_or_missing(kb_root, kb_config):
    bad = kb_root / "docs/onboarding/bad.md"
    bad.write_text("---\ntitle: T: colon\nowner: x\n---\n# Bad\n")
    ctx = _ctx(kb_root, kb_config)
    tools = _write_tools(ctx)
    out = await tools["set_frontmatter_field"](
        {"path": "onboarding/bad.md", "field": "status", "value": "draft", "reason": "r"}
    )
    assert out.get("is_error") is True and "title: T: colon" in bad.read_text()
    out = await tools["set_frontmatter_field"](
        {"path": "governance/README.md", "field": "status", "value": "draft", "reason": "r"}
    )
    assert out.get("is_error") is True and "add_frontmatter" in out["content"][0]["text"]


def test_render_never_emits_parse_error_key():
    text = render_frontmatter({"_parse_error": "x", "title": "T"}, "body")
    assert "_parse_error" not in text and "title: T" in text


# --- security I7: field validation ---------------------------------------------------------------
async def test_set_field_rejects_reviewed_unknown_fields_and_bad_values(kb_root, kb_config):
    ctx = _ctx(kb_root, kb_config)
    tools = _write_tools(ctx)
    for field, value in (
        ("reviewed", "2026-09-15"),
        ("evil", "x"),
        ("status", "bogus"),
        ("audience", '["nobody"]'),
        ("tags", '["not-a-real-tag"]'),
    ):
        out = await tools["set_frontmatter_field"](
            {"path": "onboarding/README.md", "field": field, "value": value, "reason": "r"}
        )
        assert out.get("is_error") is True, field
    ok = await tools["set_frontmatter_field"](
        {"path": "onboarding/README.md", "field": "status", "value": "draft", "reason": "r"}
    )
    assert "applied" in ok["content"][0]["text"]


# --- code review I3: timestamps in reviewed ------------------------------------------------------
def test_parse_reviewed_accepts_datetime_and_check_survives(kb_root, kb_config):
    from datetime import date, datetime

    assert parse_reviewed(datetime(2025, 1, 1, 10, 0)) == date(2025, 1, 1)
    page = kb_root / "docs/onboarding/README.md"
    page.write_text(page.read_text().replace("reviewed: 2026-09-01", "reviewed: 2025-01-01 10:00:00"))
    findings = run_all_checks(load_catalog(kb_root, kb_config), kb_config, today=TODAY)
    assert any(f.check == "freshness" and f.path == "onboarding/README.md" for f in findings)


# --- code review I4 + security I4: file-relative lines, frontmatter scanned -----------------------
def test_sensitive_lines_are_file_relative_and_frontmatter_is_scanned(kb_root, kb_config):
    findings = check_sensitive(load_catalog(kb_root, kb_config), kb_config)
    stale = [f for f in findings if f.path == "onboarding/stale.md"]
    assert stale and stale[0].line == 12
    page = kb_root / "docs/onboarding/README.md"
    page.write_text(page.read_text().replace("owner: enablement", f"owner: enablement\nnote: {AKIA}"))
    findings = check_sensitive(load_catalog(kb_root, kb_config), kb_config)
    assert any(f.path == "onboarding/README.md" and f.line == 4 for f in findings)


# --- code review I8/I9: CRLF and fenced links -----------------------------------------------------
def test_crlf_frontmatter_parses():
    meta, body = parse_frontmatter("---\r\ntitle: T\r\n--- \r\n# B\r\n")
    assert meta == {"title": "T"} and body.startswith("# B")


def test_links_inside_code_fences_are_ignored():
    body = "```markdown\n[a](missing.md)\n```\ntext `[b](inline.md)` and [c](real.md)\n"
    assert [link.target for link in extract_links(body)] == ["real.md"]


# --- security I5: allowlist marker ---------------------------------------------------------------
def test_allow_marker_only_for_placeholders_and_is_visible(kb_root, kb_config):
    page = kb_root / "docs/onboarding/README.md"
    page.write_text(
        page.read_text() + f"\nkey {AKIA} <!-- kb-allow-sensitive -->\nAKIAABCDEFGHIJKLMNOP kb-allow-sensitive\n"
    )
    findings = [
        f for f in check_sensitive(load_catalog(kb_root, kb_config), kb_config) if f.path == "onboarding/README.md"
    ]
    infos = [f for f in findings if f.severity == "info"]
    assert infos and "allowlisted" in infos[0].message
    assert any(f.severity == "critical" for f in findings)  # the non-placeholder key with a bare marker
