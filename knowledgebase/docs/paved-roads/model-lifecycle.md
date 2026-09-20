---
title: Model lifecycle
owner: ai-platform-architecture
status: active
reviewed: 2026-09-15
tags: [paved-road, model-risk, governance]
audience: [engineer, product, risk]
---
# Model lifecycle

Every AI use case moves through the same stages. The stages exist so that the bank's
model risk obligations are met by the process rather than by heroics at release time.

## Stages

1. **Idea** — a one-page use-case brief: problem, users, data involved (with
   classification), impact if wrong. Reviewed by the team lead.
2. **Pre-assessment** — Model Risk Management assigns a risk tier using the
   [model risk](../governance/model-risk.md) criteria. The tier sets the evidence required.
3. **Build** — on a [paved road](README.md), with the evaluation set written first.
4. **Validation** — independent review of the evaluation evidence, security review, and
   for tier 1 and 2 use cases a formal validation report.
5. **Release** — through the gates in the [evaluation pipeline](evaluation-pipeline.md),
   with a monitoring page and a named model owner.
6. **Operate** — scheduled evaluation runs, incident process, periodic review at the
   cadence the tier requires.
7. **Retire** — decommission plan, data deletion, risk record closed.

## Artifacts per stage

| Stage | Artifact | Lives in |
| --- | --- | --- |
| Idea | Use-case brief | Jira `AIKB`, type *Use case* |
| Pre-assessment | Risk tier record | Model inventory |
| Build | Code, prompts, evaluation set, decision records | Source control |
| Validation | Validation report | Model inventory |
| Release | Monitoring page, runbook | Observability portal, source control |
| Operate | Evaluation trend, incidents | Observability portal |

## Who to talk to

Model owners are accountable at every stage. Model Risk Management owns tiering and
validation. AI Platform Architecture owns the roads. The onboarding
[30/60/90](../onboarding/30-60-90.md) page expects you to run a pre-assessment by day 90.
