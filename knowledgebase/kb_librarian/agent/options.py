"""Build ``ClaudeAgentOptions`` for one librarian audit."""

from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, HookMatcher, McpSdkServerConfig

from kb_librarian.agent.gate import GateFn
from kb_librarian.agent.prompts import SYSTEM_PROMPT
from kb_librarian.config import LibrarianSettings
from kb_librarian.tools.server import KB_SERVER_NAME

# ``tools=[]`` removes every built-in Claude Code tool (file, shell, web, tool
# search, ...). This deny-list is a second layer naming the ones that matter most,
# so a future SDK default cannot quietly hand them back.
DISALLOWED_BUILTINS: tuple[str, ...] = (
    "Bash", "Write", "Edit", "MultiEdit", "NotebookEdit", "NotebookRead", "Read", "Glob", "Grep", "LS",
    "WebFetch", "WebSearch", "Task", "Agent", "TodoWrite", "KillShell", "BashOutput",
    "ToolSearch", "Skill", "SlashCommand", "AskUserQuestion", "ListMcpResourcesTool",
    "ReadMcpResourceTool", "ExitPlanMode", "EnterPlanMode",
)  # fmt: skip


def build_options(
    settings: LibrarianSettings,
    server: McpSdkServerConfig,
    *,
    cwd: Path,
    can_use_tool: GateFn,
    hooks: dict[str, list[HookMatcher]],
    max_turns: int | None = None,
    max_budget_usd: float | None = None,
) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={KB_SERVER_NAME: server},
        # No built-ins at all; the kb MCP tools are the whole tool surface.
        tools=[],
        # Never pre-approve: an allowed_tools entry auto-approves a whole tool
        # before can_use_tool is consulted. Every call must reach the gate.
        allowed_tools=[],
        disallowed_tools=list(DISALLOWED_BUILTINS),
        permission_mode="default",
        can_use_tool=can_use_tool,
        hooks=hooks,
        max_turns=settings.max_turns if max_turns is None else max_turns,
        max_budget_usd=settings.max_budget_usd if max_budget_usd is None else max_budget_usd,
        model=settings.model,
        effort=settings.effort,
        cwd=str(cwd),
        # Isolate from any user/project Claude Code settings on the host: the
        # librarian sees only what this file gives it.
        setting_sources=[],
        strict_mcp_config=True,
    )
