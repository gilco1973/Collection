"""The librarian's ``semantic_search`` tool through ``run_chat`` (FakeQuery, hash embedder; no network, no LLM)."""

from pathlib import Path

from kb_librarian.chat.prompts import CHAT_SYSTEM_PROMPT
from kb_librarian.chat.runner import run_chat
from kb_librarian.models import AuditReport
from kb_librarian.retrieval.build import build_index, index_path
from kb_librarian.retrieval.embedder import EmbedError, HashEmbedder
from kb_librarian.retrieval.index import VectorIndex
from kb_librarian.retrieval.retriever import Retriever
from kb_librarian.tools.context import ToolContext
from kb_librarian.tools.read_tools import build_read_tools
from tests.fake_query import FakeQuery, _result, _settings
from tests.helpers import payload


class FailingEmbedder(HashEmbedder):
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise EmbedError("embedding endpoint returned 503")


def test_the_system_prompt_tells_the_model_when_to_use_which_search():
    assert "`semantic_search` first for open questions" in CHAT_SYSTEM_PROMPT
    assert "`search_documents` for exact terms" in CHAT_SYSTEM_PROMPT
    assert "read with `get_document` before citing" in CHAT_SYSTEM_PROMPT


async def test_semantic_search_is_not_offered_without_an_index(kb_root: Path):
    fake = FakeQuery(calls=[("semantic_search", {"query": "onboarding"})], result=_result(result="Nothing."))
    await run_chat(_settings(), kb_root, "how do I start?", [], query_fn=fake)
    assert fake.denied == ["semantic_search"] and fake.tool_results == []  # never registered as a tool at all


async def test_semantic_search_excludes_withheld_and_out_of_view_pages_and_sources_still_come_from_reads(
    kb_root: Path, kb_config
):
    build_index(kb_root, kb_config, HashEmbedder())
    (kb_root / "docs/governance/README.md").unlink()  # indexed, but no longer in the catalog: never a hit
    calls = [
        ("semantic_search", {"query": "fake key flagged"}),  # only the withheld page says that
        ("semantic_search", {"query": "no frontmatter at all"}),  # only the deleted page said that
        ("semantic_search", {"query": "healthy page links to governance", "limit": 1}),
        ("get_document", {"path": "onboarding/README.md"}),
    ]
    fake = FakeQuery(calls=calls, result=_result(result="Start with the onboarding page."))
    answer = await run_chat(_settings(), kb_root, "where do I start?", [], query_fn=fake)
    assert fake.denied == []
    withheld, gone, found, _ = fake.tool_results
    assert payload(withheld) == [] and "stale.md" not in str(withheld)
    assert payload(gone) == [] and "governance" not in str(gone)
    rows = payload(found)
    assert [r["path"] for r in rows] == ["onboarding/README.md"] and rows[0]["heading"] == "Onboarding"
    assert set(rows[0]) == {"path", "heading", "excerpt", "score"} and rows[0]["excerpt"].startswith("# Onboarding")
    assert 0 < rows[0]["score"] <= 1 and rows[0]["score"] == round(rows[0]["score"], 3)
    assert answer.sources == [{"path": "onboarding/README.md", "title": "Onboarding"}]  # the page read, not the hits


async def test_semantic_search_survives_an_embedder_failure_and_needs_a_retriever(kb_root: Path, kb_config, catalog):
    build_index(kb_root, kb_config, HashEmbedder())
    report = AuditReport(audit_type="offline", dry_run=True)
    without = ToolContext(root=kb_root, config=kb_config, catalog=catalog, report=report)
    assert "semantic_search" not in {t.name for t in build_read_tools(without)}
    failing = Retriever(VectorIndex(index_path(kb_root)), FailingEmbedder())
    ctx = ToolContext(root=kb_root, config=kb_config, catalog=catalog, report=report, retriever=failing)
    tools = {t.name: t.handler for t in build_read_tools(ctx)}
    result = await tools["semantic_search"]({"query": "anything"})
    assert result.get("is_error") is True and "503" in result["content"][0]["text"]
    ctx.retriever = Retriever(VectorIndex(index_path(kb_root)), HashEmbedder())
    assert payload(await tools["semantic_search"]({"query": "   "})) == []
    many = payload(await tools["semantic_search"]({"query": "onboarding governance index page", "limit": 99}))
    assert 1 <= len(many) <= 20 and all(r["path"] in {d.rel_path for d in catalog.documents} for r in many)
