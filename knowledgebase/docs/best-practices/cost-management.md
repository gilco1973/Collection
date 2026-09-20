---
title: Cost management
owner: ai-platform-architecture
status: active
reviewed: 2026-09-15
tags: [best-practice, cost, observability]
audience: [engineer, leadership]
---
# Cost management

Measure cost per completed task, not per request. A cheaper request that needs more
retries or more turns is not cheaper.

## Free wins, in order

1. **Prompt caching**: stable prefix first (system prompt, tool definitions, reference
   documents), volatile content last. Verify with the cache-read token counts in the
   gateway logs; zero means something in the prefix changes per request.
2. **Input hygiene**: send the retrieved chunks, not the whole document; strip
   boilerplate; do not resend conversation history the model no longer needs.
3. **Loop hygiene**: agents stop when done; `max_turns` is a safety net, not a target.
4. **Output hygiene**: ask for the format you need; structured outputs are shorter than prose.
5. **Batch** anything that is not latency-sensitive.

## Trade-offs, measured before chosen

- **Effort / thinking level**: lower effort on the strongest model often matches a
  weaker model at high effort, with one cache namespace. Measure on your evaluation set.
- **Model choice**: the gateway's logical names let the platform team move workloads;
  ask for a routing change with evidence rather than hard-coding a smaller model.

## Budgets

- Every team has a monthly gateway budget; every agent run has a per-run cap.
- Alerts at 80%; non-production hard-stops at 100%.
- Cost is attributed per logical model and per feature on the [observability](observability.md) dashboard.
