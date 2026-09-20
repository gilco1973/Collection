"""Reader-record retention: ``ProfileStore.purge``/``stats`` and ``kb-librarian profiles purge|stats``.

Fakes only: records are JSON files written straight into ``.librarian/users/`` with chosen timestamps
(``save`` would stamp the current time). Every assertion about output checks that no subject or
hashed stem leaks: the CLI prints counts, never identities.
"""

import hashlib
import io
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kb_librarian import cli
from kb_librarian.config import LibrarianSettings
from kb_librarian.profile.store import Profile, ProfileStore

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
STALE_AT = NOW - timedelta(days=40)
CUTOFF = NOW - timedelta(days=30)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("KB_PROFILE_RETENTION_DAYS", "KB_ALLOW_LIVE"):
        monkeypatch.delenv(key, raising=False)


def _write(store: ProfileStore, sub: str, updated_at: datetime) -> Path:
    store.dir.mkdir(parents=True, exist_ok=True)
    path = store._path(sub)
    path.write_text(Profile(sub=sub, updated_at=updated_at).model_dump_json(indent=1), encoding="utf-8")
    return path


def _snapshot(directory: Path) -> dict[str, str]:
    """Name -> content hash (a symlink hashes its target path), so 'byte-identical' is checkable."""
    return {
        p.name: hashlib.sha256(os.readlink(p).encode() if p.is_symlink() else p.read_bytes()).hexdigest()
        for p in sorted(directory.iterdir())
    }


def _run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    return cli.main(list(argv), out=out), out.getvalue()


@pytest.fixture
def records(kb_root: Path) -> tuple[ProfileStore, Path, Path]:
    store = ProfileStore(kb_root)
    return store, _write(store, "u-old", STALE_AT), _write(store, "u-new", NOW)


def test_retention_setting_is_optional_and_positive(monkeypatch):
    assert LibrarianSettings().profile_retention_days is None
    monkeypatch.setenv("KB_PROFILE_RETENTION_DAYS", "30")
    assert LibrarianSettings().profile_retention_days == 30
    with pytest.raises(ValueError):
        LibrarianSettings(profile_retention_days=0)


def test_dry_run_reports_the_stale_stem_and_leaves_the_directory_byte_identical(records):
    store, stale, fresh = records
    before = _snapshot(store.dir)
    stems = store.purge(CUTOFF, dry_run=True).stems
    assert stems == [stale.stem] and "u-old" not in stems[0]
    assert _snapshot(store.dir) == before and stale.is_file() and fresh.is_file()


def test_live_purge_removes_exactly_the_stale_record(records):
    store, stale, fresh = records
    fresh_bytes = fresh.read_bytes()
    assert store.purge(CUTOFF, dry_run=False).stems == [stale.stem]
    assert not stale.exists() and fresh.read_bytes() == fresh_bytes
    assert store.purge(CUTOFF, dry_run=False).stems == []
    assert store.load("u-new").updated_at == NOW


def test_unparsable_files_symlinks_and_leftovers_are_skipped(records, tmp_path: Path):
    store, stale, _ = records
    broken = store.dir / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    naive = store.dir / "naive.json"  # a timestamp without a timezone is never decided on
    naive.write_text(Profile(sub="u-naive", updated_at=datetime(2020, 1, 1)).model_dump_json(), encoding="utf-8")
    outside = tmp_path / "elsewhere.json"
    outside.write_text(Profile(sub="u-link", updated_at=STALE_AT).model_dump_json(), encoding="utf-8")
    link = store.dir / "link.json"
    link.symlink_to(outside)
    leftover = store.dir / f"{stale.stem}.json.tmp"
    leftover.write_text("partial", encoding="utf-8")
    assert store.purge(CUTOFF, dry_run=True).stems == [stale.stem]
    assert store.purge(CUTOFF, dry_run=False).stems == [stale.stem]
    assert broken.is_file() and naive.is_file() and link.is_symlink() and outside.is_file() and leftover.is_file()


def test_stats_reports_counts_and_timestamps_but_no_identity(records, tmp_path: Path):
    from kb_librarian.profile.store import ProfileStats

    store, _, _ = records
    stats = store.stats()
    assert (stats.count, stats.oldest_updated_at, stats.newest_updated_at) == (2, STALE_AT, NOW)
    assert "sub" not in stats.model_dump() and "u-old" not in stats.model_dump_json()
    (store.dir / "broken.json").write_text("{not json", encoding="utf-8")
    assert store.stats().count == 2  # an unreadable file is not a record
    assert ProfileStore(tmp_path / "other").stats() == ProfileStats(count=0)  # no users directory at all


