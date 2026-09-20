---
title: "Tutorial 3: an agent with the Claude Agent SDK"
owner: ai-platform-enablement
status: active
reviewed: 2026-09-15
tags: [tutorial, agents, security]
audience: [engineer]
---
# Tutorial 3: an agent with the Claude Agent SDK

## Goal

Build a small agent that inspects a folder of markdown pages and proposes fixes, with a
permission gate, a dry-run default and an audit trail. This is the [agent with tools](../paved-roads/agent-with-tools.md)
road in miniature; the full-size version is the [librarian](../governance/librarian-agent.md).

## Steps

1. Install the SDK: `poetry add claude-agent-sdk`. Authentication is inherited from
   the environment as configured by the platform team; do not put a key in code.

2. Define tools as an in-process MCP server:

   ```python
   from claude_agent_sdk import create_sdk_mcp_server, tool

   @tool(name="list_pages", description="List markdown pages.", input_schema={})
   async def list_pages(args: dict) -> dict:
       return {"content": [{"type": "text", "text": "\n".join(p.name for p in PAGES)]}}

   @tool(name="set_title", description="Set a page title. Mutating; needs a reason.",
         input_schema={"page": str, "title": str, "reason": str})
   async def set_title(args: dict) -> dict:
       ...  # record before/after, write only when not dry-run

   server = create_sdk_mcp_server(name="pages", tools=[list_pages, set_title])
   ```

3. Write the gate policy once, and install it at both interception points the
   SDK offers. `can_use_tool` is skipped for any whole tool named in
   `allowed_tools` (the SDK auto-approves those first), so never list your tools
   there; a `PreToolUse` hook runs for every call and cannot be shadowed:

   ```python
   from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

   MUTATING = {"mcp__pages__set_title"}
   ALLOWED = {"mcp__pages__list_pages", "mcp__pages__set_title"}

   def deny_reason(name: str, dry_run: bool) -> str | None:
       if name not in ALLOWED:
           return "not one of this agent's tools"
       if dry_run and name in MUTATING:
           return "dry run: describe the change instead"
       return None

   def make_gate(dry_run: bool):
       async def can_use_tool(name, tool_input, context):
           reason = deny_reason(name, dry_run)
           return PermissionResultDeny(message=reason) if reason else PermissionResultAllow(updated_input=tool_input)

       async def pre_tool_use(input_data, tool_use_id, context):
           reason = deny_reason(input_data["tool_name"], dry_run)
           if reason is None:
               return {}
           return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                          "permissionDecision": "deny",
                                          "permissionDecisionReason": reason}}
       return can_use_tool, pre_tool_use
   ```

4. Remove every built-in tool with `tools=[]`, record every call with a
   `PostToolUse` hook, and run:

   ```python
   from claude_agent_sdk import ClaudeAgentOptions, HookMatcher, query

   can_use_tool, pre_tool_use = make_gate(dry_run=True)
   options = ClaudeAgentOptions(
       system_prompt="You keep page titles accurate. Fix only what is wrong.",
       mcp_servers={"pages": server},
       tools=[],                      # no built-in file, shell, web or tool-search tools
       allowed_tools=[],              # never pre-approve; every call reaches the gate
       disallowed_tools=["Bash", "Write", "Edit", "WebFetch", "WebSearch", "ToolSearch"],
       can_use_tool=can_use_tool,
       hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[pre_tool_use])],
              "PostToolUse": [HookMatcher(matcher=None, hooks=[record_call])]},
       max_turns=10, max_budget_usd=0.5, setting_sources=[],
   )
   async for message in query(prompt="Audit the pages.", options=options):
       ...
   ```

5. Run in dry-run: the agent lists pages, tries `set_title`, is denied, and explains what
   it would have changed. Then run live with an explicit server-side switch and read the audit trail.

## What you learned

- Gate in code, at both interception points; budget in configuration; dry-run by
  default; trail for every call; no built-in tools unless the risk record says so.
- A permission callback that never fires looks exactly like one that always allows.
  Run once and read the SDK's warnings and the audit trail before trusting the gate.

Next: [Tutorial 4](04-rag-basics.md).
