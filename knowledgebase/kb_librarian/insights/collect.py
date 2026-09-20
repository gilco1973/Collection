"""The collector: per readable page, what reader records, problem reports and chat telemetry say about
it inside a window — as counts and rates under k-anonymity. It never lists a reader, a message or a
problem's text, and a withheld page never appears.

Reader records are enumerated through ``profile.retention.records`` (regular files only, symlinks
never followed) and a record that does not parse is skipped, as the purge does. Every source is
filtered by the window on its own timestamp: a page visit by its ``last_at``, a quiz result and a
problem report by their ``at``, a telemetry line by its ``ts``.
"""

import json
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from kb_librarian.catalog.catalog import Catalog
from kb_librarian.chat import telemetry
from kb_librarian.insights.models import Insights, PageInsight
from kb_librarian.kbconfig import KbConfig
from kb_librarian.profile.models import Profile
from kb_librarian.profile.retention import records
from kb_librarian.profile.store import USERS_DIR

DEFAULT_WINDOW_DAYS = 30
PROBLEMS_DIR = ".librarian/problems"
DEFAULT_LANG = "en"  # a turn without ``lang`` was answered from the English catalog


@dataclass
class _Tally:
    views: int = 0
    readers: int = 0
    problems: Counter = field(default_factory=Counter)
    attempts: int = 0
    fails: int = 0
    citations: int = 0

    def any(self) -> bool:
        return bool(self.readers or self.problems or self.attempts or self.citations)


def _in_window(at: datetime | None, since: datetime) -> bool:
    return at is not None and at.tzinfo is not None and at >= since


def _profiles(root: Path) -> Iterator[Profile]:
    for path in records(root / USERS_DIR):
        try:
            yield Profile.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue


def _tally_records(root: Path, readable: set[str], since: datetime, tallies: dict[str, _Tally]) -> None:
    for profile in _profiles(root):
        for path, visit in profile.viewed.items():
            if path in readable and _in_window(visit.last_at, since):
                tallies[path].views += visit.count
                tallies[path].readers += 1
        for quiz in profile.quizzes:
            if quiz.path in readable and _in_window(quiz.at, since):
                tallies[quiz.path].attempts += 1
                tallies[quiz.path].fails += quiz.score < quiz.total


def _problem_at(raw: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(str(raw.get("at", "")))
    except ValueError:
        return None


def _tally_problems(root: Path, readable: set[str], since: datetime, tallies: dict[str, _Tally]) -> None:
    directory = root / PROBLEMS_DIR
    if not directory.is_dir():
        return
    for file in sorted(directory.glob("problem-*.json")):
        if file.is_symlink() or not file.is_file():
            continue
        try:
            raw = json.loads(file.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if not isinstance(raw, dict) or not _in_window(_problem_at(raw), since):
            continue
        path, category = raw.get("path"), raw.get("category")
        if path in readable and isinstance(category, str) and category:
            tallies[path].problems[category] += 1


def _tally_telemetry(root: Path, readable: set[str], since: datetime, tallies: dict[str, _Tally]) -> dict:
    by_mode: Counter = Counter()
    by_lang: Counter = Counter()
    for line in telemetry.read(root, since):
        sources = line.get("sources")
        for path in dict.fromkeys(sources if isinstance(sources, list) else []):
            if path in readable:
                tallies[path].citations += 1
        if line.get("refused") is True:
            by_mode[str(line.get("mode") or "ask")] += 1
            by_lang[str(line.get("lang") or DEFAULT_LANG)] += 1
    return {"mode": dict(by_mode), "lang": dict(by_lang)}


def _page_insight(tally: _Tally, k: int) -> PageInsight:
    """Below ``k`` readers every number derived from reader records is withheld; the rest stays."""
    insight = PageInsight(problems=dict(tally.problems), chat_citations=tally.citations)
    if tally.readers < k:
        return insight
    insight.views, insight.readers, insight.quiz_attempts = tally.views, tally.readers, tally.attempts
    insight.quiz_fail_rate = round(tally.fails / tally.attempts, 4) if tally.attempts else None
    return insight


def collect(
    root: Path, config: KbConfig, catalog: Catalog, withheld: set[str], *, k: int, window_days: int, now: datetime
) -> Insights:
    """Aggregate the last ``window_days`` for every page of ``catalog`` that is not in ``withheld``.
    A page appears only when something was recorded about it; ``suppressed`` counts the pages that
    appear with their reader-derived numbers withheld (fewer than ``k`` distinct readers)."""
    del config  # the contract is not consulted yet: reserved for section-level roll-ups
    readable = {doc.rel_path for doc in catalog.documents if doc.rel_path not in withheld and not doc.sensitive}
    since = now - timedelta(days=window_days)
    tallies: dict[str, _Tally] = defaultdict(_Tally)
    _tally_records(root, readable, since, tallies)
    _tally_problems(root, readable, since, tallies)
    unanswered = _tally_telemetry(root, readable, since, tallies)
    pages = {path: _page_insight(tally, k) for path, tally in sorted(tallies.items()) if tally.any()}
    suppressed = sum(1 for path in pages if tallies[path].readers < k)
    return Insights(
        generated_at=now, k=k, window_days=window_days, pages=pages, unanswered=unanswered, suppressed=suppressed
    )
