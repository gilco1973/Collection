"""Run reports: the JSON dump and the Markdown summary under ``.librarian/evals/<date>.{json,md}``.

Both carry the golden items' questions and the model's answers (authored content, never a
reader's) and the pages cited by path — never a page body.
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from kb_librarian.evals.runner import EvalRun

EVALS_DIR = Path(".librarian") / "evals"
QUESTION_CHARS = 70


def run_to_dict(run: "EvalRun") -> dict:
    return {
        "date": run.date,
        "generated_at": run.generated_at,
        "model": run.model,
        "effort": run.effort,
        "golden_path": run.golden_path,
        "golden_sha256": run.golden_sha256,
        "lang": run.lang,
        "budget_usd": run.budget_usd,
        "items_run": run.summary.items,
        "results": [r.to_dict() for r in run.results],
        "summary": run.summary.to_dict(),
    }


def _cell(text: str) -> str:
    text = " ".join(text.split())
    if len(text) > QUESTION_CHARS:
        text = text[: QUESTION_CHARS - 1] + "…"
    return text.replace("|", "\\|")


def _rate(value: float) -> str:
    return f"{value:.2f}"


def _cost(value: float | None) -> str:
    return "-" if value is None else f"{value:.4f}"


def render_markdown(run: "EvalRun") -> str:
    summary = run.summary
    lines = [
        f"# Librarian evaluation — {run.date}",
        "",
        f"Model `{run.model}` (effort `{run.effort}`), golden `{run.golden_path}` (sha256 `{run.golden_sha256[:12]}`),"
        f" language filter `{run.lang or '-'}`, budget {run.budget_usd:.2f} USD.",
        "",
        f"**{'PASS' if summary.passed else 'FAIL'}** — {summary.scored} scored, {summary.errors} errors,"
        f" {summary.skipped} skipped of {summary.items}; total cost {summary.total_cost_usd:.4f} USD;"
        f" average {summary.avg_duration_ms} ms per item.",
        "",
        "| Threshold | Value | Required | Result |",
        "| --- | --- | --- | --- |",
    ]
    for check in summary.checks:
        rule = "≤" if check.name == "max_cost_usd_per_run" else "≥"
        verdict = "PASS" if check.passed else "FAIL"
        lines.append(f"| {check.name} | {check.value} | {rule} {check.threshold} | {verdict} |")
    lines += [
        "",
        "| Item | Lang | Persona | Status | Precision | Recall | Keywords | Refusal | Cost USD | ms | Question |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in run.results:
        lines.append(
            f"| {r.id} | {r.lang} | {r.persona} | {r.status} | {_rate(r.citation_precision)} |"
            f" {_rate(r.citation_recall)} | {'ok' if r.keywords_ok else 'miss'} | {'ok' if r.refusal_ok else 'miss'} |"
            f" {_cost(r.cost_usd)} | {r.duration_ms} | {_cell(r.question)} |"
        )
    errors = [r for r in run.results if r.error]
    if errors:
        lines += ["", "## Errors", ""] + [f"- `{r.id}`: {r.error}" for r in errors]
    return "\n".join(lines) + "\n"


def write_reports(run: "EvalRun", root: Path) -> tuple[Path, Path]:
    """Write ``<root>/.librarian/evals/<date>.json`` and ``.md``; a later run the same day overwrites."""
    directory = root / EVALS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    json_path, md_path = directory / f"{run.date}.json", directory / f"{run.date}.md"
    json_path.write_text(json.dumps(run_to_dict(run), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(run), encoding="utf-8")
    return json_path, md_path
