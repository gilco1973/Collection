"""Command implementations behind the ``kb-librarian`` CLI."""

import asyncio
import json
from datetime import date
from pathlib import Path

from kb_librarian.actions import ActionLog
from kb_librarian.agent.runner import run_agent_audit, run_offline_audit, run_offline_checks
from kb_librarian.agent.task_manager import AuditTaskManager
from kb_librarian.atlassian.client import AtlassianNotConfigured
from kb_librarian.atlassian.confluence import ConfluenceClient
from kb_librarian.atlassian.jira import JiraClient
from kb_librarian.atlassian.sync import sync_sections
from kb_librarian.catalog.catalog import load_catalog, render_index
from kb_librarian.config import LibrarianSettings
from kb_librarian.kbconfig import load_kb_config
from kb_librarian.models import AuditReport, LibrarianAction
from kb_librarian.reports import ReportStore, render_markdown
from kb_librarian.retrieval.build import build_index
from kb_librarian.retrieval.embedder import embedder_from_settings
from kb_librarian.tools.context import SNAPSHOTS_DIR

EXIT_OK, EXIT_FINDINGS, EXIT_FAILED, EXIT_CANCELLED = 0, 1, 2, 3


def _print_summary(report: AuditReport, out) -> None:
    print(json.dumps(report.summary(), indent=1), file=out)
    for finding in report.findings:
        where = f"{finding.path}:{finding.line}" if finding.line else finding.path
        print(f"  {finding.severity:8} {finding.check:11} {where} — {finding.message}", file=out)
    for item in report.manual_review_needed:
        print(f"  REVIEW   {item.severity:8} {item.path} — {item.reason}", file=out)
    if report.ai_summary:
        print("\nLibrarian summary:\n" + report.ai_summary, file=out)
    if report.error:
        print(f"\nERROR: {report.error}", file=out)


def mode_notice(settings: LibrarianSettings, requested_live: bool, out) -> bool:
    dry_run = settings.resolve_dry_run(not requested_live)
    if requested_live and dry_run:
        print("LIVE was requested but KB_ALLOW_LIVE is not true; forced DRY RUN.", file=out)
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}", file=out)
    return dry_run


def cmd_check(root: Path, today: date | None, as_json: bool, out) -> int:
    """Deterministic checks only, nothing persisted: the CI gate."""
    report = run_offline_checks(root, today=today)
    if as_json:
        print(report.model_dump_json(indent=1), file=out)
    else:
        _print_summary(report, out)
    if report.status != "completed":
        return EXIT_FAILED
    blocking = set(load_kb_config(root / "kb.config.yaml").ci.blocking_severities)
    return EXIT_FINDINGS if any(f.severity in blocking for f in report.findings) else EXIT_OK


def cmd_audit(settings: LibrarianSettings, root: Path, args, out) -> int:
    dry_run = mode_notice(settings, args.live, out)
    if args.offline:
        report = run_offline_audit(settings, root, dry_run=dry_run, today=args.today, offline=True)
    else:
        factories, closers = _atlassian_factories(settings, dry_run, out) if args.atlassian else ([], [])
        try:
            report = asyncio.run(
                run_agent_audit(
                    settings,
                    root,
                    dry_run=dry_run,
                    capabilities=args.capabilities,
                    offline=not args.network,
                    today=args.today,
                    max_turns=args.max_turns,
                    max_budget_usd=args.budget,
                    tool_factories=factories,
                )
            )
        finally:
            for close in closers:
                close()
    _print_summary(report, out)
    print(f"\nReport: {root / settings.reports_dir / (report.audit_id + '.md')}", file=out)
    return {"completed": EXIT_OK, "cancelled": EXIT_CANCELLED}.get(report.status, EXIT_FAILED)


def _atlassian_factories(settings: LibrarianSettings, dry_run: bool, out):
    from kb_librarian.tools.atlassian_tools import build_atlassian_tools

    try:
        confluence = ConfluenceClient.from_settings(settings, dry_run=dry_run)
        jira = JiraClient.from_settings(settings, dry_run=dry_run)
    except AtlassianNotConfigured as exc:
        print(f"Atlassian tools disabled: {exc}", file=out)
        return [], []
    return [lambda ctx: build_atlassian_tools(ctx, confluence, jira)], [confluence.close, jira.close]


