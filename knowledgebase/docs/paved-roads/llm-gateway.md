---
title: LLM gateway
owner: ai-platform-architecture
status: active
reviewed: 2026-09-15
tags: [paved-road, security, cost, observability]
audience: [engineer]
---
# LLM gateway

The gateway is the single egress for model calls. It exists so that authentication,
data-classification enforcement, logging, rate limiting, cost attribution and model
routing happen once, in one audited place, rather than in every application.

## What it gives you

- **Credentials**: applications hold a gateway key scoped to a team and environment. The
  vendor key never leaves the gateway. Keys are rotated centrally.
- **Classification enforcement**: each request carries a data classification header
  (see [data classification](../best-practices/data-classification.md)). Requests above
  the tier allowed for the selected model are rejected, not logged.
- **Logging**: prompts and completions are logged with retention per classification.
  Confidential-tier content is logged as hashes plus token counts only.
- **Routing**: a logical model name (for example `assistant-default`) maps to a concrete
  vendor model chosen by the platform team. Migrations happen without code changes.
- **Budgets**: per-team monthly budgets with alerts at 80% and hard stops at 100% for
  non-production tiers.

## How to call it

Use the internal SDK bundle, which wraps the vendor SDK with gateway defaults:

```python
from bank_ai.gateway import client  # base URL, key and headers pre-configured

response = client.messages.create(
    model="assistant-default",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Summarise the attached policy in five bullets."}],
    extra_headers={"X-Data-Classification": "internal"},
)
```

[Tutorial 1](../tutorials/01-first-call.md) walks through this end to end.

## What the gateway does not do

- It does not review your prompts for quality. See [prompt engineering](../best-practices/prompt-engineering.md).
- It does not make an application safe from prompt injection. See [security](../best-practices/security.md).
- It does not approve a use case. See [model lifecycle](model-lifecycle.md).

## Decision record

[ADR-0001](../wiki/decision-records/ADR-0001-llm-gateway.md) records why a gateway was
chosen over per-application vendor access.
