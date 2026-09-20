"""kb_librarian/insights: the collector (counts under k-anonymity, withheld pages absent, the window) and the store."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kb_librarian.chat import telemetry
from kb_librarian.insights import store
from kb_librarian.insights.collect import collect
from kb_librarian.insights.models import Insights, PageInsight
from kb_librarian.profile.store import PageVisit, Profile, ProfileStore, QuizResult

A, B, WITHHELD = "onboarding/README.md", "governance/README.md", "onboarding/stale.md"
NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
OLD = NOW - timedelta(days=60)


def _problem(root: Path, n: int, path: str, category: str, at: datetime) -> None:
    problems = root / ".librarian" / "problems"
    problems.mkdir(parents=True, exist_ok=True)
    record = {"id": f"problem-{n:012x}", "path": path, "owner": "x", "category": category, "message": "m" * 10}
    record["at"] = at.isoformat()
    (problems / f"problem-{n:012x}.json").write_text(json.dumps(record, indent=1), encoding="utf-8")


def _line(root: Path, *, ts: datetime | None = None, **over) -> None:
    line = {"mode": "ask", "lang": None, "persona": None, "sources": [], "refused": False, "cost_usd": 0.0}
    line["duration_ms"] = 1
    telemetry.record(root, **{**line, **over})
    if ts is not None:  # backdate the line just written
        path = telemetry.log_path(root)
        lines = path.read_text(encoding="utf-8").splitlines()
        lines[-1] = json.dumps({**json.loads(lines[-1]), "ts": ts.isoformat()})
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def populated(kb_root: Path) -> Path:
    profiles = ProfileStore(kb_root)
    for n in range(6):  # six readers of A, one of them twice; four of them also read the withheld page
        profiles.record_view(f"a{n}", A)
        if n < 4:
            profiles.record_view(f"a{n}", WITHHELD)
    profiles.record_view("a0", A)
    for n in range(4):  # four readers of B: below k
        profiles.record_view(f"b{n}", B)
    for n, score in enumerate((3, 3, 1)):  # A: three attempts, one failed
        profiles.record_quiz(f"a{n}", QuizResult(path=A, score=score, total=3))
    for n in range(2):  # B: two failed attempts
        profiles.record_quiz(f"b{n}", QuizResult(path=B, score=0, total=3))
    profiles.record_quiz("a5", QuizResult(path=WITHHELD, score=0, total=3))
    profiles.save(Profile(sub="a-old", viewed={A: PageVisit(first_at=OLD, last_at=OLD, count=5)}))  # outside the window
    profiles.save(Profile(sub="a-quiz-old", quizzes=[QuizResult(path=A, at=OLD, score=0, total=3)]))
    (profiles.dir / "broken.json").write_text("{not json", encoding="utf-8")
    reports = [(A, "outdated", NOW), (A, "outdated", NOW), (A, "unclear", NOW), (B, "incorrect", NOW)]
    for n, (path, category, at) in enumerate([*reports, (WITHHELD, "other", NOW), (A, "unclear", OLD)]):
        _problem(kb_root, n, path, category, at)
    (kb_root / ".librarian" / "problems" / "problem-broken.json").write_text("nope", encoding="utf-8")
    _line(kb_root, sources=[A])
    _line(kb_root, sources=[A, WITHHELD], mode="explain", lang="es")
    _line(kb_root, refused=True, lang="es")
    _line(kb_root, refused=True, mode="quiz")
    _line(kb_root, refused=True, ts=OLD)
    _line(kb_root, sources=[A], ts=OLD)
    return kb_root


def _collect(root: Path, **over) -> Insights:
    from kb_librarian.catalog.catalog import load_catalog
    from kb_librarian.kbconfig import load_kb_config

    config = load_kb_config(root / "kb.config.yaml")
    args = dict(k=5, window_days=30, now=NOW)
    return collect(root, config, load_catalog(root, config), {WITHHELD}, **{**args, **over})


def test_collector_reports_a_six_reader_page_and_suppresses_a_four_reader_one(populated: Path):
    insights = _collect(populated)
    assert insights.k == 5 and insights.window_days == 30 and insights.generated_at == NOW
    reported = PageInsight(views=7, readers=6, problems={"outdated": 2, "unclear": 1}, quiz_attempts=3)
    assert insights.pages[A] == reported.model_copy(update={"quiz_fail_rate": 0.3333, "chat_citations": 2})
    assert insights.pages[B] == PageInsight(problems={"incorrect": 1}, chat_citations=0)
    assert insights.pages[B].model_dump() == {**insights.pages[B].model_dump(), "views": None, "readers": None}
    assert insights.pages[B].quiz_attempts is None and insights.pages[B].quiz_fail_rate is None
    assert insights.suppressed == 1
    assert insights.unanswered == {"mode": {"ask": 1, "quiz": 1}, "lang": {"es": 1, "en": 1}}


def test_withheld_pages_and_pages_without_activity_never_appear(populated: Path):
    insights = _collect(populated)
    assert WITHHELD not in insights.pages and "index.md" not in insights.pages
    assert WITHHELD not in insights.model_dump_json()
    assert set(insights.pages) == {A, B}


def test_k_is_the_threshold_exactly(populated: Path):
    assert _collect(populated, k=6).pages[A].readers == 6 and _collect(populated, k=6).suppressed == 1
    at_seven = _collect(populated, k=7)
    assert at_seven.pages[A].readers is None and at_seven.pages[A].views is None and at_seven.suppressed == 2
    assert at_seven.pages[A].problems == {"outdated": 2, "unclear": 1} and at_seven.pages[A].chat_citations == 2


def test_the_window_widens_to_take_older_activity(populated: Path):
    wide = _collect(populated, window_days=90)
    assert wide.pages[A].views == 12 and wide.pages[A].readers == 7 and wide.pages[A].quiz_attempts == 4
    assert wide.pages[A].problems == {"outdated": 2, "unclear": 2} and wide.pages[A].chat_citations == 3
    assert wide.unanswered["mode"] == {"ask": 2, "quiz": 1}


def test_an_empty_state_directory_yields_no_pages(kb_root: Path):
    insights = _collect(kb_root)
    assert insights.pages == {} and insights.suppressed == 0 and insights.unanswered == {"mode": {}, "lang": {}}


def test_store_round_trips_json_and_reads_none_when_missing_or_broken(populated: Path):
    assert store.read(populated) is None
    insights = _collect(populated)
    store.write(populated, insights)
    path = populated / ".librarian" / "insights" / "latest.json"
    assert path.is_file() and not list(path.parent.glob("*.tmp"))
    assert store.read(populated) == insights
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert set(raw) == {"generated_at", "k", "window_days", "pages", "unanswered", "suppressed"}
    assert set(raw["pages"][A]) == {"views", "readers", "problems", "quiz_attempts", "quiz_fail_rate", "chat_citations"}
    path.write_text("{broken", encoding="utf-8")
    assert store.read(populated) is None
