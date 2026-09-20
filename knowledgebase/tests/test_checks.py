"""Every check is proven against the planted fixture defects."""

from kb_librarian.checks import run_all_checks
from kb_librarian.checks.freshness import check_freshness
from kb_librarian.checks.frontmatter_check import check_frontmatter
from kb_librarian.checks.links import check_links
from kb_librarian.checks.sensitive import check_sensitive
from kb_librarian.checks.structure import check_structure
from tests.conftest import TODAY


def _paths(findings, check):
    return sorted({f.path for f in findings if f.check == check})


def test_frontmatter_check_flags_missing_block_and_unknown_tag(catalog, kb_config):
    findings = check_frontmatter(catalog, kb_config)
    assert "governance/README.md" in _paths(findings, "frontmatter")
    unknown = [f for f in findings if "not-a-real-tag" in f.message]
    assert unknown and unknown[0].path == "onboarding/stale.md"


def test_freshness_flags_only_the_stale_page(catalog, kb_config):
    findings = check_freshness(catalog, kb_config, today=TODAY)
    assert _paths(findings, "freshness") == ["onboarding/stale.md"]
    assert findings[0].auto_fixable is False


def test_links_offline_flags_broken_internal_only(catalog, kb_config):
    findings = check_links(catalog, kb_config, offline=True)
    assert _paths(findings, "links") == ["onboarding/stale.md"]
    assert "does-not-exist.md" in findings[0].message


def test_links_offline_reports_untrusted_external_host(kb_root, kb_config):
    page = kb_root / "docs" / "onboarding" / "README.md"
    page.write_text(page.read_text() + "\nSee [x](https://untrusted.example.com/page).\n")
    from kb_librarian.catalog.catalog import load_catalog

    findings = check_links(load_catalog(kb_root, kb_config), kb_config, offline=True)
    hosts = [f for f in findings if "untrusted.example.com" in f.message]
    assert hosts and hosts[0].severity == "info"


def test_sensitive_flags_aws_key(catalog, kb_config):
    findings = check_sensitive(catalog, kb_config)
    assert _paths(findings, "sensitive") == ["onboarding/stale.md"]
    assert findings[0].severity == "critical"
    assert "AKIAIOSFODNN7EXAMPLE" not in findings[0].message


def test_structure_requires_section_readmes_and_index_links(kb_root, kb_config):
    (kb_root / "docs" / "governance" / "README.md").unlink()
    from kb_librarian.catalog.catalog import load_catalog

    findings = check_structure(load_catalog(kb_root, kb_config), kb_config)
    messages = " ".join(f.message for f in findings)
    assert "governance" in messages and "README.md" in messages


def test_run_all_checks_orders_by_severity(catalog, kb_config):
    findings = run_all_checks(catalog, kb_config, today=TODAY, offline=True)
    severities = [f.severity for f in findings]
    order = {"critical": 0, "error": 1, "warning": 2, "info": 3}
    assert severities == sorted(severities, key=order.__getitem__)
    assert {f.check for f in findings} >= {"frontmatter", "freshness", "links", "sensitive"}


def test_malformed_frontmatter_is_reported_as_invalid_not_missing(kb_root, kb_config):
    page = kb_root / "docs" / "onboarding" / "bad.md"
    page.write_text("---\ntitle: Tutorial 1: unquoted colon\nowner: x\n---\n# Bad\n")
    from kb_librarian.catalog.catalog import load_catalog

    findings = check_frontmatter(load_catalog(kb_root, kb_config), kb_config)
    mine = [f for f in findings if f.path == "onboarding/bad.md"]
    assert len(mine) == 1
    assert "invalid" in mine[0].message and "missing" not in mine[0].message
