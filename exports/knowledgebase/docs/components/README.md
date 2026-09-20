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
a manifest and tests. They live in the repository under `components/`; the catalog tool publishes their READMEs here
and lists them on the hub's Discover page. Skills are in the [agent skills catalog](../skills/README.md).

| Component | Kind | Language | What it is |
| --- | --- | --- | --- |
| [Audit chain](audit-chain.md) | tool | python | A hash-chained, append-only record in SQLite: every event carries prev and hash; verify() walks it, export() hands reviewers JSON lines with the head |
| [Comm templates](comm-templates.md) | tool | python | Stakeholder and customer messages as owned, versioned templates the model fills through named fields only; unknown or missing fields refused; a registry hash |
| [Governed action loop](governed-action-loop.md) | tool | python | The action loop an agent runs inside: three fixed hooks, W1 confirmed once, W2 under dual control, taint ceiling, kill switches, budgets, a chained record |
| [Ids-only logging](ids-only-logging.md) | tool | python | A JSON logger that lets only identifiers through: long strings withheld, secrets and emails masked, so no upstream text ever lands in a log line |
| [RS256 jwt verify](rs256-jwt-verify.md) | tool | python | RS256 JWT verification with the standard library against a JWKS: signature, exp, nbf, iss, aud checked, algorithm pinned (no none, no HMAC confusion) |
| [Secrets by name](secrets-by-name.md) | tool | python | Handlers never hold a credential: a named secret fetched at call time from a vault, a file or the environment, plus the redeemed-reference check |
| [Stdlib http client](stdlib-http-client.md) | tool | python | One urllib HTTP client for every upstream: timeouts, bounded retries with backoff, a size ceiling, credential-free errors, a recording transport |
| [Typed API client](typed-api-client.md) | tool | typescript | One browser HTTP client: bearer, request id, traceparent, idempotency key, If-Match, problem+json to typed errors, one retry on idempotent calls; a mock server |
| [Untrusted input guard](untrusted-input-guard.md) | tool | python | Text a model reads is evidence, not instruction: tagged sources, injection score, taint, PII masking, fenced context, cite-or-drop claims, a corpus |
| [AWS sigv4](aws-sigv4.md) | integration | python | AWS SigV4 with hmac and hashlib only: task-role credentials, signed JSON-protocol calls to Secrets Manager, CloudWatch, ECS and Bedrock |
| [Bedrock converse adapter](bedrock-converse-adapter.md) | integration | python | Claude on Bedrock Converse behind the model gateway's complete() signature: SigV4 from the task role, inference profile as modelId, usage returned |
| [OIDC pkce auth](oidc-pkce-auth.md) | integration | typescript | Authorization Code + PKCE in the browser with tokens in memory, a persona client for dev, the principal from GET /me as the authority, a closed permits set |
| [Teams graph connector](teams-graph-connector.md) | integration | python | Microsoft Teams through Graph and the Bot connector: group gates, channels, posts, cards, pins, subscriptions, 4,000-char chunking, and an in-memory fake |
| [Cited llm engine](cited-llm-engine.md) | pattern | python | The think step behind one adapter: rules offline, a model online; fenced context in, strict cited JSON out, malformed refused, proposals refused on taint |
| [Fail closed config](fail-closed-config.md) | pattern | python | Settings from the environment that refuse to start a live process with a missing gate, a memory store or an http URL; problems named, no value printed |
| [Prompt pills onboarding](prompt-pills-onboarding.md) | pattern | python | Explain a bot inside the room: a how-to card with clickable starter prompts filtered by role and increment, a first-time hint, a five-step guide page |

## Using one

1. Read its page here or the README in the repository.
2. Copy the directory into your project (Python components are standard library only unless the page says otherwise).
3. Run its tests with the one command the page names.
4. Wire the transport, secrets provider or connection it names; nothing else changes.

## Contributing one

The contract is `CONTRIBUTING.md` in the repository: one directory, a manifest, a five-minute README, tests behind
one command, no hidden dependency, no secret. Open a pull request; the catalog tool checks the rest.
