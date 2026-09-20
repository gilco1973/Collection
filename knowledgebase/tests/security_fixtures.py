"""Shared scaffolding for the security-review tests: a tiny registered project and helpers."""

import io
from datetime import date
from pathlib import Path

from kb_librarian import cli
from kb_librarian.security.ledger import SignOff

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHEET = "# Security review sheet: Demo\n\n## Purpose\n\nDemo.\n\n## Sign-off\n\nSubmit, then sign.\n"
TABLE = (
    "| Version | Commit | Reviewer | Signature | Date | Decision | Notes |\n"
    "| --- | --- | --- | --- | --- | --- | --- |\n"
)
REGISTRY = (
    "version: 1\nmodules:\n  - id: demo\n    title: Demo\n    kind: backend\n"
    "    paths: [pkg/]\n    tests: [tests/test_demo.py]\n    sheet: security/modules/demo.md\n"
)


def make_project(tmp_path: Path) -> Path:
    """A project with one registered module, a sheet and kb.config.yaml (the CLI insists on it)."""
    (tmp_path / "kb.config.yaml").write_text("version: 1\n")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("print('a')\n")
    (tmp_path / "pkg" / "b.py").write_text("print('b')\n")
    (tmp_path / "security" / "modules").mkdir(parents=True)
    (tmp_path / "security" / "modules" / "demo.md").write_text(SHEET + "\n" + TABLE)
    (tmp_path / "security" / "registry.yaml").write_text(REGISTRY)
    return tmp_path


def signoff(version: str, decision: str = "approved", signature: str = "s", when: date = date(2026, 9, 18)) -> SignOff:
    return SignOff(module="demo", version=version, reviewer="R", signature=signature, date=when, decision=decision)


def run_cli(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    return cli.main(list(argv), out=out), out.getvalue()
