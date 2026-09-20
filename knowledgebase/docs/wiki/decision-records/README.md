---
title: Decision records
owner: ai-platform-architecture
status: active
reviewed: 2026-09-15
tags: [adr]
audience: [engineer, product, risk]
---
# Decision records

Architecture decision records (ADRs) capture a decision, its context and its
consequences at the time it was made. They are immutable once accepted; a change is a
new record that supersedes the old one.

| ADR | Title | Status |
| --- | --- | --- |
| [ADR-0001](ADR-0001-llm-gateway.md) | All model calls go through an LLM gateway | Accepted |
| [ADR-0002](ADR-0002-human-in-the-loop.md) | A named human owns every consequential AI outcome | Accepted |

## Writing one

Use the sections: Context, Decision, Consequences, Alternatives considered, Status.
Number sequentially. Submit through the [review process](../../governance/review-process.md);
AI Platform Architecture and Model Risk Management both sign off.
