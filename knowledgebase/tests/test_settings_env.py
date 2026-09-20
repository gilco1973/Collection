"""Environment handling of ``LibrarianSettings``: empty values read as unset (the shipped ConfigMap,
Secret template and ``.env.example`` all carry them), and a rejected value is reported by variable
name only — never by its value."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from kb_librarian.config import LibrarianSettings, settings_errors

PROJECT = Path(__file__).resolve().parents[1]
EMPTIED = (
    "KB_PROFILE_RETENTION_DAYS", "KB_SESSION_SECRET", "KB_OIDC_ISSUER", "KB_OIDC_CLIENT_SECRET",
    "KB_LOG_LEVEL", "KB_CHAT_DAILY_BUDGET_USD", "KB_API_KEY", "KB_SESSION_TTL_HOURS",
)  # fmt: skip


def _env_example() -> dict[str, str]:
    pairs = {}
    for line in (PROJECT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            pairs[key.strip()] = value.strip()
    return pairs


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in _env_example():
        monkeypatch.delenv(key, raising=False)


def test_empty_environment_values_read_as_unset(monkeypatch):
    for key in EMPTIED:
        monkeypatch.setenv(key, "")
    settings = LibrarianSettings()
    assert settings.profile_retention_days is None and settings.session_secret is None
    assert settings.oidc_issuer is None and settings.oidc_client_secret is None and settings.api_key is None
    assert settings.log_level == "INFO" and settings.chat_daily_budget_usd == 25.0 and settings.session_ttl_hours == 12


def test_the_shipped_configmap_secret_template_and_env_example_load_as_they_are(monkeypatch):
    values: dict[str, str] = {}
    for name in ("configmap.yaml", "secret.example.yaml"):
        doc = yaml.safe_load((PROJECT / "deploy" / "k8s" / name).read_text(encoding="utf-8"))
        values.update({k: str(v) for k, v in {**(doc.get("data") or {}), **(doc.get("stringData") or {})}.items()})
    for key, value in _env_example().items():
        values.setdefault(key, value)
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    settings = LibrarianSettings()  # must not raise: an operator applies these files as shipped
    assert settings.allow_live is False and settings.atlassian_allow_write is False
    assert settings.profile_retention_days is None and settings.log_format == "json"


def test_settings_errors_name_the_variable_and_never_the_value(monkeypatch):
    monkeypatch.setenv("KB_SESSION_SECRET", "hunter2-far-too-short")
    monkeypatch.setenv("KB_LOG_LEVEL", "loudest")
    monkeypatch.setenv("KB_MAX_TURNS", "many")
    with pytest.raises(ValidationError) as info:
        LibrarianSettings()
    lines = settings_errors(info.value)
    assert len(lines) == 3 and all(
        line.split(":")[0] in {"KB_SESSION_SECRET", "KB_LOG_LEVEL", "KB_MAX_TURNS"} for line in lines
    )
    text = " ".join(lines)
    assert "hunter2" not in text and "loudest" not in text and "many" not in text


def test_insights_settings_have_defaults_and_reject_zero(monkeypatch):
    settings = LibrarianSettings()
    assert settings.chat_log_days == 90 and settings.insights_k == 5
    assert _env_example()["KB_CHAT_LOG_DAYS"] == "90" and _env_example()["KB_INSIGHTS_K"] == "5"
    monkeypatch.setenv("KB_INSIGHTS_K", "0")
    with pytest.raises(ValidationError) as exc:
        LibrarianSettings()
    assert settings_errors(exc.value) == ["KB_INSIGHTS_K: Input should be greater than 0"]
