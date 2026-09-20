"""Atlassian tools for the agent. Writes go through the same gate as the clients."""

from claude_agent_sdk import SdkMcpTool, tool
from mcp.types import ToolAnnotations

from kb_librarian.atlassian.client import AtlassianWriteRefused
from kb_librarian.atlassian.confluence import ConfluenceClient
from kb_librarian.atlassian.jira import JiraClient
from kb_librarian.atlassian.markdown import markdown_to_storage
from kb_librarian.atlassian.sync import page_title
from kb_librarian.tools.context import ToolContext, data_result, text_result

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False)
MUTATING = ToolAnnotations(readOnlyHint=False, destructiveHint=False)
_MAX_TEXT = 2000


def cql_text(query: str) -> str:
    return query.replace("\\", " ").replace('"', " ")[:200]


def build_atlassian_tools(ctx: ToolContext, confluence: ConfluenceClient, jira: JiraClient) -> list[SdkMcpTool]:
    space = ctx.config.atlassian.confluence_space_key
    project = ctx.config.atlassian.jira_project_key

    @tool(
        name="confluence_search",
        description=f"Search the Confluence space {space} with a plain-text query. Returns id, title and url per hit.",
        input_schema={"query": str},
        annotations=READ_ONLY,
    )
    async def confluence_search(args: dict) -> dict:
        cql = f'space = "{space}" and type = page and text ~ "{cql_text(str(args.get("query", "")))}"'
        return data_result(confluence.search(cql))

    @tool(
        name="confluence_get_page",
        description="Fetch one Confluence page (storage-format body) by id.",
        input_schema={"page_id": str},
        annotations=READ_ONLY,
    )
    async def confluence_get_page(args: dict) -> dict:
        return data_result(confluence.get_page(str(args.get("page_id", ""))))

    @tool(
        name="confluence_publish_page",
        description=(
            f"Mirror one knowledge-base page (by docs-relative path) into Confluence space {space}. "
            "Mutating; requires a reason."
        ),
        input_schema={"path": str, "reason": str},
        annotations=MUTATING,
    )
    async def confluence_publish_page(args: dict) -> dict:
        doc = ctx.catalog.get(str(args.get("path", "")))
        if doc is None:
            return text_result(f"no page at '{args.get('path')}'", is_error=True)
        title = page_title(doc, ctx.config)
        try:
            outcome = confluence.publish(space, title, markdown_to_storage(doc.body))
        except AtlassianWriteRefused as exc:
            return text_result(str(exc), is_error=True)
        ctx.record_external_action("confluence_publish_page", doc.rel_path, str(args.get("reason", "")))
        return data_result({"reason": args.get("reason", ""), **outcome})

    @tool(
        name="jira_create_issue",
        description=(
            f"Create a Jira issue in project {project} to track a finding for its owner. Mutating; requires a reason."
        ),
        input_schema={"summary": str, "description": str, "reason": str},
        annotations=MUTATING,
    )
    async def jira_create_issue(args: dict) -> dict:
        summary = str(args.get("summary", ""))[:200]
        description = str(args.get("description", ""))[:_MAX_TEXT]
        try:
            outcome = jira.create_issue(project, summary, description, labels=["kb-librarian"])
        except AtlassianWriteRefused as exc:
            return text_result(str(exc), is_error=True)
        ctx.record_external_action("jira_create_issue", str(outcome.get("key")), str(args.get("reason", "")))
        return data_result({"reason": args.get("reason", ""), **outcome})

    return [confluence_search, confluence_get_page, confluence_publish_page, jira_create_issue]
