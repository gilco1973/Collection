"""``kb-librarian insights [--json] [--window-days N]`` and ``insights prune``: paths and numbers only."""

import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from kb_librarian import cli
from kb_librarian.chat import telemetry
from kb_librarian.insights import store
from tests.test_insights import WITHHELD, A, B, populated  # noqa: F401  (the shared fixture)


def _run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    code = cli.main(list(argv), out=out)
    return code, out.getvalue()


def test_insights_writes_the_file_and_prints_top_pages_and_unanswered_counts(populated: Path):  # noqa: F811
    code, out = _run("--root", str(populated), "insights")
    assert code == 0, out
    stored = store.read(populated)
    assert stored is not None and stored.k == 5 and stored.window_days == 30 and set(stored.pages) == {A, B}
    lines = out.splitlines()
    by_problems = lines.index("Top pages by problem reports:")
    assert lines[by_problems + 1].split() == ["3", A, "outdated=2", "unclear=1"]
    assert lines[by_problems + 2].split() == ["1", B, "incorrect=1"]
    by_fail = lines.index("Top pages by quiz fail rate:")
    assert lines[by_fail + 1].split() == ["0.33", A, "attempts=3"]
    assert lines[by_fail + 2].startswith("Unanswered")  # B is below k: no rate, no row
    assert "ask=1 quiz=1" in out and "en=1 es=1" in out and "suppressed=1" in out
    assert WITHHELD not in out and "mmmmmmmmmm" not in out and "a0" not in out  # no withheld page, message or reader


def test_insights_json_and_window(populated: Path):  # noqa: F811
    code, out = _run("--root", str(populated), "insights", "--json", "--window-days", "90")
    assert code == 0
    data = json.loads(out)
    assert set(data) == {"generated_at", "k", "window_days", "pages", "unanswered", "suppressed"}
    assert data["window_days"] == 90 and data["pages"][A]["readers"] == 7 and data["pages"][B]["readers"] is None
    assert store.read(populated).window_days == 90


def test_insights_on_an_empty_state_directory(kb_root: Path):
    code, out = _run("--root", str(kb_root), "insights")
    assert code == 0 and "pages=0" in out and "Top pages by problem reports:" in out


def test_insights_prune_uses_the_configured_retention(kb_root: Path, monkeypatch):
    now = datetime.now(UTC)
    line = dict(mode="ask", lang=None, persona=None, sources=[], refused=True, cost_usd=None, duration_ms=1)
    telemetry.record(kb_root, **line)
    path = telemetry.log_path(kb_root)
    fresh = path.read_text(encoding="utf-8")
    old = json.dumps({**json.loads(fresh), "ts": (now - timedelta(days=100)).isoformat()}) + "\n"
    path.write_text(old + old + fresh, encoding="utf-8")
    monkeypatch.setenv("KB_CHAT_LOG_DAYS", "120")
    code, out = _run("--root", str(kb_root), "insights", "prune")
    assert code == 0 and "removed=0" in out and "older_than_days=120" in out
    monkeypatch.setenv("KB_CHAT_LOG_DAYS", "90")
    code, out = _run("--root", str(kb_root), "insights", "prune")
    assert code == 0 and "removed=2" in out and "older_than_days=90" in out
    assert path.read_text(encoding="utf-8") == fresh
