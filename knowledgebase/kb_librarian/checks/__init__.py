"""Deterministic checks the librarian runs before (and without) any LLM."""

from datetime import date

import httpx

from kb_librarian.catalog.catalog import Catalog
from kb_librarian.checks.base import Finding, sort_findings
from kb_librarian.checks.catalogs import check_catalogs
from kb_librarian.checks.freshness import check_freshness
from kb_librarian.checks.frontmatter_check import check_frontmatter
from kb_librarian.checks.links import check_links
from kb_librarian.checks.sensitive import check_sensitive
from kb_librarian.checks.structure import check_structure
from kb_librarian.kbconfig import KbConfig

__all__ = ["Finding", "run_all_checks", "sort_findings"]


def run_all_checks(
    catalog: Catalog,
    config: KbConfig,
    today: date | None = None,
    offline: bool = True,
    client: httpx.Client | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(check_structure(catalog, config))
    findings.extend(check_frontmatter(catalog, config))
    findings.extend(check_freshness(catalog, config, today=today))
    findings.extend(check_links(catalog, config, offline=offline, client=client))
    findings.extend(check_sensitive(catalog, config))
    findings.extend(check_catalogs(catalog, config, today=today))
    return sort_findings(findings)
