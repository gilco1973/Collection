"""Operator role from identity-provider groups: /api/me, audit attribution and the CSRF guard on the cookie path."""

import hashlib
import hmac
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kb_librarian.api import routes_audits
from kb_librarian.api.app import create_app
from kb_librarian.config import LibrarianSettings
from kb_librarian.models import AuditReport
from kb_librarian.reports import ReportStore
from tests.fake_idp import CLIENT_ID, ISSUER, REDIRECT_URI, FakeIdp
from tests.test_auth_routes import SECRET, _finish_login, _start_login

KEY = "operator-secret-key-123"
AUTH = {"Authorization": f"Bearer {KEY}"}
CROSS_SITE = {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}


def _settings(**kw) -> LibrarianSettings:
    base = dict(
        oidc_issuer=ISSUER,
        oidc_client_id=CLIENT_ID,
        oidc_redirect_uri=REDIRECT_URI,
        session_secret=SECRET,
        oidc_operator_groups="kb-operators, kb-admins",
    )
    return LibrarianSettings(**{**base, **kw})


def _client(kb_root: Path, idp: FakeIdp, **kw) -> TestClient:
    app = create_app(kb_root, _settings(**kw))
    app.state.kb.oidc_transport = idp.transport()
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def _sign_in(client: TestClient) -> None:
    assert _finish_login(client, _start_login(client)).status_code == 302


async def _fake_agent(settings, root, **kwargs):
    report = AuditReport(audit_type="agent", dry_run=kwargs["dry_run"], requested_by=kwargs.get("requested_by"))
    kwargs["manager"].register(report.audit_id)
    kwargs["on_registered"](report.audit_id)
    report.finish("completed")
    ReportStore(root / settings.reports_dir).save(report)
    kwargs["manager"].unregister(report.audit_id)
    return report


@pytest.fixture
def idp() -> FakeIdp:
    return FakeIdp()


def test_operator_groups_setting_is_a_trimmed_set_and_empty_by_default():
    assert LibrarianSettings().operator_groups == frozenset() and LibrarianSettings().oidc_groups_claim == "groups"
    assert LibrarianSettings(oidc_operator_groups=" a, b ,,c ").operator_groups == frozenset({"a", "b", "c"})


def test_a_group_member_is_an_operator_via_group_and_audits_record_the_subject(kb_root, idp, monkeypatch):
    monkeypatch.setattr(routes_audits, "run_agent_audit", _fake_agent)
    idp.groups = ["staff", "kb-operators"]
    client = _client(kb_root, idp)
    _sign_in(client)
    me = client.get("/api/me").json()
    assert me["role"] == "operator" and me["operator_via"] == "group" and me["user"]["operator"] is True
    started = client.post("/api/audits", json={"type": "agent"})
    assert started.status_code == 202 and started.json()["dry_run"] is True
    audit_id = started.json()["audit_id"]
    detail = client.get(f"/api/audits/{audit_id}").json()
    expected = "user:" + hmac.new(SECRET.encode(), f"{ISSUER}\0u-123".encode(), hashlib.sha256).hexdigest()[:16]
    assert (
        expected != "user:" + hashlib.sha256(f"{ISSUER}\0u-123".encode()).hexdigest()[:16]
    )  # keyed: no offline guessing
    assert detail["requested_by"] == expected  # the reader-record pseudonym: never the subject, name or e-mail
    exported = client.get(f"/api/audits/{audit_id}/export", params={"format": "md"}).text
    for secret in ("u-123", "Ada Lovelace", "ada@example.com"):
        assert secret not in json.dumps(detail) and secret not in exported
    offline = client.post("/api/audits", json={"type": "offline"})
    assert offline.status_code == 202
    assert client.get(f"/api/audits/{offline.json()['audit_id']}").json()["requested_by"] == expected


def test_without_a_matching_group_the_reader_stays_a_viewer(kb_root, idp):
    idp.groups = ["staff"]
    client = _client(kb_root, idp)
    _sign_in(client)
    me = client.get("/api/me").json()
    assert me["role"] == "viewer" and me["operator_via"] is None and me["user"]["operator"] is False
    refused = client.post("/api/audits", json={"type": "offline"})
    assert refused.status_code == 403 and refused.json()["error"]["message"] == "operator role required"


@pytest.mark.parametrize("groups", ["kb-operators", {"kb-operators": True}, ["kb-operators", 5], 7, True])
def test_a_groups_claim_that_is_not_a_list_of_strings_grants_nothing(kb_root, idp, groups):
    idp.groups = groups
    client = _client(kb_root, idp)
    _sign_in(client)
    me = client.get("/api/me").json()
    assert me["role"] == "viewer" and me["operator_via"] is None and me["user"]["sub"] == "u-123"


def test_no_configured_operator_group_means_identity_never_grants_the_role(kb_root, idp):
    idp.groups = ["kb-operators"]
    client = _client(kb_root, idp, oidc_operator_groups="")
    _sign_in(client)
    assert client.get("/api/me").json()["role"] == "viewer"


def test_the_groups_claim_name_is_configurable(kb_root, idp):
    idp.groups, idp.groups_claim = ["kb-admins"], "roles"
    client = _client(kb_root, idp, oidc_groups_claim="roles")
    _sign_in(client)
    assert client.get("/api/me").json()["operator_via"] == "group"
    other = _client(kb_root, FakeIdp(groups=["kb-admins"], groups_claim="roles"))  # server still reads `groups`
    _sign_in(other)
    assert other.get("/api/me").json()["role"] == "viewer"


def test_the_bearer_key_still_grants_operator_via_key(kb_root, idp, monkeypatch):
    monkeypatch.setattr(routes_audits, "run_agent_audit", _fake_agent)
    client = _client(kb_root, idp, api_key=KEY)
    me = client.get("/api/me", headers=AUTH).json()
    assert me["role"] == "operator" and me["operator_via"] == "key" and me["user"] is None
    assert client.get("/api/me").json() | {"operator_via": None} == client.get("/api/me").json()
    started = client.post("/api/audits", json={"type": "agent"}, headers=AUTH)
    assert client.get(f"/api/audits/{started.json()['audit_id']}").json()["requested_by"] == "key"
    idp.groups = ["kb-operators"]
    _sign_in(client)
    assert client.get("/api/me", headers=AUTH).json()["operator_via"] == "key"  # break-glass path wins
    assert client.get("/api/me").json()["operator_via"] == "group"


def test_a_group_operator_mutation_is_refused_cross_site(kb_root, idp):
    idp.groups = ["kb-operators"]
    client = _client(kb_root, idp)
    _sign_in(client)
    assert client.post("/api/audits/nope/cancel", headers=CROSS_SITE).status_code == 403
    assert client.post("/api/audits", json={"type": "offline"}, headers=CROSS_SITE).status_code == 403
    assert client.post("/api/audits/nope/cancel").status_code == 404  # same-origin: the role check passed
