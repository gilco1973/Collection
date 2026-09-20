---
title: Reusable components
owner: ai-platform-engineering
status: active
reviewed: '2026-09-20'
tags: [paved-road, agents]
audience: [engineer]
---
# Reusable components

Self-contained pieces of code an engineer copies into a project and uses the same day: tools, integrations and
patterns lifted from products that run in production, each with a README that gets someone running in five minutes,
a manifest and tests. They live in the repository under `components/`; the shelf tool publishes their READMEs here
and lists them on the hub's Discover page. Skills are in the [agent skills catalog](../skills/README.md).

| Component | Kind | Language | What it is |
| --- | --- | --- | --- |
## Agents

For operators, from the hub or a channel; engineers deploy one. Each one has a template (TEMPLATE.md: role, stages, what it may propose, what it never does), the tools it may call and the harness it runs inside, declared in `agent`.

| Component | Language | What it is |
| --- | --- | --- |
| [Incident first read agent](incident-first-read-agent.md) | python | An agent, complete: a template (role, stages, tools by tier, never list), tools reached only through the harness, a cited first read, one W1 proposal to confirm |

## Harnesses

For engineers building an agent. Each one has the loop an agent runs inside: fixed hooks, action tiers, budgets, kill switches, a chained record.

| Component | Language | What it is |
| --- | --- | --- |
| [Governed action loop](governed-action-loop.md) | python | The action loop an agent runs inside: three fixed hooks, W1 confirmed once, W2 under dual control, taint ceiling, kill switches, budgets, a chained record |
| [Mcp tool server](mcp-tool-server.md) | python | An MCP server in front of the action loop: tools/list from the signed catalog with annotations, every call through the hooks, W1 as elicitation, taint as 403 |

## Tools

For engineers; an agent calls one through its harness. Each one has code with one clear surface and a test that proves it.

| Component | Language | What it is |
| --- | --- | --- |
| [Audit chain](audit-chain.md) | python | A hash-chained, append-only record in SQLite: every event carries prev and hash; verify() walks it, export() hands reviewers JSON lines with the head |
| [Comm templates](comm-templates.md) | python | Stakeholder and customer messages as owned, versioned templates the model fills through named fields only; unknown or missing fields refused; a registry hash |
| [Ids-only logging](ids-only-logging.md) | python | A JSON logger that lets only identifiers through: long strings withheld, secrets and emails masked, so no upstream text ever lands in a log line |
| [RS256 jwt verify](rs256-jwt-verify.md) | python | RS256 JWT verification with the standard library against a JWKS: signature, exp, nbf, iss, aud checked, algorithm pinned (no none, no HMAC confusion) |
| [Secrets by name](secrets-by-name.md) | python | Handlers never hold a credential: a named secret fetched at call time from a vault, a file or the environment, plus the redeemed-reference check |
| [Shelf mcp server](shelf-mcp-server.md) | python | A read-only MCP server over the shelf: list, get, search and stage tools and every README, walkthrough and template as resources, for a coding assistant |
| [Stdlib http client](stdlib-http-client.md) | python | One urllib HTTP client for every upstream: timeouts, bounded retries with backoff, a size ceiling, credential-free errors, a recording transport |
| [Typed API client](typed-api-client.md) | typescript | One browser HTTP client: bearer, request id, traceparent, idempotency key, If-Match, problem+json to typed errors, one retry on idempotent calls; a mock server |
| [Untrusted input guard](untrusted-input-guard.md) | python | Text a model reads is evidence, not instruction: tagged sources, injection score, taint, PII masking, fenced context, cite-or-drop claims, a corpus |

## Integrations

For engineers connecting a system. Each one has a client for an external system and an in-memory fake behind the same methods.

| Component | Language | What it is |
| --- | --- | --- |
| [AWS sigv4](aws-sigv4.md) | python | AWS SigV4 with hmac and hashlib only: task-role credentials, signed JSON-protocol calls to Secrets Manager, CloudWatch, ECS and Bedrock |
| [Bedrock converse adapter](bedrock-converse-adapter.md) | python | Claude on Bedrock Converse behind the model gateway's complete() signature: SigV4 from the task role, inference profile as modelId, usage returned |
| [Mcp gateway client](mcp-gateway-client.md) | python | The harness's gateway for an external MCP server: a recorded contract, an allowlist pinned to descriptions, quarantine on drift, credentials by name; a fake |
| [OIDC pkce auth](oidc-pkce-auth.md) | typescript | Authorization Code + PKCE in the browser with tokens in memory, a persona client for dev, the principal from GET /me as the authority, a closed permits set |
| [Teams graph connector](teams-graph-connector.md) | python | Microsoft Teams through Graph and the Bot connector: group gates, channels, posts, cards, pins, subscriptions, 4,000-char chunking, and an in-memory fake |

## Patterns

For engineers adopting a practice. Each one has a small reference implementation of one practice, with the practice page it belongs to.

| Component | Language | What it is |
| --- | --- | --- |
| [Cited llm engine](cited-llm-engine.md) | python | The think step behind one adapter: rules offline, a model online; fenced context in, strict cited JSON out, malformed refused, proposals refused on taint |
| [Fail closed config](fail-closed-config.md) | python | Settings from the environment that refuse to start a live process with a missing gate, a memory store or an http URL; problems named, no value printed |
| [Prompt pills onboarding](prompt-pills-onboarding.md) | python | Explain a bot inside the room: a how-to card with clickable starter prompts filtered by role and increment, a first-time hint, a five-step guide page |

## Using one

1. Read its page here or the README in the repository.
2. Copy the directory into your project (Python components are standard library only unless the page says otherwise).
3. Run its tests with the one command the page names.
4. Wire the transport, secrets provider or connection it names; nothing else changes.

## Contributing one

The contract is `CONTRIBUTING.md` in the repository: one directory, a manifest, a five-minute README, tests behind
one command, no hidden dependency, no secret. Open a pull request; the shelf tool checks the rest.
