"""Cancellation of running audits, reachable from another process via a marker file."""

from pathlib import Path

CANCEL_DIR = ".librarian/cancel"


class AuditTaskManager:
    """Registry of running audits plus a cancel flag (in memory and on disk)."""

    def __init__(self, cancel_dir: Path | None = None) -> None:
        self.cancel_dir = cancel_dir
        self._running: set[str] = set()
        self._cancelled: set[str] = set()

    def configure(self, root: Path) -> None:
        self.cancel_dir = root / CANCEL_DIR

    def _marker(self, audit_id: str) -> Path | None:
        return self.cancel_dir / audit_id if self.cancel_dir is not None else None

    def register(self, audit_id: str) -> None:
        self._running.add(audit_id)
        self._cancelled.discard(audit_id)
        marker = self._marker(audit_id)
        if marker is not None:
            marker.unlink(missing_ok=True)

    def unregister(self, audit_id: str) -> None:
        self._running.discard(audit_id)
        self._cancelled.discard(audit_id)
        marker = self._marker(audit_id)
        if marker is not None:
            marker.unlink(missing_ok=True)

    def running(self) -> list[str]:
        return sorted(self._running)

    def cancel(self, audit_id: str) -> bool:
        """Request cancellation. Returns False only when nothing can receive it."""
        marker = self._marker(audit_id)
        if audit_id not in self._running and marker is None:
            return False
        self._cancelled.add(audit_id)
        if marker is not None:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.touch()
        return True

    def is_cancelled(self, audit_id: str) -> bool:
        marker = self._marker(audit_id)
        return audit_id in self._cancelled or (marker is not None and marker.exists())


audit_task_manager = AuditTaskManager()
