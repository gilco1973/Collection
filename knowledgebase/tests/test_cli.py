import io
import json
from pathlib import Path

import pytest

from kb_librarian import cli
from kb_librarian.models import AuditReport
from kb_librarian.reports import ReportStore


def _run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    code = cli.main(list(argv), out=out)
    return code, out.getvalue()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("KB_ALLOW_LIVE", "KB_ATLASSIAN_BASE_URL", "KB_ATLASSIAN_EMAIL", "KB_ATLASSIAN_API_TOKEN"):
        monkeypatch.delenv(key, raising=False)


def test_check_exits_one_on_blocking_findings(kb_root: Path):
    code, out = _run("--root", str(kb_root), "check", "--today", "2026-09-15")
    assert code == 1 and "sensitive" in out and "broken internal link" in out
    code, out = _run("--root", str(kb_root), "check", "--json")
    assert code == 1 and json.loads(out)["audit_type"] == "offline"


def test_check_exits_zero_on_clean_kb(kb_root: Path):
    for name in ("stale.md",):
        (kb_root / "docs" / "onboarding" / name).unlink()
    readme = kb_root / "docs" / "onboarding" / "README.md"
    readme.write_text(readme.read_text().replace(" and the [stale page](stale.md)", ""))
    (kb_root / "docs" / "governance" / "README.md").write_text(
        "---\ntitle: Governance\nowner: risk\nstatus: active\nreviewed: 2026-09-10\n"
        "tags: [governance]\naudience: [everyone]\n---\n# G\n"
    )
    assert _run("--root", str(kb_root), "index", "--write")[0] == 0
    code, out = _run("--root", str(kb_root), "check", "--today", "2026-09-15")
    assert code == 0, out


def test_check_exits_two_when_audit_fails(kb_root: Path):
    (kb_root / "kb.config.yaml").write_text("version: 1\n")
    code, out = _run("--root", str(kb_root), "check")
    assert code == 2 and "ERROR" in out


def test_audit_offline_forces_dry_run_and_writes_report(kb_root: Path):
    code, out = _run("--root", str(kb_root), "audit", "--offline", "--live", "--today", "2026-09-15")
    assert code == 0 and "forced DRY RUN" in out and "Report:" in out
    ids = ReportStore(kb_root / ".librarian/reports").list_ids()
    assert len(ids) == 1
    code, out = _run("--root", str(kb_root), "reports", "list")
    assert code == 0 and ids[0] in out
    code, out = _run("--root", str(kb_root), "reports", "show", ids[0])
    assert code == 0 and out.startswith("# Librarian audit")
    assert _run("--root", str(kb_root), "reports", "show")[0] == 2
    assert _run("--root", str(kb_root), "reports", "show", "audit-nope")[0] == 1


def test_audit_agent_path_uses_injected_query(kb_root: Path, monkeypatch):
    async def fake_run(settings, root, **kwargs):
        report = AuditReport(audit_type="agent", dry_run=kwargs["dry_run"], capabilities=kwargs["capabilities"] or [])
        report.ai_summary = f"turns={kwargs['max_turns']} offline={kwargs['offline']} extra={kwargs['tool_factories']}"
        report.finish("completed")
        ReportStore(root / settings.reports_dir).save(report)
        return report

    monkeypatch.setattr("kb_librarian.cli_commands.run_agent_audit", fake_run)
    code, out = _run(
        "--root", str(kb_root), "audit", "--capabilities", "links,structure", "--max-turns", "3", "--atlassian"
    )
    assert code == 0 and "turns=3 offline=True extra=[]" in out and "Atlassian tools disabled" in out


def test_index_prints_and_writes(kb_root: Path):
    code, out = _run("--root", str(kb_root), "index")
    assert code == 0 and "## Onboarding" in out
    code, out = _run("--root", str(kb_root), "index", "--write")
    assert code == 0 and "wrote" in out and "Stale page" in (kb_root / "docs/index.md").read_text()


def test_rollback_via_cli(kb_root: Path):
    store = ReportStore(kb_root / ".librarian/reports")
    report = AuditReport(audit_type="agent", dry_run=False)
    page = kb_root / "docs/onboarding/README.md"
    before = page.read_text()
    from kb_librarian.actions import ActionLog

    log = ActionLog(kb_root / "docs", report, kb_root / ".librarian/snapshots")
    action = log.write_page("edit", "onboarding/README.md", "edited", "why")
    store.save(report)
    assert page.read_text() == "edited"
    code, out = _run("--root", str(kb_root), "rollback", report.audit_id, action.action_id, "--reason", "undo")
    assert code == 0 and "rolled back" in out and page.read_text() == before
    assert store.load(report.audit_id).fixes_applied[0].rolled_back is True
    code, _ = _run("--root", str(kb_root), "rollback", report.audit_id, "nope", "--reason", "x")
    assert code == 1
    assert _run("--root", str(kb_root), "rollback", "audit-missing", "nope", "--reason", "x")[0] == 1
    second = log.write_page("edit", "onboarding/README.md", "v3", "why")
    store.save(report)
    page.write_text("owner edit")
    assert _run("--root", str(kb_root), "rollback", report.audit_id, second.action_id, "--reason", "x")[0] == 1
    code, out = _run("--root", str(kb_root), "rollback", report.audit_id, second.action_id, "--reason", "x", "--force")
    assert code == 0 and "(forced)" in out and page.read_text() == before


