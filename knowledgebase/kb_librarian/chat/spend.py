"""The chat spend ledger: one JSON file of day-keyed totals at ``.librarian/chat-spend.json``.

It holds numbers only — never a message, a client address or an identity — keeps the last 31 days,
is written atomically (temp file + ``os.replace``), is serialised per process by a lock, and is
re-read on every call so a total another worker added is seen at once.
"""

import json
import logging
import math
import os
import tempfile
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

SPEND_FILE = ".librarian/chat-spend.json"
KEEP_DAYS = 31
log = logging.getLogger(__name__)
_ledgers: dict[Path, "SpendLedger"] = {}
_ledgers_lock = threading.Lock()


class SpendLedger:
    def __init__(self, path: Path, clock: Callable[[], datetime] | None = None) -> None:
        self.path = path
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()

    def _today(self) -> str:
        return self._clock().astimezone(UTC).strftime("%Y-%m-%d")

    def _load(self) -> dict[str, float]:
        """The file's day totals; an unreadable or malformed file counts as empty (and is logged)."""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            log.warning("chat spend ledger is unreadable (%s); treating it as empty", type(exc).__name__)
            return {}
        if not isinstance(raw, dict):
            log.warning("chat spend ledger is not an object; treating it as empty")
            return {}
        days = {
            day: float(total)
            for day, total in raw.items()
            if isinstance(day, str) and isinstance(total, int | float) and not isinstance(total, bool)
        }
        usable = {day: total for day, total in days.items() if math.isfinite(total) and total >= 0}
        if len(usable) != len(days):  # NaN/Infinity parse as JSON here; a negative total is not a spend
            log.warning("chat spend ledger: %d day total(s) dropped as non-finite or negative", len(days) - len(usable))
        return usable

    def _save(self, days: dict[str, float]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".chat-spend-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(days, handle, sort_keys=True)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def today_total(self) -> float:
        with self._lock:
            return self._load().get(self._today(), 0.0)

    def add(self, cost_usd: float) -> float:
        """Add a turn's cost to today's total and return the new total; older days beyond 31 are dropped."""
        if not isinstance(cost_usd, int | float) or not math.isfinite(cost_usd) or cost_usd < 0:
            raise ValueError("a chat cost must be a finite, non-negative number")
        with self._lock:
            today = self._today()
            cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=KEEP_DAYS - 1)).strftime("%Y-%m-%d")
            days = {day: total for day, total in self._load().items() if day >= cutoff}
            days[today] = days.get(today, 0.0) + float(cost_usd)
            self._save(days)
            return days[today]


def ledger_for(root: Path) -> SpendLedger:
    """One ledger — and so one lock — per knowledge-base root within the process."""
    path = root / SPEND_FILE
    with _ledgers_lock:
        if path not in _ledgers:
            _ledgers[path] = SpendLedger(path)
        return _ledgers[path]
