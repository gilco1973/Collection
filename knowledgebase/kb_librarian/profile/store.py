"""One JSON file per reader under ``.librarian/users/<sha256(sub)>.json``.

The file name is a hash of the IdP subject, so a directory listing reveals no identity; the
record (``profile/models.py``) holds only page *paths*, timestamps and counts plus the chosen
persona and the session epoch. Writes are atomic (temp file, fsync, rename) and serialised per
process. Revocation fails closed: an unreadable record is replaced by a tombstone with a fresh
clock epoch, so no cookie issued earlier can match it.
"""

import hashlib
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from kb_librarian.profile.models import MAX_QUIZZES, MAX_VIEWED, PageVisit, Profile, QuizResult, now
from kb_librarian.profile.retention import ProfileStats, PurgeResult, purge_records, record_stats

__all__ = [
    "MAX_QUIZZES",
    "MAX_VIEWED",
    "PageVisit",
    "Profile",
    "ProfileStats",
    "ProfileStore",
    "PurgeResult",
    "QuizResult",
]
USERS_DIR = ".librarian/users"
log = logging.getLogger(__name__)


def _epoch_now() -> int:
    return int(time.time())


def _recovery_epoch() -> int:
    """The epoch a repaired record gets: nanoseconds, so it can never equal a second-based bump epoch
    (a bump and a repair in the same second must not agree) nor any earlier recovery."""
    return time.time_ns()


class ProfileStore:
    def __init__(self, root: Path) -> None:
        self.dir = root / USERS_DIR
        self._lock = threading.Lock()

    def _path(self, sub: str) -> Path:
        return self.dir / f"{hashlib.sha256(sub.encode('utf-8')).hexdigest()}.json"

    def load(self, sub: str) -> Profile:
        """The reader's record, empty when there is none. An unreadable record is not "empty": it is
        replaced on the spot by a tombstone carrying a fresh epoch (every earlier cookie is refused,
        the reader signs in again) — the reading data in it was lost anyway."""
        path = self._path(sub)
        if not path.is_file():
            return Profile(sub=sub)
        try:
            return Profile.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            log.warning("reader record %s is unreadable; replaced by a tombstone (sessions revoked)", path.stem[:12])
            profile = Profile(sub=sub, session_epoch=_recovery_epoch())
            self.save(profile)
            return profile

    def save(self, profile: Profile) -> None:
        profile.updated_at = now()
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self._path(profile.sub)
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write(profile.model_dump_json(indent=1))
            handle.flush()
            os.fsync(handle.fileno())  # a crash after the rename must not leave a zero-length record
        os.replace(tmp, path)

    def record_view(self, sub: str, page_path: str) -> Profile:
        with self._lock:
            profile = self.load(sub)
            visit = profile.viewed.get(page_path)
            if visit is None:
                profile.viewed[page_path] = PageVisit()
            else:
                visit.last_at, visit.count = now(), visit.count + 1
            if len(profile.viewed) > MAX_VIEWED:
                oldest = sorted(profile.viewed, key=lambda p: profile.viewed[p].last_at)[
                    : len(profile.viewed) - MAX_VIEWED
                ]
                for stale in oldest:
                    del profile.viewed[stale]
            self.save(profile)
            return profile

    def set_persona(self, sub: str, persona: str | None) -> Profile:
        with self._lock:
            profile = self.load(sub)
            profile.persona = persona
            self.save(profile)
            return profile

    def record_quiz(self, sub: str, result: QuizResult) -> Profile:
        with self._lock:
            profile = self.load(sub)
            profile.quizzes = [*profile.quizzes, result][-MAX_QUIZZES:]
            self.save(profile)
            return profile

    def session_epoch(self, sub: str) -> int:
        """The epoch a session cookie must carry to be accepted for this reader (0 until the first bump)."""
        with self._lock:
            return self.load(sub).session_epoch

    def bump_session_epoch(self, sub: str) -> int:
        """Revoke every session issued so far. The new epoch is derived from the clock (never a bare +1),
        so a value can never repeat across records or restarts; ``delete`` keeps it in a tombstone."""
        with self._lock:
            profile = self.load(sub)
            profile.session_epoch = max(profile.session_epoch + 1, _epoch_now())
            self.save(profile)
            return profile.session_epoch

    def delete(self, sub: str) -> bool:
        """Forget everything about a reader. Returns whether there was anything to forget.

        One thing is deliberately kept: a reader who ever used "sign out everywhere" leaves a tombstone
        holding only their session epoch, so the cookies that bump revoked can never come back to life
        (a cookie issued before the first bump carries epoch 0, which an empty record would accept again).
        The tombstone holds no reading data; retention purges it once every such cookie has expired."""
        with self._lock:
            path = self._path(sub)
            existed = path.is_file()
            epoch = self.load(sub).session_epoch if existed else 0
            path.unlink(missing_ok=True)
            if epoch:
                self.save(Profile(sub=sub, session_epoch=epoch))
            return existed

    def purge(self, older_than: datetime, *, dry_run: bool, revoked_until: datetime | None = None) -> PurgeResult:
        """Remove — or, in dry-run, only list — every record whose ``updated_at`` is before ``older_than``
        (inactivity-based: ``updated_at`` moves on every reader activity), except a record holding a
        revocation epoch that is not yet older than ``revoked_until`` (the session TTL ago), because a
        cookie from before that bump could still be alive. Stems only, never a subject; a record that
        cannot be removed is counted, not named."""
        with self._lock:
            return purge_records(self.dir, older_than, dry_run=dry_run, revoked_until=revoked_until)

    def stats(self) -> ProfileStats:
        """Count and activity bounds over every readable record; no identities."""
        with self._lock:
            return record_stats(self.dir)
