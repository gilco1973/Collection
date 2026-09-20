"""``kb-librarian security`` end to end, and the project-wide coverage guarantee of the registry."""

import json
import subprocess
from pathlib import Path

import pytest

from kb_librarian.security.registry import SIGNOFF_HEADING, compute_version, git_commit, load_registry
from tests.security_fixtures import PROJECT_ROOT, make_project, run_cli


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return make_project(tmp_path)


def _sign(project: Path, decision: str, notes: str = "") -> tuple[int, str]:
    return run_cli(
        "--root", str(project), "security", "sign", "demo", "--reviewer", "A. Reviewer", "--signature", "ssh:abc",
        "--decision", decision, "--notes", notes, "--date", "2026-09-18",
    )  # fmt: skip


def test_status_submit_sign_and_verify(project: Path):
    code, out = run_cli("--root", str(project), "security", "status")
    assert code == 0 and "demo" in out and "unsigned" in out
    code, out = run_cli("--root", str(project), "security", "verify")
    assert code == 1 and "demo: unsigned" in out
    code, out = run_cli("--root", str(project), "security", "submit", "demo")
    assert code == 0 and "## File manifest" in out and "`pkg/a.py`" in out and "kb-librarian security sign demo" in out
    code, out = _sign(project, "conditional", "fix X")
    assert code == 0 and "recorded conditional for demo" in out
    ledger = json.loads((project / "security" / "signoffs" / "demo.json").read_text())
    assert ledger[0]["notes"] == "fix X" and ledger[0]["date"] == "2026-09-18" and len(ledger[0]["version"]) == 64
    code, out = run_cli("--root", str(project), "security", "verify")
    assert code == 1 and "demo: conditional (fix X)" in out and "0/1 modules approved" in out
    code, out = run_cli("--root", str(project), "security", "verify", "--allow-conditional")
    assert code == 0 and "1/1 modules approved" in out
    assert _sign(project, "approved")[0] == 0
    code, out = run_cli("--root", str(project), "security", "verify")
    assert code == 0 and "1/1 modules approved" in out
    (project / "pkg" / "a.py").write_text("print('changed')\n")
    code, out = run_cli("--root", str(project), "security", "verify")
    assert code == 1 and "demo: changed" in out
    assert _sign(project, "rejected")[0] == 0
    code, out = run_cli("--root", str(project), "security", "verify")
    assert code == 1 and "demo: rejected" in out


def test_errors_are_reported_not_raised(project: Path):
    code, out = run_cli("--root", str(project), "security", "submit", "nope")
    assert code == 2 and "no module 'nope'" in out
    (project / "security" / "registry.yaml").write_text("version: [1\n")
    code, out = run_cli("--root", str(project), "security", "status")
    assert code == 2 and out.startswith("ERROR:")


def test_git_commit_tolerates_a_missing_git(monkeypatch, tmp_path: Path):
    def boom(*args, **kwargs):
        raise OSError("no git")

    monkeypatch.setattr(subprocess, "run", boom)
    assert git_commit(tmp_path) is None
    monkeypatch.undo()
    commit = git_commit(PROJECT_ROOT)
    assert commit is None or len(commit) == 12


def test_project_registry_covers_every_reviewable_file():
    """Every source, config, dependency, deploy and CI file is in exactly one reviewed module."""
    registry = load_registry(PROJECT_ROOT)
    covered: dict[str, str] = {}
    for module in registry.modules:
        assert SIGNOFF_HEADING in (PROJECT_ROOT / module.sheet).read_text(encoding="utf-8"), module.id
        for test in module.tests:
            assert (PROJECT_ROOT / test).exists(), f"{module.id}: listed test {test} does not exist"
        for rel, _ in compute_version(PROJECT_ROOT, module).files:
            assert rel not in covered, f"{rel} is in both {covered[rel]} and {module.id}"
            covered[rel] = module.id
    patterns = (
        "kb_librarian/**/*.py", "web/src/**/*.ts", "web/src/**/*.tsx", "web/*.json", "web/*.js", "web/*.ts",
        "web/index.html", "web/scripts/*", "deploy/*", "scripts/*", ".github/**/*", "pyproject.toml", "poetry.lock",
    )  # fmt: skip
    sources = {
        p.relative_to(PROJECT_ROOT).as_posix()
        for pattern in patterns
        for p in PROJECT_ROOT.glob(pattern)
        if p.is_file() and "/test/" not in p.as_posix() and "__pycache__" not in p.parts
    }
    assert sources - set(covered) == set(), f"unreviewed files: {sorted(sources - set(covered))}"
