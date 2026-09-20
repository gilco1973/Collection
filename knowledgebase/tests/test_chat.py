"""kb_librarian/chat: a read-only, tool-using Q&A turn grounded in the knowledge base."""

from pathlib import Path

from claude_agent_sdk import ResultError

from kb_librarian.chat.prompts import ChatTurn, build_chat_prompt
from kb_librarian.chat.runner import run_chat
from tests.fake_query import FakeQuery, _result, _settings


def test_build_chat_prompt_without_history():
    assert build_chat_prompt([], "what is the AI policy?") == (
        "Answer this question using the knowledge base:\n\nwhat is the AI policy?"
    )


def test_build_chat_prompt_includes_recent_turns():
    history = [ChatTurn(role="user", content="hi"), ChatTurn(role="assistant", content="hello")]
    prompt = build_chat_prompt(history, "and now?")
    assert "User: hi" in prompt and "Librarian: hello" in prompt and "User: and now?" in prompt


async def test_run_chat_answers_and_reports_read_pages_as_sources(kb_root: Path):
    fake = FakeQuery(
        calls=[("search_documents", {"query": "onboarding"}), ("get_document", {"path": "onboarding/README.md"})],
        result=_result(result="Day one starts with the AI policy."),
    )
    answer = await run_chat(_settings(), kb_root, "how do I get started?", [], query_fn=fake)
    assert answer.answer == "Day one starts with the AI policy." and answer.error is None
    assert answer.sources == [{"path": "onboarding/README.md", "title": "Onboarding"}]


async def test_run_chat_never_offers_a_write_tool(kb_root: Path):
    fake = FakeQuery(
        calls=[
            (
                "set_frontmatter_field",
                {"path": "onboarding/README.md", "field": "status", "value": "draft", "reason": "x"},
            )
        ],
        result=_result(),
    )
    await run_chat(_settings(), kb_root, "anything", [], query_fn=fake)
    assert fake.denied == ["set_frontmatter_field"]  # never registered as a chat tool at all


async def test_run_chat_cannot_read_a_page_the_api_withholds(kb_root: Path):
    # onboarding/stale.md carries a critical sensitive hit, so readers never see its body; neither may the model.
    fake = FakeQuery(
        calls=[("search_documents", {"query": "fake key"}), ("get_document", {"path": "onboarding/stale.md"})],
        result=_result(result="I could not find that."),
    )
    answer = await run_chat(_settings(), kb_root, "what is the fake key?", [], query_fn=fake)
    assert fake.denied == []  # the tools ran; the page simply is not in the chat's catalog
    assert "stale.md" not in str(fake.tool_results[0]) and fake.tool_results[1]["is_error"]
    assert answer.sources == []


async def test_run_chat_keeps_withheld_pages_out_after_a_tool_reloads_the_catalog(kb_root: Path):
    # run_checks reloads the catalog from disk; the reload must re-apply the chat's readable-only view.
    calls = [
        ("run_checks", {}),
        ("list_documents", {}),
        ("search_documents", {"query": "fake key"}),
        ("get_document", {"path": "onboarding/stale.md"}),
    ]
    fake = FakeQuery(calls=calls, result=_result(result="Nothing."))
    await run_chat(_settings(), kb_root, "anything", [], query_fn=fake, lang="es")
    listed, searched, fetched = fake.tool_results[1:]
    assert "stale.md" not in str(listed) and "stale.md" not in str(searched) and fetched["is_error"]


async def test_run_chat_reports_an_error_result(kb_root: Path):
    fake = FakeQuery(calls=[], result=_result(is_error=True, subtype="error_max_turns"))
    answer = await run_chat(_settings(), kb_root, "anything", [], query_fn=fake)
    assert answer.error and "error_max_turns" in answer.error


async def test_run_chat_carries_the_turn_cost_from_the_result_message(kb_root: Path):
    fake = FakeQuery(calls=[], result=_result(result="Hi.", total_cost_usd=0.0421))
    assert (await run_chat(_settings(), kb_root, "hi", [], query_fn=fake)).cost_usd == 0.0421
    fake = FakeQuery(calls=[], result=_result(result="Hi.", total_cost_usd=None))
    assert (await run_chat(_settings(), kb_root, "hi", [], query_fn=fake)).cost_usd is None
    fake = FakeQuery(calls=[], result=_result(is_error=True, subtype="error_max_turns", total_cost_usd=0.5))
    answer = await run_chat(_settings(), kb_root, "hi", [], query_fn=fake)
    assert answer.error and answer.cost_usd == 0.5  # a billed turn counts even when it failed
    fake = FakeQuery(calls=[], result=_result(result="Hi.", total_cost_usd=-1.0))
    assert (await run_chat(_settings(), kb_root, "hi", [], query_fn=fake)).cost_usd is None  # never a negative


async def test_run_chat_reports_a_result_error_raised_by_the_sdk(kb_root: Path):
    fake = FakeQuery(calls=[], result=_result(), raise_after=ResultError("stream dropped"))
    answer = await run_chat(_settings(), kb_root, "anything", [], query_fn=fake)
    assert answer.error and "stream dropped" in answer.error


async def test_run_chat_reports_no_answer_when_the_model_says_nothing(kb_root: Path):
    class EmptyQuery:
        async def __call__(self, *, prompt, options):
            yield _result(result="")

    answer = await run_chat(_settings(), kb_root, "anything", [], query_fn=EmptyQuery())
    assert answer.error == "the librarian returned no answer"


async def test_run_chat_localizes_the_catalog_when_a_language_is_configured(kb_root: Path, kb_config):
    target = kb_root / "docs/i18n/es/onboarding/README.md"
    target.parent.mkdir(parents=True)
    target.write_text(
        "---\ntitle: Incorporación\nowner: enablement\nstatus: active\nreviewed: 2026-09-01\n"
        "tags: [onboarding]\naudience: [new-hire]\n---\n# Incorporación\n\nContenido en español.\n",
        encoding="utf-8",
    )
    fake = FakeQuery(calls=[("get_document", {"path": "onboarding/README.md"})], result=_result(result="Listo."))
    answer = await run_chat(_settings(), kb_root, "hola", [], lang="es", query_fn=fake)
    assert answer.sources == [{"path": "onboarding/README.md", "title": "Incorporación"}]


async def test_run_chat_ignores_an_unconfigured_language(kb_root: Path):
    fake = FakeQuery(calls=[("get_document", {"path": "onboarding/README.md"})], result=_result(result="Hi."))
    answer = await run_chat(_settings(), kb_root, "hi", [], lang="../../etc", query_fn=fake)
    assert answer.sources == [{"path": "onboarding/README.md", "title": "Onboarding"}]
