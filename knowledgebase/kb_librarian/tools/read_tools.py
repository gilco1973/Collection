"""Read-only tools: safe in every mode."""

import asyncio
import sqlite3

from claude_agent_sdk import SdkMcpTool, tool
from mcp.types import ToolAnnotations

from kb_librarian.checks import run_all_checks
from kb_librarian.retrieval.embedder import EmbedError
from kb_librarian.tools.context import ToolContext, data_result, schema, text_result

MAX_BODY_CHARS = 20_000
SEMANTIC_DEFAULT, SEMANTIC_MAX = 8, 20
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False)


def build_read_tools(ctx: ToolContext) -> list[SdkMcpTool]:
    @tool(
        name="list_documents",
        description=(
            "List knowledge-base pages with their section, title, status and reviewed date. "
            "Optionally filter by section id."
        ),
        input_schema=schema(optional={"section": "string"}),
        annotations=READ_ONLY,
    )
    async def list_documents(args: dict) -> dict:
        section = str(args.get("section") or "").strip()
        docs = ctx.catalog.in_section(section) if section else ctx.catalog.documents
        rows = [
            {
                "path": d.rel_path,
                "section": d.section_id,
                "title": d.title,
                "status": d.meta.get("status"),
                "reviewed": str(d.meta.get("reviewed", "")),
                "owner": d.meta.get("owner"),
            }
            for d in docs
        ]
        return data_result(rows)

    @tool(
        name="get_document",
        description="Return the frontmatter and body of one page by its docs-relative path.",
        input_schema={"path": str},
        annotations=READ_ONLY,
    )
    async def get_document(args: dict) -> dict:
        doc = ctx.catalog.get(str(args.get("path", "")))
        if doc is None:
            return text_result(f"no page at '{args.get('path')}'", is_error=True)
        body = doc.body if len(doc.body) <= MAX_BODY_CHARS else doc.body[:MAX_BODY_CHARS] + "\n[truncated]"
        return data_result({"path": doc.rel_path, "meta": doc.meta, "body": body})

    @tool(
        name="search_documents",
        description="Case-insensitive full-text search across page titles and bodies.",
        input_schema={"query": str},
        annotations=READ_ONLY,
    )
    async def search_documents(args: dict) -> dict:
        hits = ctx.catalog.search(str(args.get("query", "")))
        return data_result([{"path": d.rel_path, "title": d.title} for d in hits])

    @tool(
        name="run_checks",
        description=(
            "Run the deterministic checks (structure, frontmatter, freshness, links, sensitive content) "
            "and return findings sorted by severity. Optionally restrict to one check name."
        ),
        input_schema=schema(optional={"check": "string"}),
        annotations=READ_ONLY,
    )
    async def run_checks(args: dict) -> dict:
        ctx.reload()
        wanted = str(args.get("check") or "").strip()
        findings = run_all_checks(ctx.catalog, ctx.config, today=ctx.today, offline=ctx.offline)
        if wanted:
            findings = [f for f in findings if f.check == wanted]
        return data_result([f.model_dump() for f in findings])

    @tool(
        name="get_contract",
        description="Return the knowledge-base contract: sections, owners, required frontmatter, taxonomy tags.",
        input_schema=schema(),
        annotations=READ_ONLY,
    )
    async def get_contract(args: dict) -> dict:
        return text_result(ctx.config.model_dump_json(indent=1))

    @tool(
        name="semantic_search",
        description=(
            "Meaning-based search over page sections: use it for open questions phrased unlike the pages "
            "(`search_documents` is for exact terms). Returns the best-matching section per page with its "
            "path, heading, a short excerpt and a score; read a page with `get_document` before citing it."
        ),
        input_schema=schema(required={"query": "string"}, optional={"limit": "integer"}),
        annotations=READ_ONLY,
    )
    async def semantic_search(args: dict) -> dict:
        if ctx.retriever is None:  # not registered in that case; a backstop, never a wider path
            return text_result("semantic search is not available: no embedding index", is_error=True)
        limit = max(1, min(int(args.get("limit") or SEMANTIC_DEFAULT), SEMANTIC_MAX))
        allowed = {d.rel_path for d in ctx.catalog.documents}  # the caller's view, withheld pages already out
        try:  # an HTTP embed must not block the loop the API's chat turn runs on
            hits = await asyncio.to_thread(ctx.retriever.search, str(args.get("query", "")), limit, allowed)
        except (EmbedError, sqlite3.Error) as exc:
            detail = str(exc) if isinstance(exc, EmbedError) else type(exc).__name__
            return text_result(f"semantic search failed: {detail}", is_error=True)
        rows = [{"path": h.path, "heading": h.heading, "excerpt": h.excerpt, "score": round(h.score, 3)} for h in hits]
        return data_result(rows)

    tools = [list_documents, get_document, search_documents, run_checks, get_contract]
    return tools + [semantic_search] if ctx.retriever is not None else tools
