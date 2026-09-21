---
title: "Jira connector"
owner: ai-platform-engineering
status: active
reviewed: '2026-09-19'
tags: [atlassian, agents, security]
audience: [engineer]
---
# jira-connector

> A component of the collection: `components/python/jira-connector/` in the repository (category integration, python, status ready). Copy it from there; this page is its README, published by the shelf tool. It is an interim implementation of the platform design specification §4.12, §4.1, §5.2 (PLT-CAT-6, PLT-ID-6, PLT-AC-16); the replacement test is under Known limits. Version 1.0.1; sign-off: owner pending; AI security pending; walkthrough `WALKTHROUGH.md`; live example `example.py`.


Jira as a harness target: read, search, comment, create; a fake behind the same methods; the token a name;
handlers refuse to run without a redeemed reference.

## What it is for

An agent that reads incidents and posts its first read needs Jira, and it must reach it the way the loop
reaches every system: through a gateway target whose handlers run only with a reference the harness minted for
that call, with a credential nobody holds. This is that target for Jira Cloud (email and API token) and Jira
Data Center (a personal access token), plus an in-memory fake with the same methods so every test, demonstration
and sandbox runs without an account.

## Five-minute start

```
cd components/python/jira-connector
python3 example.py
python3 -m unittest discover -s tests -t .
```

The example reads and comments through the fake with a redeemed reference, shows a handler refusing a reference
for another audience, then drives the real client against a recording HTTP double: the URL, the auth scheme, the
person named in the write, and no token in any URL.

## What is inside

| File | What it is |
| --- | --- |
| `jira.py` | `JiraClient` (`get_issue`, `search`, `add_comment`, `create_issue`), `FakeJira`, `handlers(client, audience)` for the harness gateway, `require_credential` |
| `example.py` | The fake and the real client against a recording double |
| `tests/test_jira.py` | Auth schemes and shapes, writes carrying the acting person, handlers gated by audience, the fake's outage switch |

## How to reuse it

Copy `jira.py`. Build the client with your HTTP (`stdlib-http-client`'s `Http`, or anything with
`json(method, url, headers, payload=None) -> dict`), your secrets provider (`secrets-by-name`), the base URL and
the token's name. Register `handlers(client, "tickets")` as the gateway target the agent's template names:
`tickets.get` is R, `tickets.comment` and `tickets.create` are W1. The service account needs read on the incident
projects and comment on them; nothing more.

## Rules it enforces

- No handler runs without a redeemed reference for its own audience; the acting person comes from the reference, never from an argument.
- The token is a name resolved at call time; it appears in an Authorization header and nowhere else.
- Every write carries the acting person's name in Jira's own record.

## Where it came from

`meg-first-responder`, `meg/responder/clients/change.py` (`JiraClient`, `FakeChange`), snapshot 2026-09-19.
Extraction: reads added (`get_issue`, `search`) since the first responder only created issues; the fake got an
outage switch; Data Center bearer auth added.

## Known limits

Jira's REST API v2; ADF bodies (v3) are not produced. Search returns the first page only.

**Replacement test:** the same operations are a recorded contract in the registry with generated clients
behind a Gateway target; the handlers here bind to the same contract operations, and the harness's conformance
tests through the target pass on both.
