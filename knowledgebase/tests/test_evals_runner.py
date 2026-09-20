"""kb_librarian/evals/runner + report: a run through ``run_chat`` with a scripted FakeQuery."""

import json
from datetime import date
from pathlib import Path

from kb_librarian.evals.items import load_golden
from kb_librarian.evals.runner import run_eval
from tests.evals_helpers import GOOD_ANSWER, Router, reads, says, scripted, write_golden
from tests.fake_query import FakeQuery, _result, _settings

TODAY = date(2026, 9, 15)


async def test_run_writes_json_and_markdown_with_the_agreed_fields(kb_root: Path):
    golden = write_golden(kb_root)
    items = load_golden(golden, kb_root)
    router = scripted()
    run = await run_eval(_settings(), kb_root, items, budget_usd=5.0, query_fn=router, golden_path=golden, today=TODAY)
    assert [r.status for r in run.results] == ["scored"] * 3
    good, refusal, missing = run.results
    assert good.citation_precision == 1.0 and good.citation_recall == 1.0 and good.keywords_ok and good.refusal_ok
    assert refusal.refused and refusal.refusal_ok and refusal.sources == []
    assert missing.citation_recall == 1.0 and not missing.keywords_ok
    assert run.summary.total_cost_usd == 0.06 and run.summary.scored == 3
    assert "menú de la cafetería" in "".join(router.prompts)  # the Spanish item went through in Spanish
    json_path, md_path = run.json_path, run.md_path
    assert json_path == kb_root / ".librarian" / "evals" / "2026-09-15.json" and md_path.suffix == ".md"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["date"] == "2026-09-15" and data["model"] == _settings().model and data["effort"] == _settings().effort
    assert data["golden_sha256"] == run.golden_sha256 and len(data["golden_sha256"]) == 64
    assert data["budget_usd"] == 5.0 and data["lang"] is None and data["items_run"] == 3
    assert [r["id"] for r in data["results"]] == ["onb-start", "ref-cafeteria", "gov-what"]
    assert data["results"][0]["answer"] == GOOD_ANSWER and data["results"][0]["question"] == "how do I get started?"
    assert data["summary"]["passed"] is True and data["summary"]["keywords_rate"] == 0.6667
    md = md_path.read_text(encoding="utf-8")
    assert md.count("| onb-start") == 1 and "| ref-cafeteria" in md and "| gov-what" in md
    assert "citation_precision" in md and "**PASS**" in md and "2026-09-15" in md
    for text in (md, json_path.read_text(encoding="utf-8")):
        assert "Healthy page" not in text  # a page body never lands in a report


async def test_budget_stop_marks_the_rest_skipped(kb_root: Path):
    items = load_golden(write_golden(kb_root), kb_root)
    dear = reads("onboarding/README.md", GOOD_ANSWER, total_cost_usd=0.4)
    run = await run_eval(_settings(), kb_root, items, budget_usd=0.5, query_fn=dear, today=TODAY)
    assert [r.status for r in run.results] == ["scored", "skipped", "skipped"]
    assert run.summary.skipped == 2 and run.summary.total_cost_usd == 0.4
    assert run.results[1].cost_usd is None and run.results[1].duration_ms == 0
    assert run.summary.items == 3 and json.loads(run.json_path.read_text())["summary"]["skipped"] == 2


async def test_errors_are_recorded_not_raised(kb_root: Path):
    items = load_golden(write_golden(kb_root), kb_root)
    router = Router(
        {
            "get started": FakeQuery(calls=[], result=_result(), raise_after=RuntimeError("cli exploded")),
            "cafetería": says("x", is_error=True, subtype="error_max_turns", total_cost_usd=0.05),
        },
        default=reads("governance/README.md", "Governance. Rules. More rules."),
    )
    lines: list[str] = []

    class Out:
        def write(self, text: str) -> None:
            lines.append(text)

    run = await run_eval(_settings(), kb_root, items, budget_usd=5.0, query_fn=router, out=Out(), today=TODAY)
    raised, errored, fine = run.results
    assert raised.status == "error" and raised.error == "RuntimeError" and raised.cost_usd is None
    assert errored.status == "error" and "error_max_turns" in errored.error and errored.cost_usd == 0.05
    assert fine.status == "scored" and run.summary.errors == 2 and run.summary.scored == 1
    progress = "".join(lines)
    assert "onb-start" in progress and "error" in progress and "Governance. Rules." not in progress


async def test_lang_filter_runs_only_that_language(kb_root: Path):
    items = load_golden(write_golden(kb_root), kb_root)
    router = scripted()
    run = await run_eval(_settings(), kb_root, items, budget_usd=5.0, lang="es", query_fn=router, today=TODAY)
    assert [r.id for r in run.results] == ["ref-cafeteria"] and run.lang == "es"
    assert json.loads(run.json_path.read_text())["lang"] == "es"