def test_cli_purge_is_a_dry_run_by_default(records, kb_root: Path):
    store, stale, _ = records
    before = _snapshot(store.dir)
    code, out = _run("--root", str(kb_root), "profiles", "purge", "--older-than-days", "30")
    assert code == 0 and "Mode: DRY RUN" in out and "candidates=1" in out
    assert "removed=" not in out and stale.stem not in out and "u-old" not in out  # counts only
    assert _snapshot(store.dir) == before


def test_cli_purge_exits_two_without_a_retention_period(records, kb_root: Path):
    code, out = _run("--root", str(kb_root), "profiles", "purge")
    assert code == 2 and "KB_PROFILE_RETENTION_DAYS" in out and "--older-than-days" in out
    code, out = _run("--root", str(kb_root), "profiles", "purge", "--older-than-days", "0", "--live")
    assert code == 2 and "removed=" not in out
    assert records[1].is_file()  # nothing was touched


def test_cli_purge_live_uses_the_configured_retention_without_kb_allow_live(records, kb_root: Path, monkeypatch):
    _, stale, fresh = records
    monkeypatch.setenv("KB_PROFILE_RETENTION_DAYS", "30")
    code, out = _run("--root", str(kb_root), "profiles", "purge", "--live")
    assert code == 0 and "Mode: LIVE" in out and "removed=1" in out and "forced" not in out
    assert not stale.exists() and fresh.is_file() and stale.stem not in out and "u-old" not in out


def test_cli_purge_reports_a_filesystem_error_by_type_only(records, kb_root: Path, monkeypatch):
    def failing(self, older_than, *, dry_run, revoked_until=None):
        raise PermissionError(13, "denied", str(kb_root / ".librarian" / "users" / "deadbeef.json"))

    monkeypatch.setattr(ProfileStore, "purge", failing)
    code, out = _run("--root", str(kb_root), "profiles", "purge", "--older-than-days", "30", "--live")
    assert code == 2 and "purge failed: PermissionError" in out and "removed=" not in out
    assert "deadbeef" not in out and ".librarian" not in out


def test_a_record_that_cannot_be_removed_is_counted_not_named(records, kb_root: Path, monkeypatch):
    store, stale, fresh = records
    real_unlink = Path.unlink

    def unlink(self, missing_ok=False):
        if self == stale:
            raise PermissionError(13, "denied", str(self))
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink)
    result = store.purge(CUTOFF, dry_run=False)
    assert result.stems == [] and result.failed == 1 and stale.is_file()
    code, out = _run("--root", str(kb_root), "profiles", "purge", "--older-than-days", "30", "--live")
    assert code == 0 and "removed=0 failed=1" in out and stale.stem not in out and str(stale) not in out


def test_cli_live_purge_keeps_revocation_epochs_younger_than_the_session_ttl(records, kb_root: Path, monkeypatch):
    store, stale, _ = records
    revoked = _write(store, "u-revoked", STALE_AT)
    record = Profile.model_validate_json(revoked.read_text(encoding="utf-8"))
    record.session_epoch = 1_700_000_000
    revoked.write_text(record.model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("KB_SESSION_TTL_HOURS", "720")  # 30 days: a 40-day-old epoch is past every cookie's life
    code, out = _run("--root", str(kb_root), "profiles", "purge", "--older-than-days", "30", "--live")
    assert code == 0 and "removed=2 failed=0" in out and not stale.exists() and not revoked.exists()
    ten_days = datetime.now(UTC) - timedelta(days=10)  # older than a 7-day retention, younger than the 30-day TTL
    kept = _write(store, "u-revoked-2", ten_days)
    record = Profile.model_validate_json(kept.read_text(encoding="utf-8"))
    record.session_epoch = 1_700_000_000
    kept.write_text(record.model_dump_json(), encoding="utf-8")
    plain = _write(store, "u-plain", ten_days)
    code, out = _run("--root", str(kb_root), "profiles", "purge", "--older-than-days", "7", "--live")
    assert code == 0 and "removed=1 failed=0" in out and kept.is_file() and not plain.exists()


def test_cli_stats_prints_counts_only(kb_root: Path):
    code, out = _run("--root", str(kb_root), "profiles", "stats")
    assert code == 0 and "count=0" in out and "oldest_updated_at=-" in out and "newest_updated_at=-" in out
    store = ProfileStore(kb_root)
    stale, fresh = _write(store, "u-old", STALE_AT), _write(store, "u-new", NOW)
    code, out = _run("--root", str(kb_root), "profiles", "stats")
    assert code == 0 and "count=2" in out
    assert f"oldest_updated_at={STALE_AT.isoformat()}" in out and f"newest_updated_at={NOW.isoformat()}" in out
    assert "u-old" not in out and "u-new" not in out and stale.stem not in out and fresh.stem not in out
