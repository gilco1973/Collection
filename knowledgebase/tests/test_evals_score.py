"""kb_librarian/evals/score and refusals: the arithmetic and the refusal rule, offline."""

from kb_librarian.chat.runner import ChatAnswer
from kb_librarian.evals.items import EvalItem
from kb_librarian.evals.refusals import is_refusal
from kb_librarian.evals.score import score_item, skipped_item, summarise
from kb_librarian.kbconfig import EvalThresholds


def _item(paths=(), must=(), must_not=(), refuse=False, lang="en") -> EvalItem:
    return EvalItem.model_validate(
        {
            "id": "x",
            "question": "q?",
            "persona": "engineer",
            "lang": lang,
            "expect": {
                "paths": list(paths),
                "must_contain": list(must),
                "must_not_contain": list(must_not),
                "refuse": refuse,
            },
        }
    )


def _answer(text="The gateway is the single egress.", paths=(), cost=0.01, error=None) -> ChatAnswer:
    return ChatAnswer(answer=text, sources=[{"path": p, "title": p} for p in paths], cost_usd=cost, error=error)


def test_precision_and_recall_arithmetic():
    item = _item(paths=["a.md", "b.md"])
    result = score_item(item, _answer(paths=["a.md", "c.md"]), 120)
    assert result.citation_precision == 0.5 and result.citation_recall == 0.5
    assert result.duration_ms == 120 and result.cost_usd == 0.01 and result.status == "scored"
    full = score_item(item, _answer(paths=["a.md", "b.md"]), 1)
    assert full.citation_precision == 1.0 and full.citation_recall == 1.0
    nothing = score_item(item, _answer(paths=[]), 1)
    assert nothing.citation_precision == 0.0 and nothing.citation_recall == 0.0


def test_empty_expectations():
    empty = _item()
    result = score_item(empty, _answer("Nothing here.", paths=[]), 1)
    assert result.citation_precision == 1.0 and result.citation_recall == 1.0
    cited = score_item(empty, _answer(paths=["a.md"]), 1)
    assert cited.citation_precision == 0.0 and cited.citation_recall == 1.0


def test_keyword_checks_are_case_insensitive():
    item = _item(paths=["a.md"], must=["GATEWAY", "egress"], must_not=["vendor key"])
    assert score_item(item, _answer("The Gateway is the single egress.", paths=["a.md"]), 1).keywords_ok
    assert not score_item(item, _answer("The Gateway is here.", paths=["a.md"]), 1).keywords_ok
    assert not score_item(item, _answer("The gateway egress uses a Vendor Key.", paths=["a.md"]), 1).keywords_ok


def test_refusal_detection_per_language():
    assert is_refusal("That topic is not in the knowledge base.", "en")
    assert is_refusal("Sorry, no page covers payroll here. Ask HR instead, please. It is their topic.", "en")
    assert is_refusal("Ese tema no está en la base de conocimiento.", "es")
    assert is_refusal("Lo siento, ninguna página cubre eso.", "es")
    assert is_refusal("הנושא הזה לא נמצא במאגר הידע.", "he")
    assert is_refusal("לא מצאתי דף שעונה על השאלה.", "he")
    assert is_refusal("I could not find that.", "es")  # English phrases count in every language
    long_answer = "One. Two. Three sentences of real content about the gateway and its logs and its keys."
    assert not is_refusal(long_answer, "en")
    assert is_refusal("Short. Answer.", "en")  # no sources and at most two sentences
    assert not is_refusal("It is not in the knowledge base.", "en", sources=1)  # a cited answer is never a refusal


def test_refusal_ok_compares_expectation_with_detection():
    refused = _answer("That is not in the knowledge base.", paths=[])
    assert score_item(_item(refuse=True), refused, 1).refusal_ok
    assert not score_item(_item(paths=["a.md"], must=["x"]), refused, 1).refusal_ok
    answered = _answer("The gateway is the single egress. Keys are rotated centrally. Budgets apply.", paths=["a.md"])
    assert score_item(_item(paths=["a.md"]), answered, 1).refusal_ok
    assert not score_item(_item(refuse=True), answered, 1).refusal_ok


def test_an_error_scores_zero_and_keeps_the_cost():
    failed = ChatAnswer(error="agent result error: boom", cost_usd=0.2)
    result = score_item(_item(paths=["a.md"], must=["x"]), failed, 5)
    assert result.status == "error" and result.error == "agent result error: boom" and result.cost_usd == 0.2
    assert result.citation_precision == 0.0 and result.citation_recall == 0.0
    assert not result.keywords_ok and not result.refusal_ok and result.answer == ""
    assert skipped_item(_item()).status == "skipped" and skipped_item(_item()).cost_usd is None


def test_summary_averages_and_thresholds():
    thresholds = EvalThresholds(citation_precision=0.8, citation_recall=0.7, max_cost_usd_per_run=1.0)
    good = score_item(_item(paths=["a.md"], must=["egress"]), _answer(paths=["a.md"], cost=0.3), 10)
    half = score_item(_item(paths=["a.md", "b.md"]), _answer(paths=["a.md"], cost=0.3), 30)
    summary = summarise([good, half, skipped_item(_item())], thresholds)
    assert summary.items == 3 and summary.scored == 2 and summary.skipped == 1 and summary.errors == 0
    assert summary.citation_precision == 1.0 and summary.citation_recall == 0.75
    assert summary.refusal_correctness == 1.0 and summary.keywords_rate == 1.0
    assert summary.total_cost_usd == 0.6 and summary.avg_duration_ms == 20
    assert summary.passed and {c.name: c.passed for c in summary.checks} == {
        "citation_precision": True,
        "citation_recall": True,
        "refusal_correctness": True,
        "max_cost_usd_per_run": True,
    }
    missed = summarise([good, half], EvalThresholds(citation_recall=0.9))
    assert not missed.passed and [c.name for c in missed.checks if not c.passed] == ["citation_recall"]
    dear = summarise([good, half], EvalThresholds(max_cost_usd_per_run=0.5))
    assert not dear.passed and [c.name for c in dear.checks if not c.passed] == ["max_cost_usd_per_run"]


def test_summary_of_nothing_scored_fails_every_rate():
    summary = summarise([skipped_item(_item())], EvalThresholds())
    assert summary.scored == 0 and summary.citation_precision == 0.0 and not summary.passed
