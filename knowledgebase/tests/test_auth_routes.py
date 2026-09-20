"""/api/auth/*: the sign-in flow end to end against the fake IdP, and the CSRF guard."""

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from kb_librarian.api.app import create_app
from kb_librarian.auth.session import LOGIN_COOKIE, SESSION_COOKIE, sign
from kb_librarian.config import LibrarianSettings
from tests.fake_idp import CLIENT_ID, ISSUER, REDIRECT_URI, FakeIdp, fake_code

SECRET = "session-secret-for-tests-0123456789abcdef"


def _settings(**kw) -> LibrarianSettings:
    base = dict(oidc_issuer=ISSUER, oidc_client_id=CLIENT_ID, oidc_redirect_uri=REDIRECT_URI, session_secret=SECRET)
    return LibrarianSettings(**{**base, **kw})


@pytest.fixture
def idp() -> FakeIdp:
    return FakeIdp()


@pytest.fixture
def client(kb_root: Path, idp: FakeIdp) -> TestClient:
    app = create_app(kb_root, _settings())
    app.state.kb.oidc_transport = idp.transport()
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def _start_login(client: TestClient, next_path: str | None = None) -> dict:
    response = client.get("/api/auth/login", params={"next": next_path} if next_path else None)
    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"] and query["client_id"] == [CLIENT_ID]
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{LOGIN_COOKIE}=") and "HttpOnly" in cookie and "Secure" in cookie
    return {"state": query["state"][0], "nonce": query["nonce"][0], "challenge": query["code_challenge"][0]}


def _finish_login(client: TestClient, tx: dict, **params):
    code = fake_code(tx["nonce"], tx["challenge"])
    return client.get("/api/auth/callback", params={"code": code, "state": tx["state"], **params})


def test_full_sign_in_flow_sets_a_session_and_me_reports_the_user(client: TestClient):
    me = client.get("/api/me").json()
    assert me["user"] is None and me["sso_configured"] is True
    tx = _start_login(client, next_path="/kb/page/onboarding/README.md")
    done = _finish_login(client, tx)
    assert done.status_code == 302 and done.headers["location"] == "/kb/page/onboarding/README.md"
    cookies = done.headers.get_list("set-cookie")
    session = next(c for c in cookies if c.startswith(f"{SESSION_COOKIE}="))
    assert "HttpOnly" in session and "samesite=lax" in session.lower() and "Path=/" in session and "Secure" in session
    assert "Max-Age=43200" in session
    assert any(c.startswith(f"{LOGIN_COOKIE}=") and "Max-Age=0" in c for c in cookies)
    me = client.get("/api/me").json()
    expected = {"sub": "u-123", "name": "Ada Lovelace", "email": "ada@example.com", "operator": False}
    assert me["user"] == expected and me["role"] == "viewer" and me["operator_via"] is None
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/me").json()["user"] is None


def test_cookies_are_not_secure_on_a_localhost_console(kb_root: Path, idp: FakeIdp):
    app = create_app(kb_root, _settings(oidc_redirect_uri="http://localhost:5173/api/auth/callback"))
    app.state.kb.oidc_transport = idp.transport()
    response = TestClient(app, follow_redirects=False).get("/api/auth/login")
    assert response.status_code == 302 and "Secure" not in response.headers["set-cookie"]


def test_callback_rejects_a_foreign_expired_or_garbled_state(client: TestClient):
    tx = _start_login(client)
    assert _finish_login(client, {**tx, "state": "someone-elses"}).status_code == 400
    assert _finish_login(client, {**tx, "state": "é"}).status_code == 400
    assert client.get("/api/auth/callback", params={"code": "x"}).status_code == 400  # no state at all
    client.cookies.clear()
    assert _finish_login(client, tx).status_code == 400  # no login cookie


def test_callback_rejects_declined_bad_or_unverifiable_tokens_with_fixed_messages(client: TestClient, idp: FakeIdp):
    tx = _start_login(client)
    declined = _finish_login(client, tx, error="access_denied<script>", code="")
    assert declined.status_code == 401 and "<script>" not in declined.text
    for change in ({"nonce_override": "replayed"}, {"audience_override": "other"}, {"token_status": 400},
                   {"token_body": "<html>"}, {"expired": True}, {"unsigned": True}, {"unreachable": True},
                   {"sub": "s" * 300}):  # fmt: skip
        idp.__dict__.update(change)
        tx = _start_login(client)
        rejected = _finish_login(client, tx)
        assert (
            rejected.status_code == 401 and rejected.json()["error"]["message"] == "the sign-in could not be verified"
        )
        idp.__dict__.update({k: FakeIdp.__dataclass_fields__[k].default for k in change})
    assert client.get("/api/me").json()["user"] is None


def test_login_reports_an_unavailable_identity_provider_as_502(kb_root: Path, idp: FakeIdp):
    idp.unreachable = True
    app = create_app(kb_root, _settings())
    app.state.kb.oidc_transport = idp.transport()
    response = TestClient(app, base_url="https://testserver", follow_redirects=False).get("/api/auth/login")
    assert response.status_code == 502 and response.json()["error"]["message"] == "the identity provider is unavailable"


def test_a_garbled_session_cookie_is_anonymous_not_an_error(client: TestClient):
    for junk in (b"\xe9\xe9", b"a.b", b"x" * 5000, b"a.\xe9"):  # raw bytes, as a browser might send them
        response = client.get("/api/me", headers={b"Cookie": SESSION_COOKIE.encode() + b"=" + junk})
        assert response.status_code == 200 and response.json()["user"] is None
    client.cookies.set(SESSION_COOKIE, sign({"state": "s"}, SECRET, 600, "login"))  # a login cookie is not a session
    assert client.get("/api/me").json()["user"] is None


def test_logout_and_every_per_user_route_refuse_cross_site_requests(client: TestClient):
    client.cookies.set(SESSION_COOKIE, sign({"sub": "u1", "iss": ISSUER, "name": "Ada"}, SECRET, 3600, "session"))
    cross = {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}
    assert client.post("/api/auth/logout", headers=cross).status_code == 403
    assert client.post("/api/auth/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/auth/logout", headers={"Sec-Fetch-Site": "same-site"}).status_code == 403
    assert client.get("/api/profile", headers=cross).status_code == 403
    assert client.get("/api/me").json()["user"]["sub"] == "u1"  # the cookie itself is still valid
    same = {"Origin": "https://testserver", "Sec-Fetch-Site": "same-origin"}
    assert client.get("/api/profile", headers=same).status_code == 200
    assert client.post("/api/auth/logout", headers=same).status_code == 204


def test_routes_are_absent_without_sso_configuration(kb_root: Path):
    client = TestClient(create_app(kb_root, LibrarianSettings()), follow_redirects=False)
    assert client.get("/api/auth/login").status_code == 404
    assert client.get("/api/auth/callback", params={"code": "x", "state": "y"}).status_code == 404
    me = client.get("/api/me").json()
    assert me["sso_configured"] is False and me["user"] is None
    assert LibrarianSettings(oidc_issuer=ISSUER).sso_configured is False
