"""Freshness: a page is stale when its review window has elapsed."""

from datetime import date, timedelta

from kb_librarian.catalog.catalog import Catalog
from kb_librarian.checks.base import Finding
from kb_librarian.checks.frontmatter_check import parse_reviewed
from kb_librarian.kbconfig import KbConfig

CHECK = "freshness"


def review_window(doc, config: KbConfig) -> int:
    """Days between reviews for ``doc``: page override (if allowed and a real positive int) → section → default."""
    section = config.section_by_id(doc.section_id) if doc.section_id else None
    window = section.review_every_days if section else config.freshness.default_days
    override = doc.meta.get("review_every_days")
    if (
        config.freshness.allow_page_override
        and isinstance(override, int)
        and not isinstance(override, bool)
        and override > 0
    ):
        window = override
    return window


def check_freshness(catalog: Catalog, config: KbConfig, today: date | None = None) -> list[Finding]:
    today = today or date.today()
    findings: list[Finding] = []
    for doc in catalog.documents:
        reviewed = parse_reviewed(doc.meta.get("reviewed"))
        if reviewed is None or doc.meta.get("status") == "deprecated":
            continue
        window = review_window(doc, config)
        due = reviewed + timedelta(days=window)
        if due < today:
            overdue = (today - due).days
            findings.append(
                Finding(
                    check=CHECK,
                    severity="warning" if overdue <= window else "error",
                    path=doc.rel_path,
                    message=(
                        f"stale: last reviewed {reviewed.isoformat()}, due {due.isoformat()} ({overdue} days overdue)"
                    ),
                    fix_hint=f"owner '{doc.meta.get('owner', 'unknown')}' re-reviews the page and bumps 'reviewed'",
                    auto_fixable=False,
                    details={"owner": str(doc.meta.get("owner", "")), "due": due.isoformat()},
                )
            )
    return findings
