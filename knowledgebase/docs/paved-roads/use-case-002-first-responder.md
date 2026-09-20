---
title: "Use case 002: the first responder"
owner: ai-platform-architecture
status: active
reviewed: '2026-09-20'
tags: [paved-road, agents, security, model-risk, observability]
audience: [engineer, product, risk, leadership]
---
# Use case 002: the first responder

The second internal build use case: an on-call assistant in the team's chat that goes from the page to the
postmortem. It assembles the war room, reads the situation with citations, acts under the commander's confirmation,
mitigates under dual control, keeps the incident record as a projection of a hash-chained log, and drafts the
postmortem. It is standalone (its controls are built in, standard library only) and it is where most of the
reusable components in the [collection](../components/README.md) come from.

## 1. Idea (use-case brief)

- **Problem.** A page means four tools and one tired person; the first ten minutes go to finding context; updates
  are late; the postmortem is written from memory days later.
- **Users.** Duty engineers (commanders), service owners (approvers), the communications role, reviewers.
- **Data involved.** Incident metadata and text (Internal), customer data that leaks into logs (masked before the
  model and the room), credentials (by name only), the record (append-only, chained).
- **Impact if wrong.** A wrong first read costs minutes (low; every claim is cited); an unconfirmed action is
  structurally impossible (W1 once, W2 dual control); an injected instruction taints the session and caps it to reads.

## 2. Pre-assessment (risk tier)

Tier 2 under the [model risk](../governance/model-risk.md) criteria: write actions on production systems, each behind
a person's confirmation or two people's approval; the model never executes. The first-read judge records confidence
and citation on the chain for the model risk entry; the judge is validated against duty-engineer labels before the
entry is accepted.

## 3. Build (on the paved roads)

| Road | How it is used |
| --- | --- |
| [Agent with tools](agent-with-tools.md) | The governed action loop: three fixed hooks per call, tiers R, W1, W2, a signed catalog, kill switches, budgets |
| [LLM gateway](llm-gateway.md) | The model gateway: inference profile, allowlist, prompt by reference, per-turn budget; a rules engine offline, a model online |
| [RAG service](rag-service.md) | Runbooks indexed with owners and access lists (a runbook without an owner is not served); incident memory from the record |
| [Evaluation pipeline](evaluation-pipeline.md) | Five demonstrations: replay, live week, game day, the injection corpus, chaos; the corpus is the release gate |

## 4. The three increments

| Increment | What a duty engineer gets |
| --- | --- |
| 1 · Assemble | A populated war room within two minutes of the page: the card, the pinned timeline, the on-call mentioned, a cited first read, the runbook step |
| 2 · Act with confirmation | Acknowledge, escalate, status updates from templates, action items, watches, shift handover: one card, one click, once |
| 3 · Mitigate and learn | Rollback, scale, flag, restart under dual control with expected effect, risk, undo and verification; the postmortem within the hour; incident memory |

Each increment is a configuration value that changes the signed catalog; raising it needs the previous
demonstration accepted.

## 5. Validation

Over 400 tests, the five demonstrations green offline (ten replays under two minutes with every claim cited and zero
unauthorized actions; the corpus at nine classes, all tainted, all proposals refused; four chaos drills with the
record intact), a threat-model delta table reviewed row by row against the code, and a readiness page that names
every account-bound step with its owner.

## 6. Release and operate

The runbook covers health, gates, kill switches, rotation, degraded modes as a table (including running the incident
without the assistant) and evidence. The first production deployment is increment 1, reads only.

## What the collection took from it

`governed-action-loop`, `audit-chain`, `untrusted-input-guard`, `cited-llm-engine`, `comm-templates`,
`prompt-pills-onboarding`, `teams-graph-connector`, `bedrock-converse-adapter`, `stdlib-http-client`,
`rs256-jwt-verify`, `aws-sigv4`, `secrets-by-name`, `ids-only-logging`, `fail-closed-config`, and the skills
`security-notes`, `production-readiness`, `runbook`, `handover`, `use-case-to-backlog`, `walkthrough-video`.