def test_cancel_via_cli(kb_root: Path):
    store = ReportStore(kb_root / ".librarian/reports")
    running = AuditReport(audit_type="agent")
    store.save(running)
    code, out = _run("--root", str(kb_root), "cancel", running.audit_id)
    assert code == 0 and (kb_root / ".librarian/cancel" / running.audit_id).exists()
    done = AuditReport(audit_type="agent")
    done.finish("completed")
    store.save(done)
    assert _run("--root", str(kb_root), "cancel", done.audit_id)[0] == 1
    assert _run("--root", str(kb_root), "cancel", "audit-nope")[0] == 1


def test_check_does_not_persist_a_report(kb_root: Path):
    _run("--root", str(kb_root), "check")
    assert ReportStore(kb_root / ".librarian/reports").list_ids() == []


def test_atlassian_sync_without_configuration(kb_root: Path):
    code, out = _run("--root", str(kb_root), "atlassian", "sync")
    assert code == 2 and "KB_ATLASSIAN_BASE_URL" in out


def test_atlassian_sync_dry_run_with_configuration(kb_root: Path, monkeypatch):
    monkeypatch.setenv("KB_ATLASSIAN_BASE_URL", "https://t.atlassian.net")
    monkeypatch.setenv("KB_ATLASSIAN_EMAIL", "svc@example.com")
    monkeypatch.setenv("KB_ATLASSIAN_API_TOKEN", "tok")
    code, out = _run("--root", str(kb_root), "atlassian", "sync", "--sections", "onboarding")
    assert code == 0 and "would-publish" in out


def test_missing_root_is_reported(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, out = _run("check")
    assert code == 2 and "kb.config.yaml not found" in out
    code, out = _run("--root", str(tmp_path / "nope"), "check")
    assert code == 2 and not (tmp_path / "nope").exists()


def test_translate_sync_with_no_target_languages(kb_root: Path):
    (kb_root / "kb.config.yaml").write_text(
        (kb_root / "kb.config.yaml").read_text().replace("i18n:\n  languages: [es, he]\n", "")
    )
    code, out = _run("--root", str(kb_root), "translate", "sync")
    assert code == 0 and "nothing to do" in out
    assert ReportStore(kb_root / ".librarian/reports").list_ids() == []


def test_translate_sync_dry_run_uses_injected_translator(kb_root: Path, monkeypatch):
    from kb_librarian.i18n.sync import TranslationResult

    async def fake_sync(root, config, jobs, report, **kwargs):
        assert kwargs["model"] == "claude-opus-5"
        return [TranslationResult(j.doc.rel_path, j.lang, "proposed") for j in jobs]

    monkeypatch.setattr("kb_librarian.cli_translate.sync", fake_sync)
    code, out = _run("--root", str(kb_root), "translate", "sync", "--languages", "es")
    assert code == 0 and "proposed  es  onboarding/README.md" in out and "Report:" in out
    ids = ReportStore(kb_root / ".librarian/reports").list_ids()
    assert len(ids) == 1 and ReportStore(kb_root / ".librarian/reports").load(ids[0]).dry_run is True


def test_translate_sync_reports_a_failed_page_via_exit_code(kb_root: Path, monkeypatch):
    from kb_librarian.i18n.sync import TranslationResult

    async def fake_sync(root, config, jobs, report, **kwargs):
        return [TranslationResult(jobs[0].doc.rel_path, jobs[0].lang, "failed", "boom")]

    monkeypatch.setattr("kb_librarian.cli_translate.sync", fake_sync)
    code, out = _run("--root", str(kb_root), "translate", "sync", "--languages", "es")
    assert code == 1 and "failed" in out and "boom" in out


def test_translate_sync_is_a_noop_when_everything_is_up_to_date(kb_root: Path, monkeypatch):
    monkeypatch.setattr("kb_librarian.cli_translate.plan", lambda *a, **k: [])
    code, out = _run("--root", str(kb_root), "translate", "sync")
    assert code == 0 and "up to date" in out
