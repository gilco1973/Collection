"""Permission gate: the only policy that decides whether a tool call may run.

The same policy is enforced twice, because the SDK offers two interception
points with different blind spots:

- ``can_use_tool`` — consulted for calls that no allow rule pre-approved. Any
  whole tool named in ``allowed_tools`` (or in a settings file) is auto-approved
  *before* this callback, so the librarian never lists its tools there.
- A ``PreToolUse`` hook — runs for every call regardless of allow rules, and is
  where denials are written into the audit trail (a denied call never reaches
  ``PostToolUse``).

Rules: unknown tools are denied; mutating tools are denied while the audit is a
dry run; mutating tools need a non-empty ``reason``.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny, ToolPermissionContext

from kb_librarian.models import AuditReport, ToolCall
from kb_librarian.tools.server import unqualify

GateFn = Callable[
    [str, dict[str, Any], ToolPermissionContext],
    Awaitable[PermissionResultAllow | PermissionResultDeny],
]


class GatePolicy:
    def __init__(self, dry_run: bool, allowed_tools: list[str], mutating: set[str]) -> None:
        self.dry_run = dry_run
        self.allowed = set(allowed_tools)
        self.mutating = set(mutating)

    def is_mutating(self, tool_name: str) -> bool:
        return unqualify(tool_name) in self.mutating

    def deny_reason(self, tool_name: str, tool_input: dict[str, Any]) -> str | None:
        """Return why this call must be denied, or ``None`` when it may run. Any surprise denies."""
        try:
            return self._deny_reason(tool_name, tool_input)
        except Exception as exc:  # fail closed: an unexpected input shape is never an allow
            return f"'{tool_name}' was denied: the gate could not evaluate its input ({type(exc).__name__})."

    def _deny_reason(self, tool_name: str, tool_input: dict[str, Any]) -> str | None:
        if not isinstance(tool_input, dict):
            raise TypeError("tool_input must be a mapping")
        if tool_name not in self.allowed:
            return f"'{tool_name}' is not a librarian tool; only the kb MCP tools are permitted."
        if self.dry_run and self.is_mutating(tool_name):
            return (
                f"'{unqualify(tool_name)}' is a mutating tool and this audit is a DRY RUN. "
                "Describe the intended change in your summary instead of retrying."
            )
        if self.is_mutating(tool_name) and not str(tool_input.get("reason", "")).strip():
            return f"'{unqualify(tool_name)}' requires a non-empty 'reason'."
        return None


def make_can_use_tool(policy: GatePolicy) -> GateFn:
    async def can_use_tool(
        tool_name: str, tool_input: dict[str, Any], context: ToolPermissionContext
    ) -> PermissionResultAllow | PermissionResultDeny:
        reason = policy.deny_reason(tool_name, tool_input)
        if reason is not None:
            return PermissionResultDeny(message=reason)
        return PermissionResultAllow(updated_input=tool_input)

    return can_use_tool


def make_pretooluse_gate(policy: GatePolicy, report: AuditReport | None = None):
    """The same policy as a ``PreToolUse`` hook, which no allow rule can shadow."""

    async def gate_hook(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict:
        tool_name = str(input_data.get("tool_name", ""))
        tool_input = dict(input_data.get("tool_input") or {})
        reason = policy.deny_reason(tool_name, tool_input)
        if reason is None:
            return {}
        if report is not None:
            report.tool_calls.append(
                ToolCall(tool=unqualify(tool_name), input=tool_input, ok=False, summary=f"denied: {reason}")
            )
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }

    return gate_hook
