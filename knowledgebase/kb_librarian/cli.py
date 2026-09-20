"""``kb-librarian`` command line."""

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from kb_librarian import cli_commands as commands
from kb_librarian.api.observability import configure_logging
from kb_librarian.cli_doctor import add_doctor_parser, cmd_doctor
from kb_librarian.cli_evals import add_evals_parser, cmd_eval
from kb_librarian.cli_insights import add_insights_parser, cmd_insights
from kb_librarian.cli_profiles import add_profiles_parser, cmd_profiles
from kb_librarian.cli_translate import cmd_translate_sync
from kb_librarian.config import LibrarianSettings, settings_errors
from kb_librarian.kbconfig import find_kb_root
from kb_librarian.security.cli_security import add_security_parser, cmd_security


def _csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _capabilities(value: str) -> list[str]:
    from kb_librarian.agent.prompts import CAPABILITY_PROMPTS

    names = _csv(value)
    unknown = sorted(set(names) - set(CAPABILITY_PROMPTS))
    if unknown or not names:
        raise argparse.ArgumentTypeError(f"unknown capabilities {unknown}; choose from {sorted(CAPABILITY_PROMPTS)}")
    return names


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kb-librarian", description="Maintain the AI knowledge base.")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="knowledge-base root (default: nearest kb.config.yaml)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="deterministic checks only; exit 1 on error/critical findings (CI gate)")
    check.add_argument("--json", action="store_true")
    check.add_argument("--today", type=date.fromisoformat, default=None)

    audit = sub.add_parser("audit", help="run a librarian audit (dry-run unless --live and KB_ALLOW_LIVE=true)")
    audit.add_argument("--offline", action="store_true", help="deterministic checks only, no LLM")
    mode = audit.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="explicit dry run (the default)")
    mode.add_argument("--live", action="store_true", help="request a live run")
    audit.add_argument("--network", action="store_true", help="verify external links over HTTP")
    audit.add_argument("--atlassian", action="store_true", help="expose Confluence/Jira tools to the agent")
    audit.add_argument("--capabilities", type=_capabilities, default=None)
    audit.add_argument("--max-turns", type=int, default=None)
    audit.add_argument("--budget", type=float, default=None, help="max spend in USD")
    audit.add_argument("--today", type=date.fromisoformat, default=None)

    index = sub.add_parser("index", help="render docs/index.md from the catalog")
    index.add_argument("--write", action="store_true")
    index.add_argument(
        "--embeddings",
        action="store_true",
        help="build the embedding index (.librarian/index) from every page instead of rendering docs/index.md",
    )
    index.add_argument("--today", type=date.fromisoformat, default=None)

    cancel = sub.add_parser("cancel", help="cancel a running audit (next tool call is denied)")
    cancel.add_argument("audit_id")

    reports = sub.add_parser("reports", help="list or show audit reports")
    reports.add_argument("action", choices=["list", "show"])
    reports.add_argument("audit_id", nargs="?")

    rollback = sub.add_parser("rollback", help="undo an applied action")
    rollback.add_argument("audit_id")
    rollback.add_argument("action_id")
    rollback.add_argument("--reason", required=True)
    rollback.add_argument("--force", action="store_true", help="overwrite even if the page changed since the action")

    atlassian = sub.add_parser("atlassian", help="Atlassian integration commands")
    atl_sub = atlassian.add_subparsers(dest="atlassian_command", required=True)
    atl_sync = atl_sub.add_parser("sync", help="mirror configured sections into Confluence")
    atl_sync.add_argument("--live", action="store_true")
    atl_sync.add_argument("--sections", type=_csv, default=None)

    add_doctor_parser(sub)
    translate = sub.add_parser("translate", help="content translation commands")
    tr_sub = translate.add_subparsers(dest="translate_command", required=True)
    tr_sync = tr_sub.add_parser(
        "sync", help="translate new/changed pages into the configured languages (the nightly job)"
    )
    tr_sync.add_argument("--live", action="store_true")
    tr_sync.add_argument("--languages", type=_csv, default=None, help="override kb.config.yaml's i18n.languages")
    add_insights_parser(sub)
    add_security_parser(sub)
    add_profiles_parser(sub)
    add_evals_parser(sub)
    return parser


def main(argv: list[str] | None = None, out=None) -> int:
    out = out or sys.stdout
    args = build_parser().parse_args(argv)
    try:
        settings = LibrarianSettings()
    except ValidationError as exc:  # one line per variable, never its value, never a traceback
        for line in settings_errors(exc):
            print(f"FAIL settings — {line}", file=out)
        return 2
    configure_logging(settings)
    env_root = Path(os.environ["KB_ROOT"]) if os.environ.get("KB_ROOT") else None  # the deployment's convention
    try:
        root = (args.root or env_root or find_kb_root()).resolve()
        if not (root / "kb.config.yaml").is_file():
            raise FileNotFoundError(f"kb.config.yaml not found in {root}")
    except FileNotFoundError as exc:
        print(str(exc), file=out)
        return 2
    if args.command == "check":
        return commands.cmd_check(root, args.today, args.json, out)
    if args.command == "doctor":
        return cmd_doctor(settings, root, args, out)
    if args.command == "insights":
        return cmd_insights(settings, root, args, out)
    if args.command == "audit":
        return commands.cmd_audit(settings, root, args, out)
    if args.command == "index":
        return commands.cmd_index(root, args.write, args.today, out, settings=settings, embeddings=args.embeddings)
    if args.command == "cancel":
        return commands.cmd_cancel(settings, root, args.audit_id, out)
    if args.command == "reports":
        return commands.cmd_reports(settings, root, args.action, args.audit_id, out)
    if args.command == "rollback":
        return commands.cmd_rollback(settings, root, args.audit_id, args.action_id, args.reason, args.force, out)
    if args.command == "translate":
        return cmd_translate_sync(settings, root, args.live, args.languages, out)
    if args.command == "profiles":
        return cmd_profiles(settings, root, args, out)
    if args.command == "eval":
        return cmd_eval(settings, root, args, out)
    if args.command == "security":
        return cmd_security(root, args, out)
    return commands.cmd_atlassian_sync(settings, root, args.live, args.sections, out)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
