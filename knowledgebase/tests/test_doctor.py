"""``kb-librarian doctor``: offline checks, exit codes, CLI wiring and the --model probe (fakes only)."""

import io
import re
import shutil
from pathlib import Path

import pytest
from pydantic import SecretStr

from kb_librarian import cli, cli_doctor
from kb_librarian.config import LibrarianSettings
from tests.doctor_helpers import ENV_KEYS, FAKE_CREDENTIAL, WithRetention, run_doctor
from tests.fake_idp import CLIENT_ID, ISSUER, REDIRECT_URI
from tests.fake_query import _result

LINE = re.compile(r"^(OK|WARN|FAIL) [a-z-]+ — .+$")
PROJECT = Path(__file__).resolve().parents[1]
OFFLINE = [
    "python", "kb-config", "catalog", "state-dir", "credentials", "api-key", "sso", "session-secret",
    "live-gate", "atlassian", "atlassian-write-gate", "retention", "embeddings",
]  # fmt: skip


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path: Path):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_CREDENTIAL)
    monkeypatch.setattr(cli_doctor, "CLI_CREDENTIAL_STORE", tmp_path / "no-such-store.json")


def test_doctor_sees_the_bundled_cli_s_own_credential_store(kb_root: Path, monkeypatch, tmp_path: Path):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    code, lines = run_doctor(WithRetention(), kb_root)
    assert code == 1 and any(line.startswith("WARN credentials — ") and "doctor --model" in line for line in lines)
    store = tmp_path / ".claude" / ".credentials.json"
    store.parent.mkdir()
    store.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli_doctor, "CLI_CREDENTIAL_STORE", store)
    code, lines = run_doctor(WithRetention(), kb_root)
    assert code == 0 and any(line.startswith("OK credentials — ") and "bundled CLI" in line for line in lines)
    assert not any(str(store) in line for line in lines)


def test_doctor_is_clean_on_the_project_and_on_the_fixture(kb_root: Path, tmp_path: Path):
    project = tmp_path / "project"  # the real contract and pages, in a copy so the index is built off-tree
    shutil.copytree(PROJECT / "docs", project / "docs")
    shutil.copy(PROJECT / "kb.config.yaml", project / "kb.config.yaml")
    for root in (project, kb_root):
        code, lines = run_doctor(WithRetention(), root)
        assert code == 0, lines
        assert [line.split()[1] for line in lines] == OFFLINE
        assert all(LINE.match(line) and line.startswith("OK ") for line in lines), lines
        assert FAKE_CREDENTIAL not in "\n".join(lines) and "ANTHROPIC_API_KEY set (medium)" in "\n".join(lines)


