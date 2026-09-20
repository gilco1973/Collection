"""Frontmatter contract: required fields, enumerations, taxonomy tags, dates."""

from datetime import date, datetime

from kb_librarian.catalog.catalog import Catalog, Document
from kb_librarian.checks.base import Finding
from kb_librarian.kbconfig import KbConfig

CHECK = "frontmatter"


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def parse_reviewed(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def _raw_title_line(doc: Document) -> str | None:
    if not doc.body_offset:
        return None
    for line in doc.path.read_text(encoding="utf-8").splitlines()[: doc.body_offset]:
        if line.startswith("title:"):
            return line
    return None


def _check_document(doc: Document, config: KbConfig) -> list[Finding]:
    if doc.frontmatter_error:
        return [
            Finding(
                check=CHECK,
                severity="error",
                path=doc.rel_path,
                message=f"frontmatter YAML is invalid: {doc.frontmatter_error}",
                fix_hint="quote values containing ':' or '#'; check indentation",
            )
        ]
    if not doc.has_frontmatter:
        return [
            Finding(
                check=CHECK,
                severity="error",
                path=doc.rel_path,
                message="missing frontmatter block",
                fix_hint="add a frontmatter block with " + ", ".join(config.frontmatter.required),
                auto_fixable=True,
            )
        ]
    findings: list[Finding] = []
    for field in config.frontmatter.required:
        if field not in doc.meta or doc.meta[field] in (None, "", []):
            findings.append(
                Finding(
                    check=CHECK,
                    severity="error",
                    path=doc.rel_path,
                    message=f"missing required field '{field}'",
                    auto_fixable=field in ("reviewed", "status"),
                )
            )
    status = doc.meta.get("status")
    if status is not None and status not in config.frontmatter.status_values:
        findings.append(
            Finding(
                check=CHECK,
                severity="error",
                path=doc.rel_path,
                message=f"status '{status}' not in {config.frontmatter.status_values}",
            )
        )
    for audience in _as_list(doc.meta.get("audience")):
        if audience not in config.frontmatter.audience_values:
            findings.append(
                Finding(
                    check=CHECK,
                    severity="warning",
                    path=doc.rel_path,
                    message=f"audience '{audience}' not in {config.frontmatter.audience_values}",
                )
            )
    for tag in _as_list(doc.meta.get("tags")):
        if tag not in config.taxonomy.tags:
            findings.append(
                Finding(
                    check=CHECK,
                    severity="warning",
                    path=doc.rel_path,
                    message=f"tag '{tag}' is not in the taxonomy",
                    fix_hint="use an existing tag or propose a taxonomy change in governance",
                )
            )
    raw_title = _raw_title_line(doc)
    if raw_title and " #" in raw_title and not raw_title.split(":", 1)[1].strip().startswith(("'", '"')):
        findings.append(
            Finding(
                check=CHECK,
                severity="warning",
                path=doc.rel_path,
                message="title contains an unquoted '#' and is truncated by YAML; quote the title",
            )
        )
    override = doc.meta.get("review_every_days")
    if override is not None and (not isinstance(override, int) or isinstance(override, bool) or override <= 0):
        findings.append(
            Finding(
                check=CHECK,
                severity="error",
                path=doc.rel_path,
                message=f"'review_every_days' must be a positive integer, got {override!r}",
            )
        )
    if "reviewed" in doc.meta and parse_reviewed(doc.meta["reviewed"]) is None:
        findings.append(
            Finding(
                check=CHECK,
                severity="error",
                path=doc.rel_path,
                message="'reviewed' is not an ISO date (YYYY-MM-DD)",
                auto_fixable=True,
            )
        )
    return findings


def check_frontmatter(catalog: Catalog, config: KbConfig) -> list[Finding]:
    findings: list[Finding] = []
    for doc in catalog.documents:
        findings.extend(_check_document(doc, config))
    return findings
