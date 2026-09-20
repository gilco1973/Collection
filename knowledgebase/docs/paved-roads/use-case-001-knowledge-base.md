---
title: "Use case 001: the knowledge base and its librarian"
owner: ai-platform-architecture
status: active
reviewed: 2026-09-15
tags: [paved-road, agents, model-risk, governance]
audience: [engineer, product, risk, leadership]
---
# Use case 001: the knowledge base and its librarian

The first internal build use case on the AI Platform is this knowledge base and the
librarian agent that maintains it. It goes through the [model lifecycle](model-lifecycle.md)
exactly as any other use case would, so new teams can read a completed example of every
artifact they will be asked for.

## 1. Idea (use-case brief)

- **Problem.** Onboarding material for AI builders drifts: pages go stale, links break,
  ownership blurs, and secrets occasionally land in wiki pages.
- **Users.** New joiners (readers), page owners, platform operators.
- **Data involved.** Internal-tier documentation only. No customer, employee or
  Confidential data may enter the knowledge base; the librarian's sensitive-content check
  and the content standards enforce this.
- **Impact if wrong.** A reader follows outdated guidance (low); a live audit rewrites
  page metadata incorrectly (low, reversible by rollback); a secret in a page is not caught
  (medium, mitigated by the check and CI gate).

## 2. Pre-assessment (risk tier)

**Tier 3** under the [model risk](../governance/model-risk.md) criteria: internal
productivity; every output is owned by a human (page owners review flags, operators
approve live runs); the agent runs dry by default and every mutating tool (frontmatter and index edits,
rollback, Confluence publish, Jira issue) is gated, logged with before/after hashes and,
for page edits, reversible. The record lives in the
model inventory with `ai-platform-engineering` as model owner.

## 3. Build (on the paved roads)

| Road | How it is used |
| --- | --- |
| [Agent with tools](agent-with-tools.md) | Claude Agent SDK, in-process MCP tools, one gate policy at both interception points, no built-in tools, budgets, cancel, audit trail |
| [LLM gateway](llm-gateway.md) | Model calls carry the Internal classification; the logical model is set by configuration |
| [Evaluation pipeline](evaluation-pipeline.md) | The deterministic checks are the evaluation set for the *content*; the fixture knowledge base with planted defects is the evaluation set for the *agent* (every mutation must be denied in dry run, every planted defect must be found) |
| [Assistant service](assistant-service.md) | Not used in v1; "Ask the knowledge base" is the candidate v2 feature |

Code, prompts, tool definitions, the contract (`kb.config.yaml`) and the tests live in
source control with the pages they govern.

## 4. Validation

Evidence reviewed before the first live run: unit and API test suites with coverage
gates, a review panel (architecture, code, security, agent-SDK, product, adversarial
audit) with every Critical and Important finding fixed, and real dry-run audits against
the fixture showing the gate denying every mutation attempt. Security review confirmed
the server-side live gate, the redaction of persisted reports, and the two-account
Atlassian split.

## 5. Release

- CI gate: `kb-librarian check` on every change to the content.
- Nightly dry-run audit with the markdown report as an artifact.
- Weekly live audit limited to `frontmatter,structure`, enabled by the repository
  variable `KB_WEEKLY_LIVE`; its page changes arrive as a pull request and its report as a
  build artifact, both reviewed by a named operator before merge.
- Monitoring page: audit status, findings by severity, denied tool calls, cost per run,
  review-queue size (all available from the API for the platform dashboard).

## 6. Operate

Runbook: `docs/governance/librarian-agent.md` (safety model, cancel, rollback).
Incidents (a page with sensitive content, a wrong live change) follow the
[review process](../governance/review-process.md) and the incident-summary skill.
Quarterly: re-run the fixture evaluation after any SDK or model change.

## 7. Retire

If the knowledge base moves to another system, the mirror to Confluence is switched off,
the API is removed from the platform catalog, reports are archived per retention, and
the model inventory record is closed.
