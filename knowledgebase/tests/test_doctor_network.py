"""``kb-librarian doctor --network``: IdP discovery and Atlassian reachability against fakes (no socket)."""

from pathlib import Path

import httpx
import pytest

from tests.doctor_helpers import ENV_KEYS, FAKE_CREDENTIAL, WithRetention, run_doctor
from tests.fake_idp import CLIENT_ID, ISSUER, REDIRECT_URI, FakeIdp

SECRET = "session-secret-for-tests-0123456789abcdef"
ATLASSIAN = dict(atlassian_base_url="https://t.atlassian.net", atlassian_email="svc@example.com")
TOKEN = "tok-secret-value-123"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_CREDENTIAL)


def _sso(**kw) -> WithRetention:
    base = dict(oidc_issuer=ISSUER, oidc_client_id=CLIENT_ID, oidc_redirect_uri=REDIRECT_URI, session_secret=SECRET)
    return WithRetention(**{**base, **kw})


def test_network_checks_are_reported_as_skipped_when_nothing_is_configured(kb_root: Path):
    code, lines = run_doctor(WithRetention(), kb_root, network=True)
    assert code == 0
    assert "OK idp — skipped: SSO not configured" in lines
    assert "OK atlassian-api — skipped: Atlassian not configured" in lines
    code, lines = run_doctor(WithRetention(), kb_root)
    assert code == 0 and not any(" idp " in line or " atlassian-api " in line for line in lines)


def test_idp_discovery_is_checked_through_the_provider(kb_root: Path):
    idp = FakeIdp()
    code, lines = run_doctor(_sso(), kb_root, network=True, oidc_transport=idp.transport())
    assert code == 0 and "OK idp — discovery document fetched and consistent" in lines
    assert [r.url.path for r in idp.requests] == ["/.well-known/openid-configuration"]
    idp.unreachable = True
    code, lines = run_doctor(_sso(), kb_root, network=True, oidc_transport=idp.transport())
    assert code == 2 and "FAIL idp — identity provider unreachable (ConnectError)" in lines
    wrong_issuer = _sso(oidc_issuer="https://other.example.test")
    code, lines = run_doctor(wrong_issuer, kb_root, network=True, oidc_transport=FakeIdp().transport())
    assert code == 2 and any(line.startswith("FAIL idp — ") for line in lines)


def test_atlassian_myself_is_checked_through_the_client(kb_root: Path):
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"accountId": "a1", "emailAddress": "svc@example.com"})

    settings = WithRetention(atlassian_api_token=TOKEN, **ATLASSIAN)
    code, lines = run_doctor(settings, kb_root, network=True, atlassian_transport=httpx.MockTransport(handle))
    assert code == 0 and "OK atlassian-api — reachable: /rest/api/3/myself answered" in lines
    assert seen[0].url.path == "/rest/api/3/myself" and seen[0].headers["authorization"].startswith("Basic ")
    joined = "\n".join(lines)
    assert TOKEN not in joined and "svc@example.com" not in joined and "a1" not in joined


def test_atlassian_denied_unreachable_and_non_json_are_failures(kb_root: Path):
    settings = WithRetention(atlassian_api_token=TOKEN, **ATLASSIAN)
    denied = httpx.MockTransport(lambda request: httpx.Response(401, json={"message": "nope"}))
    code, lines = run_doctor(settings, kb_root, network=True, atlassian_transport=denied)
    assert code == 2 and "FAIL atlassian-api — returned 401 for /rest/api/3/myself" in lines

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    code, lines = run_doctor(settings, kb_root, network=True, atlassian_transport=httpx.MockTransport(refuse))
    assert code == 2 and "FAIL atlassian-api — unreachable (ConnectError)" in lines
    html = httpx.MockTransport(lambda request: httpx.Response(200, text="<html>login</html>"))
    code, lines = run_doctor(settings, kb_root, network=True, atlassian_transport=html)
    assert code == 2 and "FAIL atlassian-api — returned a non-JSON body" in lines
