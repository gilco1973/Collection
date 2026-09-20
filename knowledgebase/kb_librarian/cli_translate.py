"""Content translation CLI command: `kb-librarian translate sync` (the nightly job)."""

import asyncio
from pathlib import Path

from kb_librarian.catalog.catalog import load_catalog
from kb_librarian.cli_commands import EXIT_FINDINGS, EXIT_OK, mode_notice
from kb_librarian.config import LibrarianSettings
from kb_librarian.i18n.sync import load_state, plan, sync
from kb_librarian.kbconfig import load_kb_config
from kb_librarian.models import AuditReport
from kb_librarian.reports import ReportStore


def cmd_translate_sync(settings: LibrarianSettings, root: Path, live: bool, languages: list[str] | None, out) -> int:
    """The nightly job: translate every new/changed page into the configured languages."""
    dry_run = mode_notice(settings, live, out)
    config = load_kb_config(root / "kb.config.yaml")
    langs = languages or config.i18n.languages
    if not langs:
        print("no target languages configured (kb.config.yaml i18n.languages); nothing to do", file=out)
        return EXIT_OK
    catalog = load_catalog(root, config)
    jobs = plan(catalog, langs, load_state(root, config))
    report = AuditReport(audit_type="offline", dry_run=dry_run, capabilities=["translate-sync"])
    results = []
    if not jobs:
        print("everything is translated and up to date", file=out)
    else:
        results = asyncio.run(sync(root, config, jobs, report, model=settings.model))
        for result in results:
            detail = f": {result.error}" if result.error else ""
            print(f"{result.status:9} {result.lang:3} {result.rel_path}{detail}", file=out)
    report.finish("completed")
    ReportStore(root / settings.reports_dir).save(report)
    print(f"\nReport: {root / settings.reports_dir / (report.audit_id + '.md')}", file=out)
    return EXIT_FINDINGS if any(r.status == "failed" for r in results) else EXIT_OK
