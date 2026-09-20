"""Persistence and rendering of audit reports. Everything saved is redacted first."""

import json
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from kb_librarian.checks.sensitive import redact
from kb_librarian.models import AuditReport


def _redact_tree(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [_redact_tree(v) for v in value]
    if isinstance(value, dict):
        return {k: _redact_tree(v) for k, v in value.items()}
    return value


def sanitized(report: AuditReport) -> AuditReport:
    """A copy with every string leaf passed through the sensitive-content redactor."""
    return AuditReport.model_validate(_redact_tree(report.model_dump(mode="json")))


def report_summary(report: AuditReport) -> dict[str, Any]:
    """The list/detail summary the API serves; computed once per file by the index."""
    return {
        **report.summary(),
        "audit_date": report.audit_date.isoformat(),
        "completed_at": report.completed_at.isoformat() if report.completed_at else None,
        "capabilities": report.capabilities,
        "error": report.error,
        "reason": report.reason,
        "requested_by": report.requested_by,
    }


@dataclass(frozen=True)
class ReportEntry:
    audit_id: str
    status: str
    audit_date: datetime
    completed_at: datetime | None
    dry_run: bool
    audit_type: str
    summary: dict[str, Any]
    stamp: tuple[int, int]  # (st_mtime_ns, st_size): survives coarse-mtime filesystems


class ReportStore:
    def __init__(self, reports_dir: Path) -> None:
        self.reports_dir = reports_dir
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, ReportEntry] = {}
        self._lock = threading.Lock()
        self._latest: tuple[str, tuple[int, int], AuditReport] | None = None  # (id, stamp, report)

    def _json_path(self, audit_id: str) -> Path:
        return self.reports_dir / f"{audit_id}.json"

    def save(self, report: AuditReport) -> Path:
        clean = sanitized(report)
        path = self._json_path(report.audit_id)
        path.write_text(clean.model_dump_json(indent=2), encoding="utf-8")
        (self.reports_dir / f"{report.audit_id}.md").write_text(render_markdown(clean), encoding="utf-8")
        with self._lock:
            self._index.pop(report.audit_id, None)
        return path

    def load(self, audit_id: str) -> AuditReport:
        path = self._json_path(audit_id)
        if not path.is_file():
            raise FileNotFoundError(f"no report '{audit_id}' in {self.reports_dir}")
        return AuditReport.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def entries(self) -> list[ReportEntry]:
        """Every readable report's index entry, newest ``audit_date`` first; re-read only when a file changes."""
        with self._lock:
            seen: set[str] = set()
            for path in self.reports_dir.glob("*.json"):
                st = path.stat()
                stamp = (st.st_mtime_ns, st.st_size)
                cached = self._index.get(path.stem)
                if cached is None or cached.stamp != stamp:
                    try:
                        report = self.load(path.stem)
                    except (ValueError, OSError):
                        continue  # a corrupt or half-written file never takes the index down
                    cached = ReportEntry(
                        report.audit_id,
                        report.status,
                        report.audit_date,
                        report.completed_at,
                        report.dry_run,
                        report.audit_type,
                        report_summary(report),
                        stamp,
                    )
                    self._index[path.stem] = cached
                seen.add(path.stem)
            for stale in set(self._index) - seen:
                self._index.pop(stale, None)
            return sorted(self._index.values(), key=lambda e: e.audit_date, reverse=True)

    def list_ids(self, limit: int | None = None) -> list[str]:
        ids = [e.audit_id for e in self.entries()]
        return ids[:limit] if limit else ids

    def latest(self) -> AuditReport | None:
        ids = self.list_ids(limit=1)
        return self.load(ids[0]) if ids else None

    def latest_completed(self) -> AuditReport | None:
        """The newest completed report, parsed once per index stamp (it is consulted on every page request)."""
        for entry in self.entries():
            if entry.status == "completed":
                cached = self._latest
                if cached is None or cached[0] != entry.audit_id or cached[1] != entry.stamp:
                    cached = (entry.audit_id, entry.stamp, self.load(entry.audit_id))
                    self._latest = cached
                return cached[2]
        return None


def render_markdown(report: AuditReport) -> str:
    summary = report.summary()
    lines = [
        f"# Librarian audit {report.audit_id}",
        "",
        f"- Type: {report.audit_type} | Status: {report.status} | Mode: {'DRY RUN' if report.dry_run else 'LIVE'}",
        f"- Date: {report.audit_date.isoformat()} | Turns: {report.num_turns} | Cost: ${report.total_cost_usd:.4f}",
        f"- Findings: {summary['issues_found']} {summary['by_severity']}",
        f"- Fixes applied: {summary['fixes_applied']} | proposed: {summary['fixes_proposed']} "
        f"| manual review: {summary['manual_review_needed']} | denied tool calls: {summary['denied_calls']}",
        "",
    ]
    if report.reason:
        lines += [f"- Requested by: {report.requested_by or 'unknown'} — reason: {report.reason}", ""]
    if report.error:
        lines += ["## Error", "", f"```\n{report.error}\n```", ""]
    if report.ai_summary:
        lines += ["## Librarian summary", "", report.ai_summary, ""]
    lines += ["## Findings", ""]
    if not report.findings:
        lines.append("_None._")
    for finding in report.findings:
        location = f"{finding.path}:{finding.line}" if finding.line else finding.path
        lines.append(f"- **{finding.severity}** `{finding.check}` {location} — {finding.message}")
    lines += ["", "## Actions", ""]
    if not report.fixes_applied:
        lines.append("_None._")
    for action in report.fixes_applied:
        mode = "proposed" if action.dry_run else ("rolled back" if action.rolled_back else "applied")
        lines.append(f"- `{action.action_id}` {action.action_type} {action.path} ({mode}) — {action.description}")
    lines += ["", "## Manual review", ""]
    if not report.manual_review_needed:
        lines.append("_None._")
    for item in report.manual_review_needed:
        lines.append(f"- **{item.severity}** {item.path} — {item.reason}")
    denied = [c for c in report.tool_calls if not c.ok]
    if denied:
        lines += ["", "## Denied or failed tool calls", ""]
        lines += [f"- `{c.tool}` — {c.summary}" for c in denied]
    return "\n".join(lines) + "\n"
