"""Scoring one item and summarising a run. Pure functions: no model, no filesystem."""

from dataclasses import asdict, dataclass, field

from kb_librarian.chat.runner import ChatAnswer
from kb_librarian.evals.items import EvalItem
from kb_librarian.evals.refusals import is_refusal
from kb_librarian.kbconfig import EvalThresholds

STATUSES = ("scored", "error", "skipped")


@dataclass
class ItemResult:
    id: str
    lang: str
    persona: str
    question: str
    expected_paths: list[str]
    refuse_expected: bool
    status: str = "scored"
    answer: str = ""
    sources: list[str] = field(default_factory=list)
    refused: bool = False
    citation_precision: float = 0.0
    citation_recall: float = 0.0
    keywords_ok: bool = False
    refusal_ok: bool = False
    cost_usd: float | None = None
    duration_ms: int = 0
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Check:
    name: str
    value: float
    threshold: float
    passed: bool


@dataclass
class Summary:
    items: int
    scored: int
    errors: int
    skipped: int
    citation_precision: float
    citation_recall: float
    refusal_correctness: float
    keywords_rate: float
    total_cost_usd: float
    avg_duration_ms: int
    checks: list[Check]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["passed"] = self.passed
        return data


def _base(item: EvalItem) -> ItemResult:
    return ItemResult(
        id=item.id,
        lang=item.lang,
        persona=item.persona,
        question=item.question,
        expected_paths=list(item.expect.paths),
        refuse_expected=item.expect.refuse,
    )


def skipped_item(item: EvalItem) -> ItemResult:
    """An item the run did not reach (budget exhausted)."""
    result = _base(item)
    result.status = "skipped"
    return result


def citation_scores(cited: list[str], expected: list[str]) -> tuple[float, float]:
    """(precision, recall) of ``cited`` against ``expected``; both 1.0 when nothing was expected and
    nothing cited, and recall 1.0 whenever nothing was expected."""
    hits = len(set(cited) & set(expected))
    precision = hits / len(cited) if cited else (1.0 if not expected else 0.0)
    recall = hits / len(expected) if expected else 1.0
    return precision, recall


def keywords_ok(answer: str, must_contain: list[str], must_not_contain: list[str]) -> bool:
    lowered = answer.casefold()
    return all(k.casefold() in lowered for k in must_contain) and not any(
        k.casefold() in lowered for k in must_not_contain
    )


def score_item(item: EvalItem, answer: ChatAnswer, duration_ms: int) -> ItemResult:
    """Score one chat answer. An errored turn scores zero on every measure but keeps what it cost."""
    result = _base(item)
    result.duration_ms = duration_ms
    result.cost_usd = answer.cost_usd
    if answer.error:
        result.status, result.error = "error", answer.error
        return result
    result.answer = answer.answer
    result.sources = [s["path"] for s in answer.sources]
    result.citation_precision, result.citation_recall = citation_scores(result.sources, result.expected_paths)
    result.keywords_ok = keywords_ok(answer.answer, item.expect.must_contain, item.expect.must_not_contain)
    result.refused = is_refusal(answer.answer, item.lang, sources=len(result.sources))
    result.refusal_ok = item.expect.refuse == result.refused
    return result


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def summarise(results: list[ItemResult], thresholds: EvalThresholds) -> Summary:
    """Averages over every item the run reached (errors count as zeros; skipped items do not count)."""
    reached = [r for r in results if r.status != "skipped"]
    costs = [r.cost_usd for r in results if r.cost_usd is not None]
    precision = _mean([r.citation_precision for r in reached])
    recall = _mean([r.citation_recall for r in reached])
    refusal = _mean([float(r.refusal_ok) for r in reached])
    total_cost = round(sum(costs), 6)
    t = thresholds
    checks = [
        Check("citation_precision", precision, t.citation_precision, precision >= t.citation_precision),
        Check("citation_recall", recall, t.citation_recall, recall >= t.citation_recall),
        Check("refusal_correctness", refusal, t.refusal_correctness, refusal >= t.refusal_correctness),
        Check("max_cost_usd_per_run", total_cost, t.max_cost_usd_per_run, total_cost <= t.max_cost_usd_per_run),
    ]
    return Summary(
        items=len(results),
        scored=sum(1 for r in reached if r.status == "scored"),
        errors=sum(1 for r in reached if r.status == "error"),
        skipped=len(results) - len(reached),
        citation_precision=precision,
        citation_recall=recall,
        refusal_correctness=refusal,
        keywords_rate=_mean([float(r.keywords_ok) for r in reached]),
        total_cost_usd=total_cost,
        avg_duration_ms=round(_mean([float(r.duration_ms) for r in reached])),
        checks=checks,
    )
