---
title: Best practices
owner: ai-platform-architecture
status: active
reviewed: 2026-09-15
tags: [best-practice]
audience: [engineer, data-scientist, product]
---
# Best practices

Practices that apply on every paved road. Each page is short, opinionated, and owned;
disagree by proposing a change through the [review process](../governance/review-process.md).

| Page | One-line rule |
| --- | --- |
| [Prompt engineering](prompt-engineering.md) | Write the evaluation first; the prompt is what makes it pass. |
| [Agent design](agent-design.md) | Use an agent only when a workflow cannot be written down. |
| [Security](security.md) | Treat every model input as untrusted and every tool as a privilege. |
| [Data classification](data-classification.md) | Label before you prompt; the label decides where data may go. |
| [Responsible AI](responsible-ai.md) | Decide up front where a human owns the outcome. |
| [Cost management](cost-management.md) | Cache, right-size, budget; measure cost per completed task. |
| [Observability](observability.md) | If it is not on a dashboard, it is not in production. |
| [Action tiers and confirmation](action-tiers-and-confirmation.md) | The tier on the catalog entry decides who says yes; the model never does. |
| [Untrusted input and the taint ceiling](untrusted-input-and-taint.md) | Text a model reads is evidence; an instruction in it caps the session to reads. |
| [Fail closed, secrets by name, ids-only logs](fail-closed-and-ids-only.md) | A missing gate never starts; a handler never holds a credential; a log line never holds text. |
| [The chained record and "not measured"](the-chained-record.md) | Everything the agent did is on one verifiable chain; a metric nobody measured is absent, not zero. |
| [Demonstrations as acceptance](demonstrations-as-acceptance.md) | Every increment ends in a command that writes a report with numbers. |
| [The model gateway and its guardrails](model-gateway-guardrails.md) | One door to the model: profile, allowlist, prompt hash, budget, context on the record. |
| [Building with a coding agent](building-with-a-coding-agent.md) | A plan pull request first, tests seen failing, a verdict before merge, a versioned handover. |
