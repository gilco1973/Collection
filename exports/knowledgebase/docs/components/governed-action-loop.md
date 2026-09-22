---
title: "Governed action loop"
owner: ai-platform-engineering
status: active
reviewed: '2026-09-19'
tags: [agents, security, governance]
audience: [engineer]
---
# governed-action-loop

> A component of the collection: `components/python/governed-action-loop/` in the repository (category harness, python, status ready). Copy it from there; this page is its README, published by the shelf tool. It is an interim implementation of the platform design specification §5.1, §5.2, §5.5, §6, §4.12, §4.15, §4.8 (PLT-AC-8, PLT-AC-11, PLT-AC-12, PLT-AC-16, PLT-AC-17, PLT-AC-19, PLT-AC-24, PLT-AC-29, PLT-AC-30, PLT-AUD-12, PLT-POL-3, PLT-CAT-5, PLT-CAT-6, PLT-HAR-11, PLT-HDL-1, PLT-PRM-1, PLT-PRM-3); the replacement test is under Known limits. Version 1.1.2; sign-off: owner pending; AI security pending; walkthrough `WALKTHROUGH.md`; live example `example.py`.


The action loop an agent runs inside: admit a person, act through three fixed hooks, park a write until the person
confirms it once, refuse a mitigation without a second person, cap a session that saw an injected instruction to
reads, stop within one call on a kill switch, spend against a budget, and record every step on a hash chain.

## What it is for

You are giving a model tools that write to real systems (tickets, pages, pipelines, money) and you need the
controls to be structural rather than a prompt's good intentions. This package is the Meg core: the part of the first
responder that decides whether a call happens at all, and proves afterwards what happened. It is standard library
only and runs offline against fakes, so a team can adopt the loop before any account exists.

## Five-minute start

```
cd components/python/governed-action-loop
python3 example.py                                  # one agent: read, W1 parked, confirmed once, W2 refused, chain verified
python3 -m unittest discover -s tests -t . -v       # the invariants, one test each
```

`example.py` is the whole wiring for a consumer: three tools by tier, four rules, two handlers, the result shapes.
Copy it and replace the fakes with your clients.

## What is inside

| File | What it is |
| --- | --- |
| `actionloop/harness.py` | `Harness`: `admit`, `call` (the three private hooks: catalog lookup, argument validation, rule decision before; data guard after; record always), `confirm`, `taint`, `end`, `resume`; `Budget`, `Session`, `Stop` with its typed reasons |
| `actionloop/policy.py` | The rule bundle: permit or forbid, a principal match, an action match by name or tier, `when` conditions over the call's environment; forbid overrides permit; default deny; `structural_checks` no bundle can waive (ladder ceiling, taint ceiling, W1 needs a confirmation, W2 an approval); the `DisagreementCounter` |
| `actionloop/catalog.py` | `ToolDecl` and `build` (tier, contract operation, permission, argument schema, reversible, idempotent); the fixtures the build refuses (unbacked claim, irreversible W1, restricted argument, no-entry handler); signing with two approvers |
| `actionloop/gateway.py` | The connector boundary: evaluates the same bundle a second time, redeems the per-call reference, then runs the handler; a target holds no credential |
| `actionloop/identity.py` | Tenant, human and agent as one principal chain; the fake IdP for tests; outbound *references* bound to audience, run and deadline that a handler redeems, never a token it holds |
| `actionloop/dataguard.py` | Projection to the declared result shape, PII masking per audience (model, log, human), the injection score, provenance-tagged segments and fencing for a brief |
| `actionloop/audit.py` | The hash-chained record (vendored from `audit-chain`) |
| `actionloop/kill.py` | Kill switches by run, board and consumer, with a quorum, read at admit and before every call |
| `actionloop/telemetry.py` | Spend per consumer, board, ticket and phase; "not measured" is a state, never zero |
| `actionloop/modelgw.py` | The one door to a model: inference profile per consumer, allowlist, prompt by reference with its hash, per-turn token budget, the model context stamped on every call; `FakeModel` for offline runs |
| `actionloop/signing.py` | Canonical JSON, sha256, two-approver HMAC signing (replace the key with a KMS signer in production) |
| `example.py` | A complete consumer, runnable |
| `tests/test_loop.py` | The invariants below, one test each |

## How to reuse it

Copy the `actionloop/` directory into your service and write your own `example.py`:

1. Declare tools with `ToolDecl` (name them `target___tool`), build and sign the catalog. Every tool binds to a recorded contract operation; a W1 tool must be reversible.
2. Write the bundle: who may read, who may confirm a W1, who may approve a W2 (never the requester).
3. Register handlers on the gateway per target. A handler receives `(args, credential)` where the credential is a redeemed reference; it fetches its own secret by name at call time (`secrets-by-name`).
4. Declare a result shape per tool: which fields reach the model, and which are identifiers kept verbatim.
5. Admit a session with a token from your IdP (`identity.resolve`; pair with `rs256-jwt-verify` for real tokens), call tools, handle `Stop`, render `session.pending` as the confirmation card, call `confirm` with the hash the person saw.

The model never calls `Harness.call` directly. Your think step (see `cited-llm-engine`) proposes; your command layer
turns proposals into calls; the loop decides.

## Production adapters

The fakes have production counterparts behind the same two methods, so the loop does not change between the
sandbox and the bank: `identity.JwksIdP` verifies the bank's RS256 tokens against its JWKS and maps directory groups
to roles (`roles_map`); `signing.KmsKey` signs and verifies catalogs and bundles on an asymmetric KMS key through the
`aws-sigv4` component's `AwsJson` (the private key never leaves KMS); `signing.FakeKms` stands in for tests.
`tests/test_production_adapters.py` proves both against a generated key and the fake.

## Rules it enforces

- Three hooks in a fixed order on every call; a consumer cannot add a fourth or reach a handler around them.
- Default deny; a forbid beats any permit; every decision names the policies and a typed deny code.
- A W1 call parks with a hash of tool and arguments; only the acting person confirms; the confirmation is consumed once.
- A W2 or MONEY call needs an approval reference; the bundle decides who may approve (the example: not the requester).
- A tainted session is capped at reads (ladder L1) whatever its bundle says.
- A kill switch at any scope lands at the next hook and refuses admission.
- Budgets (tokens, tool calls, time) stop with a typed reason; a handler failure is `handler.errors`, never a raw exception.
- Every call and decision is on the chain; the intent of a W call is recorded before dispatch.
- A session resumes only for the person it was admitted for and only under the same catalog hash.
- An unsigned or tampered catalog never loads.

## Where it came from

Meg, the first responder (`meg/crai`, standalone edition, snapshot 2026-09-19), where it runs under 400 tests and
the replay, live-week, game-day, corpus and chaos demonstrations. Extracted as is, with the incident-specific stages
removed from the fake model, the spec cross-references dropped from docstrings, and neutral names in the examples.
`audit.py` is vendored from `audit-chain` so that component can be taken alone.

## Known limits

SQLite for sessions and the record (swap the connection for Postgres behind the same statements). HMAC signing with
a local key until a KMS signer exists. The injection score is a marker heuristic: the taint ceiling is the control,
the score is the floor. The gateway is in-process; a real gateway replaces `FakeGateway` behind `tools_call`.

**Replacement test** (the platform specification's §14.3 rule for an interim): The consumer restarts unchanged when the in-process gateway is AgentCore Gateway with the same bundle in AgentCore Policy, the local HMAC key is KMS signing, and the SQLite stores are the control layer's; the conformance test on the three hooks passes on both.
