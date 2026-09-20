"""Finding model shared by every check (defined in ``models`` so reports do not depend on checks)."""

from kb_librarian.models import SEVERITY_ORDER, Finding, Severity, sort_findings

__all__ = ["SEVERITY_ORDER", "Finding", "Severity", "sort_findings"]
