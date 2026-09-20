"""Assemble the in-process MCP server the librarian agent talks to."""

from claude_agent_sdk import McpSdkServerConfig, SdkMcpTool, create_sdk_mcp_server

from kb_librarian.tools.context import ToolContext
from kb_librarian.tools.read_tools import build_read_tools
from kb_librarian.tools.write_tools import build_write_tools

KB_SERVER_NAME = "kb"

# Documentation of the tools that change the knowledge base or an external system.
# The gate does not trust this list: it derives the mutating set from each tool's
# MCP annotations (``readOnlyHint=False``), and a test keeps the two in step.
MUTATING_TOOLS: frozenset[str] = frozenset(
    {
        "set_frontmatter_field",
        "add_frontmatter",
        "regenerate_index",
        "rollback_action",
        "confluence_publish_page",
        "jira_create_issue",
    }
)


def qualified(name: str) -> str:
    """The name the SDK uses for an in-process MCP tool."""
    return f"mcp__{KB_SERVER_NAME}__{name}"


def unqualify(tool_name: str) -> str:
    prefix = f"mcp__{KB_SERVER_NAME}__"
    return tool_name[len(prefix) :] if tool_name.startswith(prefix) else tool_name


def mutating_names(tools: list[SdkMcpTool]) -> set[str]:
    """Unqualified names of tools whose annotations say they are not read-only."""
    missing = [t.name for t in tools if t.annotations is None]
    if missing:
        raise ValueError(f"tools without annotations: {missing}")
    return {t.name for t in tools if not t.annotations.read_only_hint}


def build_kb_tools(ctx: ToolContext, extra: list[SdkMcpTool] | None = None) -> list[SdkMcpTool]:
    return [*build_read_tools(ctx), *build_write_tools(ctx), *(extra or [])]


def build_kb_server(tools: list[SdkMcpTool]) -> McpSdkServerConfig:
    return create_sdk_mcp_server(name=KB_SERVER_NAME, version="1.0.0", tools=tools)
