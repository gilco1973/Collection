"""Findings, audit reports and actions, persisted as JSON under ``.librarian/reports``."""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

AuditStatus = Literal["in_progress", "completed", "failed", "cancelled"]
Severity = Literal["critical", "error", "warning", "info"]
SEVERITY_ORDER: dict[str, int] = {"critical": 0, "error": 1, "warning": 2, "info": 3}


def _now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class Finding(BaseModel):
    """One defect a check found in one file. ``line`` is file-relative (1-based)."""

    check: str
    severity: Severity
    path: str
    message: str
    fix_hint: str | None = None
    auto_fixable: bool = False
    line: int | None = None
    details: dict[str, str] = Field(default_factory=dict)


def sort_findings(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (SEVERITY_ORDER[f.severity], f.path, f.line or 0))


class ToolCall(BaseModel):
    """One tool invocation (or denial) recorded in the audit trail."""

    tool: str
    input: dict[str, Any] = Field(default_factory=dict)
    ok: bool = True
    summary: str = ""
    at: datetime = Field(default_factory=_now)


class LibrarianAction(BaseModel):
    """A change the librarian made (or, in dry-run, proposed) to one page or external system.

    Page contents are never stored here: ``before_sha256``/``after_sha256`` reference
    snapshots under ``.librarian/snapshots/`` that rollback reads.
    """

    action_id: str = Field(default_factory=lambda: new_id("act"))
    audit_id: str
    timestamp: datetime = Field(default_factory=_now)
    action_type: str
    path: str
    description: str
    dry_run: bool
    before_sha256: str | None = None
    after_sha256: str | None = None
    rolled_back: bool = False
    rollback_timestamp: datetime | None = None
    rollback_reason: str | None = None
    rollback_forced: bool = False


class ManualReviewItem(BaseModel):
    path: str
    reason: str
    severity: str = "warning"
    raised_by: str = "librarian"
    at: datetime = Field(default_factory=_now)


class AuditReport(BaseModel):
    audit_id: str = Field(default_factory=lambda: new_id("audit"))
    audit_type: Literal["offline", "agent"]
    audit_date: datetime = Field(default_factory=_now)
    status: AuditStatus = "in_progress"
    dry_run: bool = True
    capabilities: list[str] = Field(default_factory=list)
    reason: str | None = None
    requested_by: str | None = None

    findings: list[Finding] = Field(default_factory=list)
    fixes_applied: list[LibrarianAction] = Field(default_factory=list)
    manual_review_needed: list[ManualReviewItem] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)

    ai_summary: str | None = None
    total_cost_usd: float = 0.0
    num_turns: int = 0
    execution_time_seconds: float = 0.0
    error: str | None = None
    completed_at: datetime | None = None

    def summary(self) -> dict[str, Any]:
        by_severity: dict[str, int] = {}
        for finding in self.findings:
            by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1
        return {
            "audit_id": self.audit_id,
            "audit_type": self.audit_type,
            "status": self.status,
            "dry_run": self.dry_run,
            "issues_found": len(self.findings),
            "by_severity": by_severity,
            "fixes_applied": len([a for a in self.fixes_applied if not a.dry_run]),
            "fixes_proposed": len([a for a in self.fixes_applied if a.dry_run]),
            "manual_review_needed": len(self.manual_review_needed),
            "tool_calls": len(self.tool_calls),
            "denied_calls": len([c for c in self.tool_calls if not c.ok]),
            "total_cost_usd": round(self.total_cost_usd, 4),
            "num_turns": self.num_turns,
        }

    def finish(self, status: AuditStatus, error: str | None = None) -> None:
        self.status = status
        self.error = error
        self.completed_at = _now()
        self.execution_time_seconds = (self.completed_at - self.audit_date).total_seconds()
