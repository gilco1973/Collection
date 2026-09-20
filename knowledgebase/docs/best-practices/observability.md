---
title: Observability
owner: ai-platform-architecture
status: active
reviewed: 2026-09-15
tags: [best-practice, observability, evaluation]
audience: [engineer]
---
# Observability

## Every production feature has a page showing

| Signal | Why |
| --- | --- |
| Request rate, latency (p50, p95), error rate | Is it up and usable |
| Token usage and cost per request and per completed task | Budget and efficiency |
| Cache hit rate | Whether prompt caching is working |
| Refusal rate and hand-off rate | Whether users are being served or bounced |
| Evaluation score trend (scheduled runs against the live model) | Whether quality is drifting |
| User feedback (thumbs, corrections) | Ground truth you did not have to label |
| Tool-call counts and denial counts (agents) | Whether the gate is doing work |

## Logging rules

- Log at the retention tier of the data classification. Confidential prompts are
  logged as hashes and token counts.
- Correlate by request id from channel to gateway to tool. The gateway id is the key.
- Never log credentials or tool secrets. Tool inputs are logged; tool credentials are not.

## Alerts

- Evaluation score below tolerance for two consecutive scheduled runs.
- Budget at 80% and 100%.
- Error rate or refusal rate step change.
- Any critical sensitive-content finding from the librarian in this knowledge base.

## Runbooks

Each page links its runbook. A runbook names the model owner, the roll-back (gateway
routing change or feature flag) and the escalation path.
