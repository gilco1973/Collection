"""``kb-librarian profiles ...``: retention purge and aggregate statistics for reader records.

``purge`` is dry-run by default and removes nothing without an explicit ``--live``. That flag is
deliberately *not* behind ``KB_ALLOW_LIVE``: that gate protects knowledge-base pages from a leaked
key or a stray flag reaching the model's write tools, whereas a purge never touches a page — it is
the operator's scheduled data-minimisation duty on the state volume (see the deployment's cron
job). Output is counts only: never a subject, a name, an e-mail, a hashed file stem or a path.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from kb_librarian.cli_commands import EXIT_FAILED, EXIT_OK
from kb_librarian.config import LibrarianSettings
from kb_librarian.profile.store import ProfileStore


def add_profiles_parser(sub) -> None:
    profiles = sub.add_parser("profiles", help="reader records: retention purge and statistics")
    prof = profiles.add_subparsers(dest="profiles_command", required=True)
    purge = prof.add_parser("purge", help="remove records inactive for N days (dry run unless --live)")
    purge.add_argument(
        "--older-than-days", type=int, default=None, help="inactivity threshold (default: KB_PROFILE_RETENTION_DAYS)"
    )
    purge.add_argument("--live", action="store_true", help="really remove the records; the default only counts")
    prof.add_parser("stats", help="record count and the oldest/newest activity, no identities")


def cmd_profiles(settings: LibrarianSettings, root: Path, args, out) -> int:
    store = ProfileStore(root)
    if args.profiles_command == "stats":
        return _stats(store, out)
    return _purge(settings, store, args.older_than_days, args.live, out)


def _purge(settings: LibrarianSettings, store: ProfileStore, older_than_days: int | None, live: bool, out) -> int:
    days = older_than_days if older_than_days is not None else settings.profile_retention_days
    if days is None:
        print("no retention period: pass --older-than-days N or set KB_PROFILE_RETENTION_DAYS", file=out)
        return EXIT_FAILED
    if days <= 0:
        print("--older-than-days must be a positive number of days", file=out)
        return EXIT_FAILED
    dry_run = not live
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}", file=out)
    print(f"older_than_days={days}", file=out)
    now = datetime.now(UTC)
    # A record holding a revocation epoch is kept until every cookie from before that bump has expired.
    revoked_until = now - timedelta(hours=settings.session_ttl_hours)
    try:
        result = store.purge(now - timedelta(days=days), dry_run=dry_run, revoked_until=revoked_until)
    except OSError as exc:  # the type only: an OSError message carries the record's path
        print(f"purge failed: {type(exc).__name__}", file=out)
        return EXIT_FAILED
    if dry_run:
        print(f"candidates={len(result.stems)}", file=out)
    else:
        print(f"removed={len(result.stems)} failed={result.failed}", file=out)
    return EXIT_OK


def _stats(store: ProfileStore, out) -> int:
    stats = store.stats()
    print(f"count={stats.count}", file=out)
    for name in ("oldest_updated_at", "newest_updated_at"):
        value = getattr(stats, name)
        print(f"{name}={value.isoformat() if value else '-'}", file=out)
    return EXIT_OK
