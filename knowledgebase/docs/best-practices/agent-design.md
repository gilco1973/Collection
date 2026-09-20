---
title: Agent design
owner: ai-platform-architecture
status: active
reviewed: 2026-09-15
tags: [best-practice, agents, security]
audience: [engineer]
---
# Agent design

## Should this be an agent?

Answer all four. A "no" to any means build a workflow or an assistant instead.

- **Complexity**: is the task multi-step and hard to specify fully in advance?
- **Value**: does the outcome justify higher cost and latency?
- **Viability**: is the model demonstrably capable at this task type on our evaluation set?
- **Cost of error**: can mistakes be caught and reversed (review, rollback, dry-run)?

## Tool surface

- Few, well-described tools beat many thin ones. A tool description is a prompt.
- Every mutating tool takes a `reason` argument and records an action with before and
  after state, so a reviewer can read why it happened and undo it.
- Read tools and write tools are separate objects; the permission gate distinguishes
  them by name, not by trust in the model.
- Built-in file, shell and web tools are off by default.

## Control

- `max_turns` and `max_budget_usd` on every run.
- A cancel path an operator can use mid-run (the librarian uses a pre-tool hook).
- Dry-run as the default mode; live mode is a server-side switch.
- Deterministic checks run *before* the model so it starts from evidence, not from a
  blank page. The librarian's `run_checks` tool is the pattern.

## Context

- Prefer retrieval and summaries over ever-longer transcripts.
- Use the provider's compaction or context-editing features for long sessions rather
  than home-grown truncation that silently drops tool results.

## Reference implementation

The [librarian agent](../governance/librarian-agent.md) and [Tutorial 3](../tutorials/03-agent-sdk.md).
