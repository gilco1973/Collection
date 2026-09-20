---
name: incident-summary
description: Produce a structured post-incident summary from an incident channel transcript and timeline.
title: Incident summary skill
owner: ai-platform-engineering
status: active
reviewed: 2026-09-15
tags: [skill, observability]
audience: [engineer]
---
# Incident summary skill

## When to use
After an incident is resolved and the channel is quiet, when the incident lead asks for
the summary. Not during the incident.

## Inputs
- Channel transcript export and alert timeline (Internal tier; check for Confidential
  content before use and redact it first).

## Steps
1. Build the timeline from timestamps, not from memory; quote the source line for each entry.
2. State impact in measurable terms: duration, affected feature, request volume, customers if any.
3. Identify the trigger, the contributing causes and what detected it.
4. List the actions taken and which one resolved it.
5. Draft follow-ups as verifiable statements ("add alert on X below Y") with an owner placeholder.

## Tools
| Tool | Mutating | Notes |
| --- | --- | --- |
| Transcript read | No | |
| Jira issue create | Yes | Only for follow-ups, one per action, after human review |

## Checks before finishing
- [ ] Every timeline entry cites its source.
- [ ] No customer identifiers in the summary.
- [ ] Follow-ups are actions, not observations.

## Output format
Sections: Summary, Impact, Timeline, Causes, Detection, Resolution, Follow-ups.

## Evaluation
`evals/` — 5 synthetic incidents with reference summaries, graded by rubric.
