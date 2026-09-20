"""``kb-librarian security ...``: status, submission packets, sign-offs and drift verification."""

from datetime import date
from pathlib import Path

import yaml

from kb_librarian.security.ledger import SignOff, module_status, record_signoff
from kb_librarian.security.registry import ModuleSpec, compute_version, git_commit, load_registry

EXIT_OK, EXIT_DRIFT, EXIT_FAILED = 0, 1, 2
_BLOCKING = ("unsigned", "changed", "rejected")


def add_security_parser(sub) -> None:
    security = sub.add_parser("security", help="security review package: status, submit, sign, verify")
    sec = security.add_subparsers(dest="security_command", required=True)
    sec.add_parser("status", help="every module with its current version and sign-off state")
    submit = sec.add_parser("submit", help="print the submission packet for one module (sheet + file manifest)")
    submit.add_argument("module")
    sign = sec.add_parser("sign", help="record a reviewer's sign-off for a module's current version")
    sign.add_argument("module")
    sign.add_argument("--reviewer", required=True, help="reviewer name or id")
    sign.add_argument("--signature", required=True, help="the reviewer's signature (typed, or a detached-signature id)")
    sign.add_argument("--decision", required=True, choices=["approved", "conditional", "rejected"])
    sign.add_argument("--date", type=date.fromisoformat, default=None, help="ISO date (default: today)")
    sign.add_argument("--notes", default="")
    verify = sec.add_parser("verify", help="exit 1 unless every module is approved at its current version")
    verify.add_argument("--allow-conditional", action="store_true", help="treat 'conditional' as passing")


def cmd_security(root: Path, args, out) -> int:
    try:
        registry = load_registry(root)
        if args.security_command == "status":
            return _status(root, registry.modules, out)
        if args.security_command == "verify":
            return _verify(root, registry.modules, args.allow_conditional, out)
        module = registry.get(args.module)
        if args.security_command == "submit":
            return _submit(root, module, out)
        return _sign(root, module, args, out)
    except (KeyError, ValueError, FileNotFoundError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=out)
        return EXIT_FAILED


def _status(root: Path, modules: list[ModuleSpec], out) -> int:
    print(f"{'module':<22} {'kind':<9} {'version':<13} {'status':<12} {'signed version':<15} reviewer / date", file=out)
    for module in modules:
        current = compute_version(root, module)
        status, last = module_status(root, current)
        signed = last.version[:12] if last else "-"
        who = f"{last.reviewer} / {last.date.isoformat()}" if last else "-"
        print(f"{module.id:<22} {module.kind:<9} {current.short:<13} {status:<12} {signed:<15} {who}", file=out)
    return EXIT_OK


def _verify(root: Path, modules: list[ModuleSpec], allow_conditional: bool, out) -> int:
    problems, conditional = [], []
    for module in modules:
        status, last = module_status(root, compute_version(root, module))
        if status in _BLOCKING:
            problems.append(f"{module.id}: {status}")
        elif status == "conditional":
            conditional.append(f"{module.id}: conditional ({last.notes or 'no notes'})" if last else module.id)
    for line in [*problems, *conditional]:
        print(line, file=out)
    passing = len(modules) - len(problems) - (0 if allow_conditional else len(conditional))
    print(f"{passing}/{len(modules)} modules approved at their current version", file=out)
    return EXIT_DRIFT if problems or (conditional and not allow_conditional) else EXIT_OK


def _submit(root: Path, module: ModuleSpec, out) -> int:
    current = compute_version(root, module)
    status, last = module_status(root, current)
    print(f"# Security review submission: {module.title}", file=out)
    print(f"\n- Module: `{module.id}` ({module.kind})", file=out)
    print(f"- Version: `{current.version}` (commit `{git_commit(root) or 'n/a'}`)", file=out)
    last_text = f" (last: {last.reviewer}, {last.date.isoformat()})" if last else ""
    print(f"- Sign-off state: {status}{last_text}", file=out)
    print(f"- Sheet: `{module.sheet}`", file=out)
    print(f"- Tests: {', '.join(f'`{t}`' for t in module.tests) or 'none listed'}", file=out)
    print("\n## File manifest\n\n| File | SHA-256 |\n| --- | --- |", file=out)
    for rel, digest in current.files:
        print(f"| `{rel}` | `{digest}` |", file=out)
    print("\n## Review sheet\n", file=out)
    print((root / module.sheet).read_text(encoding="utf-8").rstrip("\n"), file=out)
    print(
        "\n## To sign\n\n```\nkb-librarian security sign "
        f'{module.id} --reviewer "<name>" --signature "<signature>" --decision approved|conditional|rejected\n```',
        file=out,
    )
    return EXIT_OK


def _sign(root: Path, module: ModuleSpec, args, out) -> int:
    current = compute_version(root, module)
    signoff = SignOff(
        module=module.id,
        version=current.version,
        commit=git_commit(root),
        reviewer=args.reviewer,
        signature=args.signature,
        date=args.date or date.today(),
        decision=args.decision,
        notes=args.notes,
    )
    path = record_signoff(root, current, signoff)
    print(f"recorded {signoff.decision} for {module.id} @ {current.short} by {signoff.reviewer} -> {path}", file=out)
    return EXIT_OK
