"""``kb-librarian insights [--json] [--window-days N]`` and ``insights prune``.

``insights`` regenerates ``.librarian/insights/latest.json`` from reader records, problem reports
and chat telemetry (``insights/collect.py``: counts and rates under k-anonymity, withheld pages
excluded through the same verdict the reader API uses) and prints the top pages by problem
reports, by quiz fail rate, and the unanswered-question counts — paths and numbers only.
``insights prune`` drops chat telemetry lines older than ``KB_CHAT_LOG_DAYS``: the retention
sibling of ``profiles purge``, meant for the same scheduled job.
"""

from datetime import UTC, datetime
from pathlib import Path

from kb_librarian.api import service
from kb_librarian.catalog.catalog import load_catalog
from kb_librarian.chat import telemetry
from kb_librarian.cli_commands import EXIT_OK
from kb_librarian.config import LibrarianSettings
from kb_librarian.insights import store
from kb_librarian.insights.collect import DEFAULT_WINDOW_DAYS, collect
from kb_librarian.insights.models import Insights
from kb_librarian.kbconfig import load_kb_config
from kb_librarian.reports import ReportStore

TOP = 10


def add_insights_parser(sub) -> None:
    insights = sub.add_parser("insights", help="which pages confuse people: regenerate and print the aggregates")
    insights.add_argument("--json", action="store_true", help="print the stored file instead of the summary")
    insights.add_argument(
        "--window-days", type=int, default=DEFAULT_WINDOW_DAYS, help=f"look-back window (default {DEFAULT_WINDOW_DAYS})"
    )
    ins = insights.add_subparsers(dest="insights_command")
    ins.add_parser("prune", help="drop chat telemetry lines older than KB_CHAT_LOG_DAYS")


def cmd_insights(settings: LibrarianSettings, root: Path, args, out) -> int:
    if getattr(args, "insights_command", None) == "prune":
        removed = telemetry.prune(root, settings.chat_log_days)
        print(f"removed={removed} older_than_days={settings.chat_log_days}", file=out)
        return EXIT_OK
    window_days = max(1, int(args.window_days))
    config = load_kb_config(root / "kb.config.yaml")
    catalog = load_catalog(root, config)
    withheld = service.withheld_paths(catalog, ReportStore(root / settings.reports_dir).latest_completed())
    insights = collect(
        root, config, catalog, withheld, k=settings.insights_k, window_days=window_days, now=datetime.now(UTC)
    )
    store.write(root, insights)
    if args.json:
        print(insights.model_dump_json(indent=1), file=out)
    else:
        _print_summary(insights, out)
    return EXIT_OK


def _print_summary(insights: Insights, out) -> None:
    print(
        f"generated_at={insights.generated_at.isoformat()} window_days={insights.window_days} k={insights.k} "
        f"pages={len(insights.pages)} suppressed={insights.suppressed}",
        file=out,
    )
    print("Top pages by problem reports:", file=out)
    by_problems = sorted(
        ((sum(p.problems.values()), path, p) for path, p in insights.pages.items() if p.problems),
        key=lambda item: (-item[0], item[1]),
    )
    for total, path, page in by_problems[:TOP]:
        categories = " ".join(f"{name}={n}" for name, n in sorted(page.problems.items()))
        print(f"  {total}  {path}  {categories}", file=out)
    print("Top pages by quiz fail rate:", file=out)
    by_fail = sorted(
        ((p.quiz_fail_rate, path, p) for path, p in insights.pages.items() if p.quiz_fail_rate is not None),
        key=lambda item: (-item[0], item[1]),
    )
    for rate, path, page in by_fail[:TOP]:
        print(f"  {rate:.2f}  {path}  attempts={page.quiz_attempts}", file=out)
    for dimension in ("mode", "lang"):
        counts = insights.unanswered.get(dimension, {})
        print(f"Unanswered by {dimension}:", file=out)
        print("  " + (" ".join(f"{key}={n}" for key, n in sorted(counts.items())) or "-"), file=out)
