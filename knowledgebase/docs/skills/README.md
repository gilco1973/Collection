---
title: Agent skills catalog
owner: ai-platform-enablement
status: active
reviewed: 2026-09-15
tags: [skill, agents]
audience: [engineer, everyone]
---
# Agent skills catalog

A skill is a folder with a `SKILL.md` that teaches an agent (or a person) a repeatable
procedure: when to use it, the steps, the checks, and the output format. Skills are how
we make good practice reusable instead of tribal.

## Catalog

| Skill | Use when | Owner |
| --- | --- | --- |
| [code-review](code-review/SKILL.md) | Reviewing code, including AI-generated code, against our standards | ai-platform-architecture |
| [incident-summary](incident-summary/SKILL.md) | Turning an incident channel into a structured post-incident summary | ai-platform-engineering |
| [policy-qa](policy-qa/SKILL.md) | Answering policy questions with citations from the governed corpus | ai-platform-enablement |
<!-- collection:start -->
| [handover](handover/SKILL.md) | The versioned handover document: what it is, since last time, tickets done here vs what remains on the account, decisions, layout, limits | ai-platform-enablement |
| [pixel-parity-screenshots](pixel-parity-screenshots/SKILL.md) | Prove a front end matches its design artboards: render both under identical conditions, diff, document exceptions, gate CI on zero pixels | ai-platform-enablement |
| [production-readiness](production-readiness/SKILL.md) | One table for a service leaving the sandbox: area, DONE/WRITTEN/OPEN, evidence with numbers, the open item with an owner | ai-platform-enablement |
| [runbook](runbook/SKILL.md) | The runbook for the engineer on duty for the service itself: health, gates, kill switches, rotation, degraded modes, increments, evidence | ai-platform-enablement |
| [security-notes](security-notes/SKILL.md) | Write SECURITY.md for an AI service: threat-model delta (threat, control, where), data classes, the injection corpus, known limits | ai-platform-enablement |
| [use-case-to-backlog](use-case-to-backlog/SKILL.md) | One plan file to a Jira-ready backlog: epics, tickets, phases, critical path, CSV; the specification and the backlog never drift | ai-platform-enablement |
| [walkthrough-video](walkthrough-video/SKILL.md) | A narrated, captioned walkthrough video from real screenshots, a slide plan, text-to-speech and ffmpeg; rebuilt, never re-recorded | ai-platform-enablement |
<!-- collection:end -->

## Writing a skill

1. Copy [templates/SKILL-template.md](templates/SKILL-template.md) into `skills/<name>/SKILL.md`.
2. Fill the frontmatter: `name`, `description` (one sentence that says *when* to use it),
   and the standard knowledge-base fields.
3. Keep the body under 150 lines. Link to detail rather than inlining it.
4. Add an evaluation: at least five input/expected-output pairs in `skills/<name>/evals/`.
5. Submit through the [review process](../governance/review-process.md).

## Rules

- A skill never contains credentials, customer data or environment-specific hostnames.
- A skill that calls tools names them and states which are mutating.
- Deprecate rather than delete: set `status: deprecated` and link the replacement.
