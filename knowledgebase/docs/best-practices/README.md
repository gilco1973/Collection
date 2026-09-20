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
