"""Run golden items through the real chat path (``run_chat``: gate, hooks, read tools) and score them.

Sequential, on purpose: the budget check between items is only meaningful when one turn's cost is
known before the next starts. The run stops when the next item *would* push the cumulative cost
past the budget — the estimate for the next item is the dearest turn seen so far — and every item
not reached is recorded as ``skipped``. An erroring item is recorded, never raised.
"""

import hashlib
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from claude_agent_sdk import query as sdk_query

from kb_librarian.chat.runner import ChatAnswer, QueryFn, run_chat
from kb_librarian.config import LibrarianSettings
from kb_librarian.evals.items import DEFAULT_GOLDEN, EvalItem
from kb_librarian.evals.report import write_reports
from kb_librarian.evals.score import ItemResult, Summary, score_item, skipped_item, summarise
from kb_librarian.kbconfig import load_kb_config


@dataclass
class EvalRun:
    date: str
    generated_at: str
    model: str
    effort: str
    golden_path: str
    golden_sha256: str
    lang: str | None
    budget_usd: float
    results: list[ItemResult] = field(default_factory=list)
    summary: Summary | None = None
    json_path: Path | None = None
    md_path: Path | None = None


def golden_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def _progress(out, result: ItemResult) -> None:
    if out is not None:  # one line per item: never the answer
        cost = "-" if result.cost_usd is None else f"{result.cost_usd:.4f}"
        print(
            f"{result.id:32} {result.status:7} p={result.citation_precision:.2f} r={result.citation_recall:.2f}"
            f" kw={'ok' if result.keywords_ok else 'miss'} ref={'ok' if result.refusal_ok else 'miss'}"
            f" cost={cost} {result.duration_ms}ms",
            file=out,
        )


async def _turn(settings: LibrarianSettings, root: Path, item: EvalItem, query_fn: QueryFn) -> ChatAnswer:
    lang = None if item.lang == "en" else item.lang
    try:
        return await run_chat(settings, root, item.question, [], lang=lang, query_fn=query_fn)
    except Exception as exc:  # noqa: BLE001 — recorded by type only; a message may carry a path
        return ChatAnswer(error=type(exc).__name__)


async def run_eval(
    settings: LibrarianSettings,
    root: Path,
    items: list[EvalItem],
    *,
    budget_usd: float,
    lang: str | None = None,
    query_fn: QueryFn = sdk_query,
    out=None,
    golden_path: Path | None = None,
    today: date | None = None,
) -> EvalRun:
    """Run ``items`` (those in ``lang`` when given) and write the JSON and Markdown reports."""
    golden = golden_path or root / DEFAULT_GOLDEN
    thresholds = load_kb_config(root / "kb.config.yaml").evals
    chosen = [i for i in items if lang is None or i.lang == lang]
    now = datetime.now(UTC)
    run = EvalRun(
        date=(today or now.date()).isoformat(),
        generated_at=now.isoformat(timespec="seconds"),
        model=settings.model,
        effort=str(settings.effort),
        golden_path=golden.name if golden.is_absolute() else golden.as_posix(),
        golden_sha256=golden_digest(golden),
        lang=lang,
        budget_usd=budget_usd,
    )
    spent, dearest = 0.0, 0.0
    for index, item in enumerate(chosen):
        if spent >= budget_usd or spent + dearest > budget_usd:
            run.results.extend(skipped_item(rest) for rest in chosen[index:])
            break
        started = time.monotonic()
        answer = await _turn(settings, root, item, query_fn)
        result = score_item(item, answer, round((time.monotonic() - started) * 1000))
        if result.cost_usd is not None:
            spent += result.cost_usd
            dearest = max(dearest, result.cost_usd)
        run.results.append(result)
        _progress(out, result)
    run.summary = summarise(run.results, thresholds)
    run.json_path, run.md_path = write_reports(run, root)
    return run
