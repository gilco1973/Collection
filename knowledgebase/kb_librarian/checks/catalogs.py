"""YAML catalogs (videos, resources): required fields, dates, URL hosts."""

from datetime import date
from urllib.parse import urlsplit

import yaml

from kb_librarian.catalog.catalog import Catalog
from kb_librarian.checks.base import Finding
from kb_librarian.checks.frontmatter_check import parse_reviewed
from kb_librarian.kbconfig import CatalogConfig, KbConfig

CHECK = "catalogs"


def _finding(path: str, message: str, severity: str = "error") -> Finding:
    return Finding(check=CHECK, severity=severity, path=path, message=message)  # type: ignore[arg-type]


def _check_entry(index: int, entry: dict, spec: CatalogConfig, config: KbConfig) -> list[Finding]:
    findings: list[Finding] = []
    for field in spec.required_fields:
        if entry.get(field) in (None, "", []):
            findings.append(_finding(spec.path, f"entry {index}: missing required field '{field}'"))
    for field in spec.date_fields:
        if field in entry and parse_reviewed(entry[field]) is None:
            findings.append(_finding(spec.path, f"entry {index}: '{field}' is not an ISO date"))
    for field in spec.url_fields:
        url = entry.get(field)
        if not url:
            continue
        parts = urlsplit(str(url))
        host = parts.hostname or ""
        if parts.scheme != "https":
            findings.append(_finding(spec.path, f"entry {index}: '{field}' must be an https URL"))
        elif spec.allowed_hosts and host not in spec.allowed_hosts:
            findings.append(_finding(spec.path, f"entry {index}: host '{host}' is not in allowed_hosts"))
        elif not spec.allowed_hosts and host not in config.links.trusted_hosts:
            findings.append(_finding(spec.path, f"entry {index}: host '{host}' is not in links.trusted_hosts", "info"))
    return findings


def check_catalogs(catalog: Catalog, config: KbConfig, today: date | None = None) -> list[Finding]:
    findings: list[Finding] = []
    for spec in config.catalogs:
        path = catalog.docs_root / spec.path
        if not path.is_file():
            findings.append(_finding(spec.path, "catalog file is missing"))
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            findings.append(_finding(spec.path, f"catalog YAML is invalid: {str(exc).splitlines()[0]}"))
            continue
        entries = data.get("entries") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            findings.append(_finding(spec.path, "catalog must be a mapping with an 'entries' list"))
            continue
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                findings.append(_finding(spec.path, f"entry {index}: must be a mapping"))
                continue
            findings.extend(_check_entry(index, entry, spec, config))
    return findings