def test_doctor_warns_without_a_model_credential_or_retention(kb_root: Path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    code, lines = run_doctor(LibrarianSettings(), kb_root)
    assert code == 1
    assert any(line.startswith("WARN credentials — ") for line in lines)
    assert any(line.startswith("WARN retention — ") for line in lines)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t" * 80)
    code, lines = run_doctor(WithRetention(), kb_root)
    assert code == 0 and "OK credentials — CLAUDE_CODE_OAUTH_TOKEN set (long)" in lines


def test_doctor_fails_on_short_secrets_and_never_prints_them(kb_root: Path):
    settings = WithRetention.model_construct(api_key=SecretStr("k3y-abc"), session_secret=SecretStr("s3cr3t-xyz"))
    code, lines = run_doctor(settings, kb_root)
    assert code == 2
    assert any(line.startswith("FAIL api-key — ") and "16" in line for line in lines)
    assert any(line.startswith("FAIL session-secret — ") and "32" in line for line in lines)
    joined = "\n".join(lines)
    assert "k3y-abc" not in joined and "s3cr3t-xyz" not in joined and FAKE_CREDENTIAL not in joined
    sso = dict(oidc_issuer=ISSUER, oidc_client_id=CLIENT_ID, oidc_redirect_uri=REDIRECT_URI)  # secret alone = partial
    strong = WithRetention(api_key="operator-key-0123456789", session_secret="s" * 40, **sso)
    code, lines = run_doctor(strong, kb_root)
    assert code == 0 and "OK api-key — KB_API_KEY set (medium)" in lines and "OK sso — configured" in lines
    assert "OK session-secret — KB_SESSION_SECRET set (medium)" in lines


def test_doctor_flags_partial_sso_partial_atlassian_and_open_gates(kb_root: Path):
    settings = WithRetention(
        oidc_issuer="https://idp.example.test",
        allow_live=True,
        atlassian_allow_write=True,
        atlassian_base_url="https://t.atlassian.net",
    )
    code, lines = run_doctor(settings, kb_root)
    assert code == 2
    text = "\n".join(lines)
    assert "FAIL sso — partially configured: missing KB_OIDC_CLIENT_ID, KB_OIDC_REDIRECT_URI, KB_SESSION_SECRET" in text
    assert "FAIL atlassian — partially configured: missing KB_ATLASSIAN_EMAIL, KB_ATLASSIAN_API_TOKEN" in text
    assert "WARN live-gate — KB_ALLOW_LIVE=true" in text
    assert "WARN atlassian-write-gate — KB_ATLASSIAN_ALLOW_WRITE=true but Atlassian is not configured" in text
    full = WithRetention(
        atlassian_allow_write=True,
        atlassian_base_url="https://t.atlassian.net",
        atlassian_email="svc@example.com",
        atlassian_api_token="tok-secret-value",
    )
    code, lines = run_doctor(full, kb_root)
    assert code == 1 and "OK atlassian — configured" in lines and "tok-secret-value" not in "\n".join(lines)
    assert any(line.startswith("WARN atlassian-write-gate — KB_ATLASSIAN_ALLOW_WRITE=true: ") for line in lines)


def test_doctor_fails_when_the_project_or_state_dir_is_broken(kb_root: Path, monkeypatch):
    (kb_root / "kb.config.yaml").write_text("version: 1\n")
    code, lines = run_doctor(WithRetention(), kb_root, index=False)
    assert code == 2
    assert any(line.startswith("FAIL kb-config — does not load (") for line in lines)
    assert "FAIL catalog — skipped: kb.config.yaml did not load" in lines
    monkeypatch.setattr("kb_librarian.cli_doctor.probe_writable", lambda directory: False)
    code, lines = run_doctor(WithRetention(), kb_root, index=False)
    assert "FAIL state-dir — .librarian/ is not writable" in lines


def test_doctor_reports_the_python_version(kb_root: Path, monkeypatch):
    import sys

    monkeypatch.setattr(sys, "version_info", (3, 12, 1, "final", 0))
    code, lines = run_doctor(WithRetention(), kb_root)
    assert code == 2 and "FAIL python — 3.12.1; 3.11 is required" in lines


def test_doctor_is_wired_into_the_cli(kb_root: Path):
    out = io.StringIO()
    code = cli.main(["--root", str(kb_root), "doctor"], out=out)
    text = out.getvalue()
    assert code == 1 and text.startswith("OK python — 3.11.") and "WARN retention — " in text
    usage = cli.build_parser().format_help()
    assert "doctor" in usage
    assert cli.build_parser().parse_args(["doctor", "--network", "--model"]).model is True


def test_doctor_model_probe_uses_the_injected_query(kb_root: Path):
    class Query:
        def __init__(self, result=None, error: Exception | None = None):
            self.result, self.error, self.options, self.calls = result, error, None, 0

        async def __call__(self, *, prompt, options):
            self.calls += 1
            self.options = options
            if self.error:
                raise self.error
            yield self.result

    good = Query(_result(result="OK", total_cost_usd=0.003))
    code, lines = run_doctor(WithRetention(), kb_root, model=True, query_fn=good)
    assert code == 0 and "OK model — one turn completed with claude-opus-5 (cost $0.0030)" in lines
    options = good.options
    assert options.max_turns == 1 and options.max_budget_usd == 0.05 and options.effort == "low"
    assert options.tools == [] and options.allowed_tools == [] and options.mcp_servers == {}
    assert "Bash" in options.disallowed_tools and options.setting_sources == []
    errored = Query(_result(is_error=True, subtype="error_x"))
    code, lines = run_doctor(WithRetention(), kb_root, model=True, query_fn=errored)
    assert code == 2 and "FAIL model — the turn ended in error (error_x)" in lines
    raising = Query(error=RuntimeError("no cli at /home"))
    code, lines = run_doctor(WithRetention(), kb_root, model=True, query_fn=raising)
    assert code == 2 and "FAIL model — RuntimeError: could not complete a turn" in lines
    assert "/home" not in "\n".join(lines)
    unused = Query(_result())
    code, _ = run_doctor(WithRetention(), kb_root, query_fn=unused)
    assert code == 0 and unused.calls == 0  # without --model nothing leaves the machine
