"""Session revocation: the per-reader epoch, "sign out everywhere", and what a stale cookie can still do."""

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kb_librarian.api.app import create_app
from kb_librarian.auth.session import SESSION_COOKIE, User, sign, user_from_session, verify
from kb_librarian.profile.store import ProfileStore
from tests.fake_idp import ISSUER, FakeIdp
from tests.test_auth_routes import SECRET, _finish_login, _settings, _start_login

CROSS_SITE = {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}
SAME_ORIGIN = {"Origin": "https://testserver", "Sec-Fetch-Site": "same-origin"}


@pytest.fixture
def idp() -> FakeIdp:
    return FakeIdp()


def _client(kb_root: Path, idp: FakeIdp) -> TestClient:
    app = create_app(kb_root, _settings())
    app.state.kb.oidc_transport = idp.transport()
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def _sign_in(client: TestClient) -> str:
    """A fresh sign-in from an empty cookie jar; returns the session cookie it produced."""
    client.cookies.clear()
    assert _finish_login(client, _start_login(client)).status_code == 302
    return client.cookies.get(SESSION_COOKIE)


def _with(client: TestClient, cookie: str) -> TestClient:
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, cookie)
    return client


def test_store_epoch_is_zero_until_bumped_and_a_bump_is_time_derived_and_strictly_increasing(kb_root):
    store = ProfileStore(kb_root)
    assert store.session_epoch("u-1") == 0
    before = int(time.time())
    first = store.bump_session_epoch("u-1")
    assert first >= before and store.session_epoch("u-1") == first
    second = store.bump_session_epoch("u-1")
    assert second > first  # even twice within the same second
    record = store.load("u-1")
    assert record.session_epoch == second and record.viewed == {} and record.updated_at.timestamp() >= before
    raw = json.loads(next((kb_root / ".librarian" / "users").glob("*.json")).read_text())
    assert raw["session_epoch"] == second
    assert store.delete("u-1") is True and store.session_epoch("u-1") == second  # a tombstone keeps the epoch
    assert store.load("u-1").viewed == {} and store.load("u-1").quizzes == [] and store.load("u-1").persona is None
    assert store.delete("u-1") is True  # the tombstone counts as a record to forget…
    assert store.session_epoch("u-1") == second  # …but the epoch is never forgotten


def test_a_never_bumped_reader_leaves_no_tombstone(kb_root):
    store = ProfileStore(kb_root)
    store.record_view("u-2", "onboarding/README.md")
    assert store.delete("u-2") is True
    assert not list((kb_root / ".librarian" / "users").glob("*.json"))


def test_user_from_session_parses_operator_and_epoch_strictly():
    def user(**extra) -> User:
        return user_from_session(
            sign({"sub": "u1", "iss": ISSUER, "name": "Ada", **extra}, SECRET, 60, "session"), SECRET
        )

    assert user().operator is False and user().epoch == 0
    assert user(operator=True, epoch=7).operator is True and user(operator=True, epoch=7).epoch == 7
    assert user(operator="yes").operator is False and user(operator=1).operator is False
    assert user(epoch="7").epoch == 0 and user(epoch=True).epoch == 0 and user(epoch=7.0).epoch == 0
    assert User(sub="u1", iss=ISSUER, name="Ada", operator=True).as_dict() == {
        "sub": "u1",
        "name": "Ada",
        "email": None,
        "operator": True,
    }


def test_a_cookie_from_before_the_bump_is_refused_while_a_fresh_sign_in_works(kb_root, idp):
    client = _client(kb_root, idp)
    first = _sign_in(client)
    assert client.get("/api/profile").status_code == 200
    out = client.post("/api/auth/logout-everywhere")
    assert out.status_code == 204
    assert out.headers["set-cookie"].startswith(f"{SESSION_COOKIE}=") and "Max-Age=0" in out.headers["set-cookie"]
    assert client.get("/api/profile").status_code == 401  # the browser dropped the cookie
    assert _with(client, first).get("/api/profile").status_code == 401  # and a kept copy is dead too
    assert client.get("/api/me").json()["user"] is None
    second = _sign_in(client)
    assert second != first and client.get("/api/profile").status_code == 200


def test_forget_me_keeps_a_revoked_cookie_refused(kb_root, idp):
    client = _client(kb_root, idp)
    _sign_in(client)
    assert client.post("/api/auth/logout-everywhere").status_code == 204
    revoked = _sign_in(client)
    assert client.post("/api/auth/logout-everywhere").status_code == 204
    assert _with(client, revoked).get("/api/profile").status_code == 401
    _sign_in(client)
    assert client.delete("/api/profile").status_code == 204  # forget me, from the live session
    assert _with(client, revoked).get("/api/profile").status_code == 401


def test_forget_me_does_not_revive_a_cookie_from_before_the_first_bump(kb_root, idp):
    client = _client(kb_root, idp)
    original = _sign_in(client)  # epoch 0: issued before any "sign out everywhere"
    assert client.post("/api/auth/logout-everywhere").status_code == 204
    assert _with(client, original).get("/api/profile").status_code == 401
    _sign_in(client)
    assert client.delete("/api/profile").status_code == 204  # the record (and its epoch) would be gone…
    assert _with(client, original).get("/api/profile").status_code == 401  # …but the revocation must hold


def test_logout_everywhere_needs_a_session_and_is_same_origin_only(kb_root, idp):
    client = _client(kb_root, idp)
    assert client.post("/api/auth/logout-everywhere").status_code == 401
    _sign_in(client)
    assert client.post("/api/auth/logout-everywhere", headers=CROSS_SITE).status_code == 403
    assert client.post("/api/auth/logout-everywhere", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/profile").status_code == 200  # nothing was revoked
    assert client.post("/api/auth/logout-everywhere", headers=SAME_ORIGIN).status_code == 204


def test_the_callback_writes_the_reader_s_current_epoch_into_the_new_session(kb_root, idp):
    epoch = ProfileStore(kb_root).bump_session_epoch(User(sub="u-123", iss=ISSUER, name="Ada").storage_key)
    client = _client(kb_root, idp)
    payload = verify(_sign_in(client), SECRET, "session")
    assert payload["epoch"] == epoch and payload["operator"] is False
    assert client.get("/api/profile").status_code == 200
