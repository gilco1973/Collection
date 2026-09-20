"""``.librarian/insights/latest.json``: written atomically, read back as ``Insights`` (or ``None``)."""

import logging
import os
import tempfile
from pathlib import Path

from kb_librarian.insights.models import Insights

INSIGHTS_FILE = ".librarian/insights/latest.json"
log = logging.getLogger(__name__)


def insights_path(root: Path) -> Path:
    return root / INSIGHTS_FILE


def write(root: Path, insights: Insights) -> Path:
    path = insights_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".latest-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(insights.model_dump_json(indent=1))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def read(root: Path) -> Insights | None:
    """The stored insights; ``None`` when none were generated yet or the file does not parse (logged)."""
    path = insights_path(root)
    if not path.is_file():
        return None
    try:
        return Insights.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        log.warning("stored insights are unreadable (%s); treating them as absent", type(exc).__name__)
        return None
