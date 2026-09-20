"""Revocation must fail closed: an unreadable record and a retention purge can never bring a revoked
cookie back to life."""

import json
from datetime import UTC, datetime, timedelta

from kb_librarian.profile.store import ProfileStore
from tests.fake_idp import ISSUER
from tests.test_session_epoch import _client, _sign_in, _with, idp  # noqa: F401 (the fixture)

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


def _backdate(store: ProfileStore, key: str, updated_at: datetime) -> None:
    path = store._path(key)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["updated_at"] = updated_at.isoformat()
    path.write_text(json.dumps(record), encoding="utf-8")


def test_an_unreadable_record_is_repaired_as_a_tombstone_with_a_fresh_epoch(kb_root):
    store = ProfileStore(kb_root)
    store.record_view("u-1", "onboarding/README.md")
    bumped = store.bump_session_epoch("u-1")
    store._path("u-1").write_text("", encoding="utf-8")  # a zero-length record after a crash
    repaired = store.session_epoch("u-1")
    assert repaired not in (0, bumped) and store.session_epoch("u-1") == repaired  # stable once repaired
    record = store.load("u-1")
    assert record.session_epoch == repaired and record.viewed == {}
    assert json.loads(store._path("u-1").read_text(encoding="utf-8"))["session_epoch"] == repaired


def test_a_corrupt_record_refuses_every_earlier_cookie_and_a_fresh_sign_in_works(kb_root, idp):  # noqa: F811
    client = _client(kb_root, idp)
    original = _sign_in(client)  # epoch 0
    assert client.post("/api/auth/logout-everywhere").status_code == 204
    current = _sign_in(client)  # carries the bumped epoch
    assert client.get("/api/profile").status_code == 200
    store = ProfileStore(kb_root)
    store._path(_key()).write_text("{not json", encoding="utf-8")
    assert _with(client, original).get("/api/profile").status_code == 401  # the pre-bump cookie stays dead…
    assert _with(client, current).get("/api/profile").status_code == 401  # …and so is the one that predates the damage
    fresh = _sign_in(client)
    assert fresh not in (original, current)
    assert client.get("/api/profile").status_code == 200 and client.get("/api/profile").status_code == 200


def _key() -> str:
    return f"{ISSUER}\0u-123"


def test_purge_keeps_a_revocation_epoch_until_the_session_ttl_has_passed(kb_root):
    store = ProfileStore(kb_root)
    epoch = store.bump_session_epoch("u-1")
    _backdate(store, "u-1", NOW - timedelta(days=10))
    store.record_view("u-2", "onboarding/README.md")  # never revoked
    _backdate(store, "u-2", NOW - timedelta(days=10))
    result = store.purge(NOW - timedelta(days=7), dry_run=False, revoked_until=NOW - timedelta(days=30))
    assert result.stems == [store._path("u-2").stem] and result.failed == 0
    assert store.session_epoch("u-1") == epoch  # a cookie issued before the bump could still be inside its TTL
    result = store.purge(NOW - timedelta(days=7), dry_run=False, revoked_until=NOW - timedelta(days=5))
    assert result.stems == [store._path("u-1").stem] and store.session_epoch("u-1") == 0
