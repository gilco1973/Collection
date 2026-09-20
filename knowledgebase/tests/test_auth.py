"""kb_librarian/auth: signed cookies, settings validation and the OIDC relying party (no routes)."""

import base64
import hashlib

import pytest

from kb_librarian.auth.oidc import OidcError, OidcProvider, pkce_pair
from kb_librarian.auth.session import safe_return_path, sign, user_from_session, verify
from kb_librarian.config import LibrarianSettings, is_secure_url
from tests.fake_idp import CLIENT_ID, ISSUER, REDIRECT_URI, FakeIdp, fake_code

SECRET = "session-secret-for-tests-0123456789abcdef"


@pytest.fixture
def idp() -> FakeIdp:
    return FakeIdp()


def test_session_cookie_round_trip_and_tamper_rejection():
    token = sign({"sub": "u1", "iss": ISSUER, "name": "Ada"}, SECRET, 60, "session", now=1000)
    payload = verify(token, SECRET, "session", now=1030)
    assert payload["sub"] == "u1" and payload["iat"] == 1000 and payload["exp"] == 1060
    assert verify(token, SECRET, "session", now=1060) is None  # expired
    assert verify(token, SECRET, "login", now=1030) is None  # wrong kind
    assert verify(token, "other-secret", "session", now=1030) is None
    body, _, mac = token.rpartition(".")
    assert verify(f"{body}x.{mac}", SECRET, "session", now=1030) is None
    for junk in ("garbage", "a.b", "éé.éé", f"{body}.é", "..", None, ""):
        assert verify(junk, SECRET, "session") is None  # never raises, whatever the bytes
    assert verify(sign({}, SECRET, 60, "session", now=0), SECRET, "session", now=0) is not None  # now=0 honoured


def test_user_from_session_requires_sub_and_iss_and_bounds_claims():
    assert user_from_session(sign({"name": "no sub", "iss": ISSUER}, SECRET, 60, "session"), SECRET) is None
    assert user_from_session(sign({"sub": "u1"}, SECRET, 60, "session"), SECRET) is None  # no issuer
    assert user_from_session(sign({"sub": "x" * 256, "iss": ISSUER}, SECRET, 60, "session"), SECRET) is None
    assert user_from_session(sign({"sub": "u1", "iss": ISSUER}, SECRET, 60, "login"), SECRET) is None
    user = user_from_session(
        sign({"sub": "u1", "iss": ISSUER, "email": 5, "name": "n" * 500}, SECRET, 60, "session"), SECRET
    )
    assert user.email is None and len(user.name) == 200 and user.storage_key == f"{ISSUER}\0u1"


def test_safe_return_path_blocks_open_redirects_and_oversize():
    assert safe_return_path("/kb/page/x.md?y=1") == "/kb/page/x.md?y=1"
    for bad in (None, "", "https://evil.example", "//evil.example", "/\\evil", "kb", "/\tx", "/" + "a" * 3000):
        assert safe_return_path(bad) == "/"


def test_pkce_pair_is_s256():
    verifier, challenge = pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected and len(verifier) >= 43


def test_settings_reject_weak_secret_and_plaintext_urls():
    with pytest.raises(ValueError, match="at least 32"):
        LibrarianSettings(session_secret="short")
    with pytest.raises(ValueError, match="https"):
        LibrarianSettings(oidc_issuer="http://idp.example.test")
    with pytest.raises(ValueError, match="https"):
        LibrarianSettings(oidc_redirect_uri="http://kb.example.test/api/auth/callback")
    dev = LibrarianSettings(oidc_issuer="http://localhost:8080/realm", oidc_redirect_uri="http://127.0.0.1:5173/cb")
    assert dev.sso_configured is False and dev.cookies_secure is False
    assert LibrarianSettings(oidc_redirect_uri=REDIRECT_URI).cookies_secure is True
    assert is_secure_url("https://a") and is_secure_url("http://localhost") and not is_secure_url("http://a")


def test_provider_verifies_keys_nonce_audience_and_discovery(idp: FakeIdp):
    provider = OidcProvider(ISSUER, CLIENT_ID, REDIRECT_URI, client_secret="s:e/c", transport=idp.transport())
    assert provider.verify_id_token(idp.id_token("n1"), "n1")["sub"] == "u-123"
    with pytest.raises(OidcError, match="unknown key"):
        provider.verify_id_token(idp.id_token("n1", kid="rotated"), "n1")
    assert sum(1 for r in idp.requests if r.url.path == "/jwks") == 1  # the refetch is rate-limited
    with pytest.raises(OidcError, match="nonce"):
        provider.verify_id_token(idp.id_token("n1"), "n2")
    idp.audience_override = [CLIENT_ID, "other-client"]
    with pytest.raises(OidcError, match="azp"):
        provider.verify_id_token(idp.id_token("n1"), "n1")
    idp.extra_claims["azp"] = CLIENT_ID
    assert provider.verify_id_token(idp.id_token("n1"), "n1")["azp"] == CLIENT_ID
    idp.audience_override, idp.extra_claims = None, {}
    idp.unsigned = True
    with pytest.raises(OidcError, match="rejected"):
        provider.verify_id_token(idp.id_token("n1"), "n1")
    idp.unsigned, idp.expired = False, True
    with pytest.raises(OidcError, match="rejected"):
        provider.verify_id_token(idp.id_token("n1"), "n1")
    idp.expired = False
    verifier, challenge = pkce_pair()
    tokens = provider.exchange_code(fake_code("n1", challenge), verifier)
    assert "id_token" in tokens
    token_request = idp.requests[-1]
    assert token_request.headers["authorization"].startswith("Basic ")  # urlencoded before base64
    assert base64.b64decode(token_request.headers["authorization"][6:]) == b"kb-console:s%3Ae%2Fc"
    assert b"client_id=" not in token_request.content  # one client-auth method, not two
    with pytest.raises(OidcError, match="returned 400"):
        provider.exchange_code(fake_code("n1", challenge), "wrong-verifier")
    provider.close()


def test_provider_turns_every_transport_and_shape_failure_into_oidc_error(idp: FakeIdp):
    wrong = OidcProvider("https://other.example", CLIENT_ID, REDIRECT_URI, transport=idp.transport())
    with pytest.raises(OidcError, match="issuer"):
        wrong.configuration()
    provider = OidcProvider(ISSUER, CLIENT_ID, REDIRECT_URI, transport=idp.transport())
    idp.token_body = "<html>maintenance</html>"
    with pytest.raises(OidcError, match="non-JSON"):
        provider.exchange_code(fake_code("n", "c"), "v")
    idp.token_body, idp.unreachable = None, True
    with pytest.raises(OidcError, match="unreachable"):
        provider.exchange_code(fake_code("n", "c"), "v")
    idp.unreachable = False
    plain = OidcProvider(ISSUER, CLIENT_ID, REDIRECT_URI, transport=idp.transport())
    verifier, challenge = pkce_pair()
    plain.exchange_code(fake_code("n", challenge), verifier)
    assert b"client_id=kb-console" in idp.requests[-1].content  # a public client names itself in the body
