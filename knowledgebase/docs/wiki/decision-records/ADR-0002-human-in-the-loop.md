---
title: "ADR-0002: a named human owns every consequential AI outcome"
owner: model-risk-management
status: active
reviewed: 2026-09-15
tags: [adr, governance, model-risk]
audience: [everyone]
---
# ADR-0002: a named human owns every consequential AI outcome

**Status:** Accepted

## Context

Supervisory expectations for model risk management require that models used in
decisions are validated, monitored and owned. Generative models add outputs that are
not decisions but influence them (drafts, summaries, recommendations) and agents that
act on systems. Without a clear rule, ownership diffuses to "the model".

## Decision

Every AI outcome with financial, legal, customer or operational impact has a named
person who reviews it and is accountable for it. For decisions (credit, pricing,
eligibility) the model only informs the person. For communications, a person approves
before sending or an approved template with an evaluation is used. For agents, live
actions are limited to an approved allow-list and everything else runs as a dry run
that a person reviews.

## Consequences

- Autonomous customer-facing decisions are out of scope until this record is superseded.
- Every agent has a dry-run mode, a permission gate and an audit trail
  ([agent with tools](../../paved-roads/agent-with-tools.md)).
- Throughput of AI-assisted processes is bounded by review capacity; teams design the
  review step to be fast (structured outputs, diffs, summaries) rather than remove it.

## Alternatives considered

- Risk-tiered full autonomy for tier 3 use cases: rejected for now; revisit with
  evidence from two years of monitored operation.
