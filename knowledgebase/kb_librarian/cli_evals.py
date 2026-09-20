"""``kb-librarian eval``: run the golden set through the librarian chat and score it.

Read-only by construction (the chat runner offers no write tool) and bounded by ``--budget``. Exit
0 when every threshold in ``kb.config.yaml`` ``evals:`` passes, 1 when one is missed, 2 when the
golden file is invalid, no item matched, or every item errored (typically: no usable credential).
"""

import asyncio
import json
from pathlib import Path

from claude_agent_sdk import query as sdk_query

from kb_librarian.cli_commands import EXIT_FAILED, EXIT_FINDINGS, EXIT_OK
from kb_librarian.config import LibrarianSettings
from kb_librarian.evals.items import DEFAULT_GOLDEN, GoldenError, load_golden
from kb_librarian.evals.report import run_to_dict
from kb_librarian.evals.runner import EvalRun, run_eval
from kb_librarian.kbconfig import load_kb_config

ALL_ERRORED = (
    "every item errored: no usable credential path? (ANTHROPIC_API_KEY / CLAUDE_CODE_OAUTH_TOKEN /"
    " the bundled CLI's store) — run `kb-librarian doctor --model`"
)


def add_evals_parser(sub) -> None:
    ev = sub.add_parser("eval", help="run evals/golden.yaml through the librarian chat and score it; exit 0/1/2")
    ev.add_argument("--items", type=int, default=None, help="run only the first N items")
    ev.add_argument("--budget", type=float, default=None, help="stop before exceeding this spend in USD")
    ev.add_argument("--json", action="store_true", help="print the run as JSON instead of the table")
    ev.add_argument("--lang", default=None, help="run only the items in this language (en, or a configured one)")
    ev.add_argument("--golden", type=Path, default=None, help="golden file (default: evals/golden.yaml)")


def _print_table(run: EvalRun, out) -> None:
    summary = run.summary
    print(f"{'item':32} {'status':7} {'prec':>5} {'rec':>5} {'kw':>4} {'ref':>4} {'cost':>8} {'ms':>6}", file=out)
    for r in run.results:
        cost = "-" if r.cost_usd is None else f"{r.cost_usd:.4f}"
        print(
            f"{r.id:32} {r.status:7} {r.citation_precision:5.2f} {r.citation_recall:5.2f}"
            f" {'ok' if r.keywords_ok else 'miss':>4} {'ok' if r.refusal_ok else 'miss':>4}"
            f" {cost:>8} {r.duration_ms:>6}",
            file=out,
        )
    print(
        f"items={summary.items} scored={summary.scored} errors={summary.errors} skipped={summary.skipped}"
        f" keywords_rate={summary.keywords_rate} total_cost_usd={summary.total_cost_usd}"
        f" avg_duration_ms={summary.avg_duration_ms}",
        file=out,
    )
    print(f"Reports: {run.json_path} {run.md_path}", file=out)
    for check in summary.checks:
        verdict = "PASS" if check.passed else "FAIL"
        print(f"{verdict} {check.name} {check.value} (threshold {check.threshold})", file=out)


def cmd_eval(settings: LibrarianSettings, root: Path, args, out) -> int:
    golden = args.golden or root / DEFAULT_GOLDEN
    try:
        items = load_golden(golden, root)
    except GoldenError as exc:
        print(f"invalid golden file: {exc}", file=out)
        return EXIT_FAILED
    if args.lang is not None:
        items = [i for i in items if i.lang == args.lang]
    if args.items is not None:
        items = items[: max(args.items, 0)]
    if not items:
        print("no items to run (check --items / --lang)", file=out)
        return EXIT_FAILED
    thresholds = load_kb_config(root / "kb.config.yaml").evals
    budget = args.budget if args.budget is not None else thresholds.max_cost_usd_per_run
    run = asyncio.run(
        run_eval(settings, root, items, budget_usd=budget, query_fn=sdk_query, golden_path=golden, out=None)
    )
    if run.summary.scored == 0 and run.summary.errors > 0:
        print(ALL_ERRORED, file=out)
        print(f"Reports: {run.json_path} {run.md_path}", file=out)
        return EXIT_FAILED
    if args.json:
        print(json.dumps(run_to_dict(run), indent=1, ensure_ascii=False), file=out)
    else:
        _print_table(run, out)
    return EXIT_OK if run.summary.passed else EXIT_FINDINGS
