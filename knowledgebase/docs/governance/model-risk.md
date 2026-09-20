---
title: Model risk management for AI use cases
owner: model-risk-management
status: active
reviewed: 2026-09-15
tags: [governance, model-risk]
audience: [engineer, product, risk, leadership]
---
# Model risk management for AI use cases

Supervisory guidance on model risk (SR 11-7 and its equivalents) expects that models
used in the bank are inventoried, validated independently, monitored and owned.
Generative and agentic systems are models for this purpose. This page tells engineers
what that means in practice.

## Tiers

| Tier | Criteria | Evidence before release | Review cadence |
| --- | --- | --- | --- |
| 1 | Influences customer decisions, regulatory reporting or financial outcomes; or acts autonomously on systems of record | Full validation report, fairness evaluation, security review, incident runbook, monitoring page | Quarterly |
| 2 | Customer-facing content or internal decisions with material impact; agents with any live mutating tools | Evaluation evidence reviewed by Model Risk, security review, monitoring page | Semi-annual |
| 3 | Internal productivity with a human owning every output; agents in dry-run only | Use-case brief, evaluation set, model owner named | Annual |

## What validators look for

- The evaluation set: representative, labelled by the owner, sized for the tier,
  including refusal and adversarial cases.
- Evidence the grader is trustworthy (human-labelled sample agreement).
- The permission gate and audit trail for agents; dry-run evidence for live tools.
- Data classification of every input, with the gateway header enforced.
- Monitoring with thresholds and a runbook naming the roll-back.
- Change control: prompts, tools and routing in source control with review.

## Inventory

Every use case at any tier has a model inventory record with owner, tier, status,
validation date and monitoring link. The record is created at pre-assessment; a use case
without one is not in production, whatever the deployment says.

## Related

- [Model lifecycle](../paved-roads/model-lifecycle.md)
- [Responsible AI](../best-practices/responsible-ai.md)
- [ADR-0002](../wiki/decision-records/ADR-0002-human-in-the-loop.md)
