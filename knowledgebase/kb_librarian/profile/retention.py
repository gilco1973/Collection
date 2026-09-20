"""Retention over the reader-record directory: what a purge decides on, and the aggregate statistics.

Both read the files directly (never through ``ProfileStore.load``, which repairs an unreadable record):
a record is decided on only when it parses and carries an aware ``updated_at``; symlinks are never
followed; a dry run touches nothing. A record holding a revocation epoch (``session_epoch > 0``) is
kept while a cookie issued before that bump could still be alive — until ``revoked_until`` — so a
purge can never revive a session that "sign out everywhere" ended.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from kb_librarian.profile.models import Profile


class ProfileStats(BaseModel):
    """What ``kb-librarian profiles stats`` reports: a count and two timestamps, never an identity."""

    count: int = 0
    oldest_updated_at: datetime | None = None
    newest_updated_at: datetime | None = None


@dataclass
class PurgeResult:
    stems: list[str] = field(default_factory=list)  # hashed file stems removed (or, dry-run, to be removed)
    failed: int = 0  # records that could not be removed (counted, never named)


def records(directory: Path) -> list[Path]:
    """Regular ``<hash>.json`` files in the store, sorted; a symlink is skipped, never followed."""
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.json") if not p.is_symlink() and p.is_file())


def record_meta(path: Path) -> tuple[datetime, int] | None:
    """A record's aware ``updated_at`` and its session epoch, or ``None`` when it cannot be decided on."""
    try:
        record = Profile.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    if record.updated_at.tzinfo is None:
        return None
    return record.updated_at, record.session_epoch


def purge_records(
    directory: Path, older_than: datetime, *, dry_run: bool, revoked_until: datetime | None = None
) -> PurgeResult:
    result = PurgeResult()
    for path in records(directory):
        meta = record_meta(path)
        if meta is None or meta[0] >= older_than:
            continue
        if meta[1] and revoked_until is not None and meta[0] >= revoked_until:
            continue  # a revocation epoch that a still-living cookie may need
        if not dry_run:
            try:
                path.unlink()
            except OSError:
                result.failed += 1
                continue
        result.stems.append(path.stem)
    return result


def record_stats(directory: Path) -> ProfileStats:
    stamps = [meta[0] for meta in (record_meta(p) for p in records(directory)) if meta is not None]
    return ProfileStats(
        count=len(stamps),
        oldest_updated_at=min(stamps) if stamps else None,
        newest_updated_at=max(stamps) if stamps else None,
    )
