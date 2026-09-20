---
title: Evaluation pipeline
owner: ai-platform-architecture
status: active
reviewed: 2026-09-15
tags: [paved-road, evaluation, observability]
audience: [engineer, data-scientist]
---
# Evaluation pipeline

"It works" is a claim backed by an evaluation set, a grader and a trend. This road is the
shared pipeline every AI feature uses to make that claim before release and keep making
it afterwards.

## Parts

- **Evaluation set**: inputs with expected behaviour, in source control next to the
  feature. Minimum sizes: 50 for a prototype, 100 for internal release, 300 for
  customer-facing release. Sourced from real (classification-appropriate) traffic where
  possible, synthesised where not, and labelled by the feature's owner.
- **Grader**: deterministic where possible (exact match, schema validity, citation
  present), model-graded with a rubric where not. Model graders are themselves evaluated
  against a human-labelled sample.
- **Runner**: runs the set on every change to a prompt, tool definition or model
  routing, in CI, and on a schedule in production against the live model.
- **Dashboard**: score trend per feature with the change that caused each movement.

## Release gates

| Stage | Gate |
| --- | --- |
| Pull request | Score not below the main branch by more than the agreed tolerance |
| Internal release | Score at or above the feature's target; no critical-category failures |
| Customer-facing release | As above, plus fairness and refusal evaluations signed off by Model Risk |
| Production | Weekly run against live model; alert on drift beyond tolerance |

## How to start

[Tutorial 5](../tutorials/05-evaluations.md) builds a first evaluation set and runner in
under an hour. Bring it to the evaluation review before you bring the prompt.
