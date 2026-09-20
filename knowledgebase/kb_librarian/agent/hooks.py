"""SDK hooks: an audit trail of every tool call, and a cancel check before each one."""

from collections.abc import Callable
from typing import Any

from claude_agent_sdk import HookContext, HookMatcher

from kb_librarian.agent.task_manager import AuditTaskManager
from kb_librarian.models import AuditReport, ToolCall
from kb_librarian.tools.server import unqualify

_SUMMARY_CHARS = 300


def response_summary(response: Any) -> tuple[bool, str]:
    """Normalise the SDK's ``tool_response`` (a dict, a list of content blocks, or text)."""
    ok = True
    if isinstance(response, dict):
        ok = not (response.get("is_error") or response.get("isError"))
        content = response.get("content", response)
    else:
        content = response
    if isinstance(content, list):
        parts = [str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in content]
        text = " ".join(p for p in parts if p)
    elif isinstance(content, dict):
        text = str(content.get("text") or content)
    else:
        text = str(content or "")
    return ok, text


def build_hooks(
    report: AuditReport,
    manager: AuditTaskManager,
    gate_hook: Callable[..., Any] | None = None,
    mutating: set[str] | None = None,
) -> dict[str, list[HookMatcher]]:
    """PreToolUse: the permission gate (when given) then the cancel check; PostToolUse(+Failure): the trail.

    Responses of read tools (everything not in ``mutating``) are recorded as a length only: page text
    must never reach a report, where a viewer could read a withheld page through the trail.
    """

    async def record_tool_call(input_data: dict[str, Any], tool_use_id: str | None, context: HookContext) -> dict:
        tool = unqualify(str(input_data.get("tool_name", "")))
        ok, summary = response_summary(input_data.get("tool_response"))
        read_only = ok and tool not in (mutating or set())
        summary = f"{len(summary)} chars" if read_only else summary[:_SUMMARY_CHARS]  # read tools: never the text
        report.tool_calls.append(
            ToolCall(tool=tool, input=dict(input_data.get("tool_input") or {}), ok=ok, summary=summary)
        )
        return {}

    async def record_failure(input_data: dict[str, Any], tool_use_id: str | None, context: HookContext) -> dict:
        report.tool_calls.append(
            ToolCall(
                tool=unqualify(str(input_data.get("tool_name", ""))),
                input=dict(input_data.get("tool_input") or {}),
                ok=False,
                summary=f"failed: {str(input_data.get('error', ''))[:_SUMMARY_CHARS]}",
            )
        )
        return {}

    async def stop_if_cancelled(input_data: dict[str, Any], tool_use_id: str | None, context: HookContext) -> dict:
        if not manager.is_cancelled(report.audit_id):
            return {}
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "This audit was cancelled by an operator. Stop now and summarise.",
            }
        }

    pre_hooks = [gate_hook, stop_if_cancelled] if gate_hook is not None else [stop_if_cancelled]
    return {
        "PreToolUse": [HookMatcher(matcher=None, hooks=pre_hooks)],
        "PostToolUse": [HookMatcher(matcher=None, hooks=[record_tool_call])],
        "PostToolUseFailure": [HookMatcher(matcher=None, hooks=[record_failure])],
    }
