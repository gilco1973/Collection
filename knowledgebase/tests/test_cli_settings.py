"""The CLI and the server on a bad environment: one diagnostic line per rejected setting, exit 2, never a
traceback and never the offending value; ``KB_ROOT`` locates the project like ``--root`` does."""

import io
import runpy
from pathlib import Path

import pytest

from kb_librarian import cli

PROJECT = Path(__file__).resolve().parents[1]
BAD_SECRET = "short-value-9"


def _run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    return cli.main(list(argv), out=out), out.getvalue()


def test_an_invalid_setting_is_one_fail_line_and_exit_two_not_a_traceback(kb_root: Path, monkeypatch):
    monkeypatch.setenv("KB_SESSION_SECRET", BAD_SECRET)
    monkeypatch.setenv("KB_LOG_LEVEL", "loudest")
    for command in (["doctor"], ["check"], ["profiles", "stats"]):
        code, out = _run("--root", str(kb_root), *command)
        lines = out.strip().splitlines()
        assert code == 2 and len(lines) == 2, out
        assert lines[0].startswith("FAIL settings — KB_LOG_LEVEL: ") and lines[1].startswith(
            "FAIL settings — KB_SESSION_SECRET: "
        )
        assert BAD_SECRET not in out and "loudest" not in out and "Traceback" not in out


def test_kb_root_locates_the_project_for_every_command(kb_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # nowhere near a kb.config.yaml
    monkeypatch.setenv("KB_ROOT", str(kb_root))
    code, out = _run("profiles", "stats")
    assert code == 0 and out.startswith("count=")
    monkeypatch.setenv("KB_ROOT", str(tmp_path / "nowhere"))
    code, out = _run("check")
    assert code == 2 and "kb.config.yaml not found" in out
    code, out = _run("--root", str(kb_root), "profiles", "stats")  # --root still wins over the variable
    assert code == 0 and out.startswith("count=")


def test_serve_exits_two_with_a_diagnostic_on_an_invalid_setting(kb_root: Path, monkeypatch, capsys):
    monkeypatch.setenv("KB_ROOT", str(kb_root))
    monkeypatch.setenv("KB_SESSION_SECRET", BAD_SECRET)
    with pytest.raises(SystemExit) as info:
        runpy.run_path(str(PROJECT / "deploy" / "serve.py"), run_name="serve_under_test")
    err = capsys.readouterr().err
    assert info.value.code == 2 and "FAIL settings — KB_SESSION_SECRET: " in err
    assert BAD_SECRET not in err and "Traceback" not in err
