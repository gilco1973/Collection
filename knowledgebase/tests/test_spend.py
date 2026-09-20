"""The chat spend ledger: day-keyed totals, rollover, pruning, atomic writes, locking."""

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kb_librarian.chat.spend import SPEND_FILE, SpendLedger, ledger_for


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def test_ledger_starts_empty_and_sums_todays_costs(tmp_path: Path):
    ledger = SpendLedger(tmp_path / "chat-spend.json")
    assert ledger.today_total() == 0.0
    assert ledger.add(0.25) == 0.25
    assert ledger.add(0.5) == pytest.approx(0.75)
    assert ledger.today_total() == pytest.approx(0.75)
    assert SpendLedger(tmp_path / "chat-spend.json").today_total() == pytest.approx(0.75)  # persisted, not cached


def test_ledger_rolls_over_at_midnight_utc(tmp_path: Path):
    clock = Clock(datetime(2026, 9, 18, 23, 59, tzinfo=UTC))
    ledger = SpendLedger(tmp_path / "s.json", clock=clock)
    ledger.add(1.0)
    clock.now += timedelta(minutes=2)
    assert ledger.today_total() == 0.0
    ledger.add(0.1)
    assert json.loads((tmp_path / "s.json").read_text()) == {"2026-09-18": 1.0, "2026-09-19": 0.1}


def test_ledger_keeps_only_the_last_31_days(tmp_path: Path):
    clock = Clock(datetime(2026, 9, 19, 12, 0, tzinfo=UTC))
    ledger = SpendLedger(tmp_path / "s.json", clock=clock)
    ledger.add(0.1)
    clock.now += timedelta(days=30)  # 2026-10-19: the 09-19 entry is exactly 31 days of history, kept
    ledger.add(0.2)
    assert set(json.loads((tmp_path / "s.json").read_text())) == {"2026-09-19", "2026-10-19"}
    clock.now += timedelta(days=1)  # 2026-10-20: 09-19 falls out
    ledger.add(0.3)
    assert set(json.loads((tmp_path / "s.json").read_text())) == {"2026-10-19", "2026-10-20"}


def test_ledger_write_is_atomic_and_leaves_no_temp_file(tmp_path: Path):
    ledger = SpendLedger(tmp_path / "nested" / "s.json")
    ledger.add(0.01)
    assert [p.name for p in (tmp_path / "nested").iterdir()] == ["s.json"]


def test_ledger_rejects_a_negative_or_non_finite_cost(tmp_path: Path):
    ledger = SpendLedger(tmp_path / "s.json")
    for bad in (-0.1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            ledger.add(bad)
    assert not (tmp_path / "s.json").exists()
    assert ledger.add(0.0) == 0.0


def test_ledger_treats_an_unreadable_file_as_empty_and_warns(tmp_path: Path, caplog):
    path = tmp_path / "s.json"
    path.write_text("{not json")
    with caplog.at_level("WARNING", logger="kb_librarian.chat.spend"):
        assert SpendLedger(path).today_total() == 0.0
    assert any("ledger" in r.getMessage() for r in caplog.records)
    clock = Clock(datetime(2026, 9, 18, tzinfo=UTC))
    path.write_text('{"2026-09-18": "abc", "2026-09-17": true, "x": 1}')  # wrong value types are ignored
    assert SpendLedger(path, clock=clock).today_total() == 0.0
    path.write_text("[1, 2]")
    assert SpendLedger(path, clock=clock).today_total() == 0.0


def test_ledger_ignores_non_finite_or_negative_totals_in_the_file(tmp_path: Path, caplog):
    ledger = SpendLedger(tmp_path / "chat-spend.json", clock=Clock(datetime(2026, 9, 18, 12, tzinfo=UTC)))
    ledger.path.write_text('{"2026-09-18": NaN, "2026-09-17": Infinity, "2026-09-16": -3, "2026-09-15": 1.5}')
    with caplog.at_level("WARNING"):
        assert ledger.today_total() == 0.0
    assert ledger.add(0.25) == 0.25
    assert json.loads(ledger.path.read_text()) == {"2026-09-15": 1.5, "2026-09-18": 0.25}
    assert "dropped" in caplog.text.lower() or "ignor" in caplog.text.lower()


def test_ledger_serialises_concurrent_adds(tmp_path: Path):
    ledger = SpendLedger(tmp_path / "s.json")
    threads = [threading.Thread(target=ledger.add, args=(0.01,)) for _ in range(25)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert ledger.today_total() == pytest.approx(0.25)


def test_ledger_for_returns_one_instance_per_root(tmp_path: Path):
    first, second = ledger_for(tmp_path), ledger_for(tmp_path)
    assert first is second and first.path == tmp_path / SPEND_FILE
    assert ledger_for(tmp_path / "other") is not first
