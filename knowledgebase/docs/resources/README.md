---
title: Resources
owner: ai-platform-enablement
status: active
reviewed: 2026-09-15
tags: [onboarding]
audience: [everyone]
---
# Resources

Curated external references. Each entry in [catalog.yaml](catalog.yaml) has an owner and
a review date; the librarian's `catalogs` check validates the entries and, with
`--network`, probes the links.

## Start here

- **Model provider documentation** — the Claude developer platform docs at
  <https://platform.claude.com> and the Agent SDK docs at
  <https://code.claude.com/docs/en/agent-sdk>. Primary source for API behaviour.
- **Building effective agents** — the provider's guidance on when an agent is warranted
  and how to keep it simple; the basis of our [agent design](../best-practices/agent-design.md) test.
- **NIST AI Risk Management Framework** — <https://www.nist.gov/itl/ai-risk-management-framework>.
  The vocabulary our [responsible AI](../best-practices/responsible-ai.md) page uses.
- **OWASP Top 10 for LLM Applications** —
  <https://owasp.org/www-project-top-10-for-large-language-model-applications/>.
  The threat list behind our [security](../best-practices/security.md) controls.
- **Supervisory guidance on model risk management (SR 11-7)** —
  <https://www.federalreserve.gov/supervisionreg/srletters/sr1107.htm>. The regulatory
  expectation our [model lifecycle](../paved-roads/model-lifecycle.md) satisfies.

## Adding a resource

Add an entry to `catalog.yaml` with `title`, `url`, `why` (one sentence on why it
matters here), `owner`, `reviewed`. External hosts should be in `links.trusted_hosts`
in `kb.config.yaml` or the librarian will mark the link as unverified.
