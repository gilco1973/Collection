---
title: Paved roads
owner: ai-platform-architecture
status: active
reviewed: 2026-09-15
tags: [paved-road, agents, rag]
audience: [engineer, data-scientist, product]
---
# Paved roads

A paved road is an approved, supported way to build a class of AI system. Building on a
paved road means the security review, model risk assessment, observability and cost
controls are largely done for you. Building off-road is allowed, but it starts with an
architecture review and you own everything the road would have given you.

## The roads

| Road | Use it for | Page |
| --- | --- | --- |
| LLM gateway | Every model call, from any language | [llm-gateway.md](llm-gateway.md) |
| Assistant service | Chat or Q&A over approved content, with a human in the loop | [assistant-service.md](assistant-service.md) |
| RAG service | Grounded answers over a governed document corpus | [rag-service.md](rag-service.md) |
| Agent with tools | Multi-step tasks that call internal systems under a permission gate | [agent-with-tools.md](agent-with-tools.md) |
| Evaluation pipeline | Proving any of the above works, before and after release | [evaluation-pipeline.md](evaluation-pipeline.md) |
| Model lifecycle | Getting a model or use case from idea to production and retirement | [model-lifecycle.md](model-lifecycle.md) |

The first internal use case built on these roads is this knowledge base itself:
[Use case 001](use-case-001-knowledge-base.md) walks it through every stage.

## Shared properties of every road

- Calls go through the gateway; direct vendor keys are not issued to applications.
- Prompts, tool definitions and evaluation sets live in source control with the code.
- Every production use case has a model owner, a risk tier and a monitoring page.
- Human approval is required for any action with financial, legal or customer impact
  ([ADR-0002](../wiki/decision-records/ADR-0002-human-in-the-loop.md)).

## Proposing a new road

Write a decision record in [wiki/decision-records](../wiki/decision-records/README.md),
get it reviewed by AI Platform Architecture and Model Risk Management, then add the page here.
