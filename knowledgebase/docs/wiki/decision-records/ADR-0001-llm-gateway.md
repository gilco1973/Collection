---
title: "ADR-0001: all model calls go through an LLM gateway"
owner: ai-platform-architecture
status: active
reviewed: 2026-09-15
tags: [adr, security, cost]
audience: [engineer, risk]
---
# ADR-0001: all model calls go through an LLM gateway

**Status:** Accepted

## Context

Teams began integrating model providers directly, each holding vendor credentials,
each logging differently, and none enforcing data classification consistently. Model
risk and security reviews could not answer "which data reached which model" without
reading every codebase.

## Decision

All model calls from any application go through a single internal gateway. The gateway
holds vendor credentials, enforces the data-classification header, logs at the
classification's retention tier, routes logical model names to concrete models, and
applies budgets. Applications receive gateway keys scoped to team and environment.

## Consequences

- One audited place to answer the regulator's question.
- Model migrations become routing changes.
- Added latency (measured under 30 ms at p95) and a single point of failure, mitigated
  by multi-region deployment and a documented degraded mode.
- Teams lose direct access to provider features until the gateway exposes them; the
  platform team commits to a two-week turnaround for new provider features.

## Alternatives considered

- Per-application vendor access with a shared library: rejected because enforcement
  would depend on every team upgrading the library.
- A provider-side organisation account with sub-keys: rejected because classification
  enforcement and hashed logging are not available there.
