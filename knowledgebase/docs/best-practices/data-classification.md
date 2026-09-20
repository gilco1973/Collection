---
title: Data classification
owner: ai-platform-architecture
status: active
reviewed: 2026-09-15
tags: [best-practice, data, security, governance]
audience: [everyone]
---
# Data classification for AI

Every prompt, document, dataset and log carries one of four labels. The label decides
which models may see it, where it may be logged, and how long it is kept.

| Tier | Examples | Allowed models | Logging |
| --- | --- | --- | --- |
| Public | Published product pages, press releases | Any gateway model | Full, 1 year |
| Internal | Procedures, non-sensitive internal documents | Any gateway model | Full, 1 year |
| Confidential | Customer records, employee data, unpublished financials | Approved models with contractual data controls only | Hashed prompt, token counts, 90 days |
| Restricted | Authentication material, cryptographic keys, regulator correspondence marked restricted | None | Rejected at the gateway |

## Rules

1. Label before you prompt. If you cannot label it, treat it as Confidential and ask.
2. Mixing tiers takes the highest tier. A prompt with one Confidential line is Confidential.
3. Restricted data does not go to a model. There is no exception path.
4. Evaluation sets follow the same tiers: a Confidential evaluation set lives in the
   Confidential store, not in the repository.
5. This knowledge base is **Internal**. Nothing Confidential or Restricted is written
   into any page, example, screenshot or report.

## How to label

- Gateway calls: the `X-Data-Classification` header, enforced server-side.
- Documents for RAG: the `classification` field at ingestion; one index per tier.
- Datasets: the data catalog entry.

## Related

- [Security for AI systems](security.md)
- [LLM gateway](../paved-roads/llm-gateway.md)
