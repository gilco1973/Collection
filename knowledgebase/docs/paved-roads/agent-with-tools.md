---
title: Agent with tools
owner: ai-platform-architecture
status: active
reviewed: 2026-09-15
tags: [paved-road, agents, security]
audience: [engineer]
---
# Agent with tools

An agent is a model that decides which tools to call, in what order, to complete a task.
Use this road only when the task is genuinely multi-step and cannot be specified as a
fixed workflow. The [agent design](../best-practices/agent-design.md) page has the
decision test; most first projects should be an [assistant](assistant-service.md) instead.

## Reference architecture

```
task ─► agent runtime (Claude Agent SDK) ─► permission gate ─► tools (MCP servers)
              │                                  │
              ▼                                  ▼
        audit trail (every tool call)      deny / allow / ask a human
```

## Non-negotiables

1. **Permission gate in code, not in the prompt.** One policy function decides whether
   a tool runs, installed as the runtime's `can_use_tool` callback *and* as a
   `PreToolUse` hook (the callback is skipped for any tool the options pre-approve, so
   nothing is ever pre-approved). The prompt tells the model the rules; the gate
   enforces them.
2. **Dry-run by default.** Every agent has a mode in which mutating tools are denied and
   the agent describes what it would do. Live mode is a server-side setting, never a
   request parameter a caller can flip.
3. **No built-ins by default.** The runtime starts with an empty built-in tool set
   (`tools=[]`); file, shell, web and tool-search tools are enabled only when the use
   case needs them and the risk record says so.
4. **Budgets.** Maximum turns and maximum spend per run are set in configuration.
5. **Audit trail.** Every tool call, its input and its outcome are recorded with the run.
6. **Human approval** for any action with financial, legal or customer impact
   ([ADR-0002](../wiki/decision-records/ADR-0002-human-in-the-loop.md)).

## Worked example

The [librarian agent](../governance/librarian-agent.md) that maintains this knowledge
base is built on this road and is the reference implementation: read its `agent/gate.py`,
`agent/hooks.py` and `agent/options.py`. [Tutorial 3](../tutorials/03-agent-sdk.md)
builds a smaller one from scratch.
