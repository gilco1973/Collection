"""Fake Claude Agent SDK query stream for end-to-end runner tests (no network, no CLI).

The fake mirrors the SDK's dispatch order: PreToolUse hooks → permission callback →
tool execution through the SDK's real in-process MCP server → PostToolUse hook.
Denied calls never execute and never reach PostToolUse, exactly as in production.
"""

from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock
from mcp import types

from kb_librarian.config import LibrarianSettings
from kb_librarian.tools.server import qualified


def _settings(**kw) -> LibrarianSettings:
    return LibrarianSettings(max_turns=5, max_budget_usd=0.25, **kw)


def _result(**overrides) -> ResultMessage:
    base = dict(
        subtype="success",
        duration_ms=10,
        duration_api_ms=5,
        is_error=False,
        num_turns=3,
        session_id="s",
        stop_reason="end_turn",
        total_cost_usd=0.0123,
        usage={},
        result="Done: flagged the stale page.",
    )
    base.update(overrides)
    return ResultMessage(**base)


async def _call_via_mcp(options, name: str, arguments: dict) -> dict:
    """Invoke a tool through the in-process MCP server the SDK built (schema validation included)."""
    server = options.mcp_servers["kb"]["instance"]
    entry = server.get_request_handler("tools/call")
    result = await entry.handler(None, types.CallToolRequestParams(name=name, arguments=arguments))
    return {"content": [block.model_dump() for block in result.content], "is_error": bool(result.is_error)}


class FakeQuery:
    def __init__(self, calls, result: ResultMessage, raise_after: Exception | None = None):
        self.calls, self.result, self.raise_after = calls, result, raise_after
        self.captured_options = None
        self.prompt = None
        self.tool_results: list[dict] = []
        self.denied: list[str] = []

    async def _hooks(self, options, event, payload):
        outputs = []
        for matcher in options.hooks.get(event, []):
            for hook in matcher.hooks:
                out = await hook(payload, "id", None)
                if out:
                    outputs.append(out)
        return outputs

    async def __call__(self, *, prompt: str, options):
        self.prompt, self.captured_options = prompt, options
        yield AssistantMessage(content=[TextBlock(text="Starting audit.")], model="fake")
        for name, tool_input in self.calls:
            full = qualified(name)
            yield AssistantMessage(content=[ToolUseBlock(id="t", name=full, input=tool_input)], model="fake")
            pre = await self._hooks(options, "PreToolUse", {"tool_name": full, "tool_input": tool_input})
            if any(o["hookSpecificOutput"]["permissionDecision"] == "deny" for o in pre):
                self.denied.append(name)
                continue
            verdict = await options.can_use_tool(full, tool_input, None)
            if verdict.behavior != "allow":
                self.denied.append(name)
                continue
            response = await _call_via_mcp(options, name, tool_input)
            self.tool_results.append(response)
            await self._hooks(
                options,
                "PostToolUse",
                {
                    "tool_name": full,
                    "tool_input": tool_input,
                    "tool_response": response["content"] if not response["is_error"] else response,
                },
            )
        if self.raise_after:
            raise self.raise_after
        yield self.result
