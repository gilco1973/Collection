"""Chat telemetry: one JSON line per turn at ``.librarian/chat-log.jsonl``.

A line holds exactly ``ts, mode, lang, persona, sources, refused, cost_usd, duration_ms`` — the
shape of the turn, never its content: no question, no answer, no client address, no reader
identity. ``record`` appends one line under a process lock (a single ``O_APPEND`` write, so
concurrent workers never interleave); ``read`` yields the well-formed lines since a moment;
``prune`` rewrites the file atomically without the lines older than the retention period.
"""

import json
import os
import tempfile
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

LOG_FILE = ".librarian/chat-log.jsonl"
KEYS = ("ts", "mode", "lang", "persona", "sources", "refused", "cost_usd", "duration_ms")
_lock = threading.Lock()


def log_path(root: Path) -> Path:
    return root / LOG_FILE


def record(
    root: Path,
    *,
    mode: str,
    lang: str | None,
    persona: str | None,
    sources: list[str],
    refused: bool,
    cost_usd: float | None,
    duration_ms: int,
) -> None:
    """Append one line. Only the listed keys, in this order; ``sources`` is a list of page paths."""
    line = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": str(mode),
        "lang": None if lang is None else str(lang),
        "persona": None if persona is None else str(persona),
        "sources": [str(path) for path in sources],
        "refused": bool(refused),
        "cost_usd": None if cost_usd is None else float(cost_usd),
        "duration_ms": max(0, int(duration_ms)),
    }
    text = json.dumps(line, ensure_ascii=True) + "\n"
    path = log_path(root)
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()


def _parse(raw: str) -> tuple[dict, datetime] | None:
    """A line as a dict with an aware timestamp, or ``None`` for anything malformed."""
    try:
        line = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(line, dict) or not isinstance(line.get("ts"), str):
        return None
    try:
        ts = datetime.fromisoformat(line["ts"])
    except ValueError:
        return None
    if ts.tzinfo is None:
        return None
    return line, ts


def read(root: Path, since: datetime) -> Iterator[dict]:
    """The well-formed lines with a timestamp at or after ``since``; malformed lines are skipped."""
    path = log_path(root)
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as handle:
        for raw in handle:
            parsed = _parse(raw)
            if parsed is not None and parsed[1] >= since:
                yield parsed[0]


def prune(root: Path, days: int) -> int:
    """Drop every line older than ``days`` (and every malformed one); returns how many were dropped.

    The file is rewritten to a temp file next to it and swapped in with ``os.replace``, under the
    same lock ``record`` takes, so a turn recorded meanwhile lands after the swap, never inside it.
    """
    path = log_path(root)
    if not path.is_file():
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=days)
    with _lock:
        raw_lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        kept = [raw for raw in raw_lines if (parsed := _parse(raw)) is not None and parsed[1] >= cutoff]
        dropped = len(raw_lines) - len(kept)
        if not dropped:
            return 0
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".chat-log-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.writelines(kept)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    return dropped
