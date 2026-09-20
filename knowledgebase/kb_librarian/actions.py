"""Change application with content snapshots, compare-and-swap, and rollback.

Page text never enters the audit report: snapshots live under
``.librarian/snapshots/<action_id>.{before,after}`` and the report carries only
their SHA-256 hashes.
"""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from kb_librarian.models import AuditReport, LibrarianAction


def sha256(text: str | None) -> str | None:
    return None if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()


class ActionLog:
    """Applies page edits for one audit and records each as a rollback-able action."""

    def __init__(self, docs_root: Path, report: AuditReport, snapshots_dir: Path) -> None:
        self.docs_root = docs_root
        self.report = report
        self.snapshots_dir = snapshots_dir

    def _resolve(self, rel_path: str) -> Path:
        path = (self.docs_root / rel_path).resolve()
        if self.docs_root.resolve() not in path.parents:
            raise ValueError(f"refusing to write outside the docs root: {rel_path}")
        return path

    def _snapshot(self, action_id: str, kind: str, text: str | None) -> None:
        if text is None:
            return
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        (self.snapshots_dir / f"{action_id}.{kind}").write_text(text, encoding="utf-8")

    def _read_snapshot(self, action_id: str, kind: str) -> str | None:
        path = self.snapshots_dir / f"{action_id}.{kind}"
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def write_page(
        self,
        action_type: str,
        rel_path: str,
        new_text: str,
        description: str,
        *,
        expected_text: str | None = None,
    ) -> LibrarianAction:
        """Write ``new_text`` unless the audit is a dry run.

        ``expected_text`` is the content the caller rendered from; when the page
        has changed since, the write is refused (no lost updates). In dry-run the
        action is recorded with an ``after`` snapshot and nothing touches disk.
        """
        path = self._resolve(rel_path)
        before = path.read_text(encoding="utf-8") if path.exists() else None
        if expected_text is not None and before is not None and before != expected_text:
            raise ValueError(f"{rel_path} changed since it was read; reload and retry")
        action = LibrarianAction(
            audit_id=self.report.audit_id,
            action_type=action_type,
            path=rel_path,
            description=description,
            dry_run=self.report.dry_run,
            before_sha256=sha256(before),
            after_sha256=sha256(new_text),
        )
        self._snapshot(action.action_id, "before", before)
        self._snapshot(action.action_id, "after", new_text)
        if not self.report.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(new_text, encoding="utf-8")
        self.report.fixes_applied.append(action)
        return action

    def rollback(self, action_id: str, reason: str, *, force: bool = False) -> LibrarianAction:
        action = next((a for a in self.report.fixes_applied if a.action_id == action_id), None)
        if action is None:
            raise KeyError(f"no action '{action_id}' in audit {self.report.audit_id}")
        if action.dry_run:
            raise ValueError(f"action '{action_id}' was a dry-run proposal; nothing to roll back")
        if action.rolled_back:
            raise ValueError(f"action '{action_id}' is already rolled back")
        if action.before_sha256 is not None and self._read_snapshot(action_id, "before") is None:
            raise ValueError(f"snapshot for '{action_id}' is missing; cannot roll back")
        path = self._resolve(action.path)
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if not force and sha256(current) != action.after_sha256:
            raise ValueError(f"{action.path} has changed since action '{action_id}'; pass force to overwrite")
        before = self._read_snapshot(action_id, "before")
        if sha256(before) != action.before_sha256:
            raise ValueError(f"snapshot for '{action_id}' does not match its recorded hash; refusing to roll back")
        if before is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(before, encoding="utf-8")
        action.rolled_back = True
        action.rollback_timestamp = datetime.now(UTC)
        action.rollback_reason = reason
        action.rollback_forced = force
        return action
