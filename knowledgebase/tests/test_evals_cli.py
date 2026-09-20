"""``kb-librarian eval``: exit codes, --items, --json, --lang, --golden."""

import io
import json
from pathlib import Path

import pytest

from kb_librarian import cli, cli_evals
from tests.evals_helpers import GOOD_ANSWER, ITEMS, REFUSAL, Router, reads, says, scripted, write_golden


def _run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    code = cli.main(list(argv), out=out)
    return code, out.getvalue()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("KB_ALLOW_LIVE", raising=False)


def _passing_items() -> list[dict]:
    return [ITEMS[0], ITEMS[1]]


def test_eval_exits_zero_when_every_threshold_passes(kb_root: Path, monkeypatch):
    write_golden(kb_root, _passing_items())
    monkeypatch.setattr(cli_evals, "sdk_query", scripted())
    code, out = _run("--root", str(kb_root), "eval")
    assert code == 0, out
    assert "PASS citation_precision" in out and "PASS refusal_correctness" in out and "PASS max_cost_usd_per_run" in out
    assert "onb-start" in out and "ref-cafeteria" in out and GOOD_ANSWER not in out
    assert (kb_root / ".librarian" / "evals").glob("*.json")


def test_eval_exits_one_when_a_threshold_is_missed(kb_root: Path, monkeypatch):
    write_golden(kb_root, _passing_items())
    monkeypatch.setattr(cli_evals, "sdk_query", Router({"get started": says("Read the governance page. It helps.")}))
    code, out = _run("--root", str(kb_root), "eval")
    assert code == 1 and "FAIL citation_recall" in out and "PASS refusal_correctness" not in out


def test_eval_exits_two_on_an_invalid_golden_file(kb_root: Path, monkeypatch):
    write_golden(kb_root, [{**ITEMS[0], "expect": {"paths": ["onboarding/stale.md"]}}])
    monkeypatch.setattr(cli_evals, "sdk_query", scripted())
    code, out = _run("--root", str(kb_root), "eval")
    assert code == 2 and "withheld" in out
    code, out = _run("--root", str(kb_root), "eval", "--golden", str(kb_root / "nowhere.yaml"))
    assert code == 2 and "not found" in out


def test_eval_exits_two_when_every_item_errored(kb_root: Path, monkeypatch):
    write_golden(kb_root, _passing_items())
    monkeypatch.setattr(cli_evals, "sdk_query", says("", is_error=True, subtype="error_during_execution"))
    code, out = _run("--root", str(kb_root), "eval")
    assert code == 2 and "every item errored" in out and "credential" in out


def test_eval_items_json_lang_and_golden_flags(kb_root: Path, monkeypatch):
    golden = write_golden(kb_root, name="other.yaml")
    monkeypatch.setattr(cli_evals, "sdk_query", scripted())
    flags = ("--items", "2", "--json", "--golden", str(golden), "--budget", "1.5")
    code, out = _run("--root", str(kb_root), "eval", *flags)
    data = json.loads(out)
    assert code == 0 and [r["id"] for r in data["results"]] == ["onb-start", "ref-cafeteria"]
    assert data["budget_usd"] == 1.5
    code, out = _run("--root", str(kb_root), "eval", "--lang", "es", "--golden", str(golden))
    assert code == 0 and "ref-cafeteria" in out and "onb-start" not in out
    code, out = _run("--root", str(kb_root), "eval", "--lang", "fr", "--golden", str(golden))
    assert code == 2 and "no items" in out


def test_eval_uses_the_configured_thresholds(kb_root: Path, monkeypatch):
    config = kb_root / "kb.config.yaml"
    config.write_text(config.read_text() + "evals:\n  citation_recall: 0.5\n  max_cost_usd_per_run: 0.01\n")
    write_golden(kb_root, _passing_items())
    monkeypatch.setattr(cli_evals, "sdk_query", scripted())
    code, out = _run("--root", str(kb_root), "eval")
    assert code == 1 and "FAIL max_cost_usd_per_run" in out and "PASS citation_recall" in out


def test_eval_help_lists_the_flags():
    parser = cli.build_parser()
    text = parser.format_help()
    assert "eval" in text
    ns = parser.parse_args(["eval", "--items", "3", "--budget", "2", "--json", "--lang", "he"])
    assert ns.command == "eval" and ns.items == 3 and ns.budget == 2.0 and ns.json
    assert ns.lang == "he" and ns.golden is None
    assert REFUSAL and reads  # helpers shared with the runner tests stay importable