def cmd_index(root: Path, write: bool, today: date | None, out, *, settings=None, embeddings: bool = False) -> int:
    config = load_kb_config(root / "kb.config.yaml")
    if embeddings:  # the vector index (every page, withheld ones included), not docs/index.md
        print(build_index(root, config, embedder_from_settings(settings or LibrarianSettings())).line, file=out)
        return EXIT_OK
    text = render_index(load_catalog(root, config), config, today=today)
    if write:
        target = root / config.docs_root / "index.md"
        target.write_text(text, encoding="utf-8")
        print(f"wrote {target}", file=out)
    else:
        print(text, file=out, end="")
    return EXIT_OK


def cmd_reports(settings: LibrarianSettings, root: Path, action: str, audit_id: str | None, out) -> int:
    store = ReportStore(root / settings.reports_dir)
    if action == "list":
        for report_id in store.list_ids():
            report = store.load(report_id)
            print(f"{report_id}  {report.audit_type:7} {report.status:11} findings={len(report.findings)}", file=out)
        return EXIT_OK
    if not audit_id:
        print("reports show needs an audit id", file=out)
        return EXIT_FAILED
    try:
        print(render_markdown(store.load(audit_id)), file=out, end="")
    except FileNotFoundError as exc:
        print(str(exc), file=out)
        return EXIT_FINDINGS
    return EXIT_OK


def cmd_rollback(
    settings: LibrarianSettings, root: Path, audit_id: str, action_id: str, reason: str, force: bool, out
) -> int:
    store = ReportStore(root / settings.reports_dir)
    config = load_kb_config(root / "kb.config.yaml")
    try:
        report = store.load(audit_id)
        action = ActionLog(root / config.docs_root, report, root / SNAPSHOTS_DIR).rollback(
            action_id, reason, force=force
        )
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(str(exc), file=out)
        return EXIT_FINDINGS
    store.save(report)
    print(f"rolled back {action.action_id} on {action.path}{' (forced)' if force else ''}", file=out)
    return EXIT_OK


def cmd_cancel(settings: LibrarianSettings, root: Path, audit_id: str, out) -> int:
    store = ReportStore(root / settings.reports_dir)
    try:
        report = store.load(audit_id)
    except FileNotFoundError as exc:
        print(str(exc), file=out)
        return EXIT_FINDINGS
    if report.status != "in_progress":
        print(f"audit {audit_id} is {report.status}; nothing to cancel", file=out)
        return EXIT_FINDINGS
    manager = AuditTaskManager()
    manager.configure(root)
    manager.cancel(audit_id)
    print(f"cancel requested for {audit_id}; the next tool call is denied and the agent is told to stop", file=out)
    return EXIT_OK


def cmd_atlassian_sync(settings: LibrarianSettings, root: Path, live: bool, sections: list[str] | None, out) -> int:
    dry_run = mode_notice(settings, live, out)
    config = load_kb_config(root / "kb.config.yaml")
    try:
        confluence = ConfluenceClient.from_settings(settings, dry_run=dry_run)
    except AtlassianNotConfigured as exc:
        print(str(exc), file=out)
        return EXIT_FAILED
    report = AuditReport(audit_type="offline", dry_run=dry_run, capabilities=["atlassian-sync"])
    try:
        results = sync_sections(load_catalog(root, config), config, confluence, sections)
    finally:
        confluence.close()
    for result in results:
        print(f"{result.action:14} {result.path} → {result.title} {result.detail}", file=out)
        report.fixes_applied.append(
            LibrarianAction(
                audit_id=report.audit_id,
                action_type=f"confluence-sync:{result.action}",
                path=result.path,
                description=result.title,
                dry_run=result.action == "would-publish",
            )
        )
    report.finish("completed")
    ReportStore(root / settings.reports_dir).save(report)
    print(f"\nReport: {root / settings.reports_dir / (report.audit_id + '.md')}", file=out)
    return EXIT_OK
