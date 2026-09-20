from pathlib import Path

import pytest
from pydantic import ValidationError

from kb_librarian.config import LibrarianSettings
from kb_librarian.kbconfig import find_kb_root, load_kb_config
from kb_librarian.models import AuditReport, LibrarianAction
from kb_librarian.reports import ReportStore, render_markdown


def test_dry_run_is_forced_unless_live_is_allowed(monkeypatch):
    monkeypatch.delenv("KB_ALLOW_LIVE", raising=False)
    settings = LibrarianSettings()
    assert settings.resolve_dry_run(False) is True
    assert settings.resolve_dry_run(True) is True
    live = LibrarianSettings(allow_live=True)
    assert live.resolve_dry_run(False) is False
    assert live.resolve_dry_run(True) is True


def test_atlassian_configured_requires_all_three(monkeypatch):
    for key in ("KB_ATLASSIAN_BASE_URL", "KB_ATLASSIAN_EMAIL", "KB_ATLASSIAN_API_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    assert LibrarianSettings().atlassian_configured is False
    full = LibrarianSettings(
        _env_file=None,
        atlassian_base_url="https://x.atlassian.net",
        atlassian_email="a@b",
        atlassian_api_token="tok-secret-value",
    )
    assert full.atlassian_configured is True
    assert "tok-secret-value" not in repr(full.atlassian_api_token)


def test_log_and_chat_ceiling_settings_are_validated_and_normalised(monkeypatch):
    for key in ("KB_LOG_LEVEL", "KB_LOG_FORMAT", "KB_CHAT_DAILY_BUDGET_USD"):
        monkeypatch.delenv(key, raising=False)
    defaults = LibrarianSettings()
    assert (defaults.log_level, defaults.log_format, defaults.chat_daily_budget_usd) == ("INFO", "json", 25.0)
    assert LibrarianSettings(log_level="debug").log_level == "DEBUG"
    assert LibrarianSettings(log_level=" Warning ").log_level == "WARNING"
    monkeypatch.setenv("KB_LOG_LEVEL", "error")
    monkeypatch.setenv("KB_LOG_FORMAT", "text")
    monkeypatch.setenv("KB_CHAT_DAILY_BUDGET_USD", "3.5")
    from_env = LibrarianSettings()
    assert (from_env.log_level, from_env.log_format, from_env.chat_daily_budget_usd) == ("ERROR", "text", 3.5)
    rejected = (
        {"log_level": "verbose"},
        {"log_level": "critical"},
        {"log_format": "xml"},
        {"chat_daily_budget_usd": 0},
    )
    for bad in rejected:
        with pytest.raises(ValidationError):
            LibrarianSettings(**bad)


def test_kb_config_rejects_duplicate_sections(tmp_path: Path, kb_root: Path):
    text = (kb_root / "kb.config.yaml").read_text()
    bad = tmp_path / "bad.yaml"
    bad.write_text(text.replace("  - id: governance", "  - id: onboarding"))
    with pytest.raises(ValidationError):
        load_kb_config(bad)


def test_kb_config_rejects_non_mapping(tmp_path: Path):
    bad = tmp_path / "list.yaml"
    bad.write_text("- a\n")
    with pytest.raises(ValueError):
        load_kb_config(bad)


def test_find_kb_root_walks_up(kb_root: Path, tmp_path: Path):
    assert find_kb_root(kb_root / "docs" / "onboarding") == kb_root.resolve()
    with pytest.raises(FileNotFoundError):
        find_kb_root(tmp_path / "elsewhere")


def test_section_for_prefers_longest_prefix(kb_config):
    assert kb_config.section_for("onboarding/x.md").id == "onboarding"
    assert kb_config.section_for("onboardingX/x.md") is None
    assert kb_config.section_by_id("nope") is None


def test_report_summary_and_finish():
    report = AuditReport(audit_type="offline")
    report.fixes_applied.append(
        LibrarianAction(audit_id=report.audit_id, action_type="x", path="p", description="d", dry_run=True)
    )
    report.fixes_applied.append(
        LibrarianAction(audit_id=report.audit_id, action_type="x", path="p", description="d", dry_run=False)
    )
    report.finish("completed")
    summary = report.summary()
    assert summary["fixes_applied"] == 1 and summary["fixes_proposed"] == 1
    assert report.completed_at is not None and report.execution_time_seconds >= 0


def test_report_store_round_trip_and_listing(tmp_path: Path):
    store = ReportStore(tmp_path / "reports")
    first = AuditReport(audit_type="offline")
    first.finish("failed", error="boom")
    store.save(first)
    second = AuditReport(audit_type="agent", ai_summary="all good")
    store.save(second)
    assert store.load(first.audit_id).error == "boom"
    assert set(store.list_ids()) == {first.audit_id, second.audit_id}
    assert store.latest() is not None
    markdown = render_markdown(second)
    assert "all good" in markdown and "_None._" in markdown
    assert "boom" in render_markdown(first)
    with pytest.raises(FileNotFoundError):
        store.load("missing")
    assert ReportStore(tmp_path / "empty").latest() is None
