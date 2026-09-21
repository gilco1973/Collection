---
name: runbook
description: Write the runbook for an AI service for the engineer on duty for the service itself; health, gates, kill switches, rotation, degraded modes as a table, raising the increment, evidence.
title: Runbook skill
owner: ai-platform-engineering
status: active
reviewed: '2026-09-20'
tags: [skill, observability]
audience: [engineer]
---
# Runbook skill

## When to use
Before the first deployment; updated at every increment and after every incident on the service itself. The reader
is the engineer on duty for the service, at night, who has not read the code.

## Inputs
- The health endpoint and what it returns; the gates and their configuration names; the kill-switch scopes; the secrets and their rotation rules; the dependencies and what happens when each is lost; the increment mechanism.
- `TEMPLATE.md` in `components/skills/runbook/`.

## Steps
1. **Health.** The endpoint, its fields, and what a change in the chain head means. Which metric is a stop-ship.
2. **The gates.** How to add a person, how to add a team, and the fact that an empty gate refuses everyone.
3. **Kill switches.** Scopes, the command, how fast a stop lands, and why clearing is a reviewed change.
4. **Rotation.** Which secrets rotate without a restart, which need one, and what a rotation invalidates.
5. **Degraded modes.** A table with one row per dependency: what happens when it is lost, what the person does. The last row is the service itself: how the work continues without it and how it catches up when it returns.
6. **Raising the increment.** The order, the gate for each step, and the fastest way to remove all write tools.
7. **Evidence.** The commands that return a turn's trace and verify the record.

## Tools
| Tool | Mutating | Notes |
| --- | --- | --- |
| The chaos drill | No (fakes) | Run it on every release; each row of the degraded-modes table is a drill |

## Checks before finishing
- [ ] Every degraded-modes row has a "what you do".
- [ ] Every command in the page runs as written.
- [ ] No hostname, group id or secret value appears; names and placeholders only.

## Output format
`RUNBOOK.md` with the seven numbered sections.

## Evaluation
A new on-duty engineer walks one degraded-mode row from the page alone during the game day.
