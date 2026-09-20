---
title: Demonstrations as acceptance
owner: ai-platform-enablement
status: active
reviewed: '2026-09-20'
tags: [best-practice, evaluation, governance]
audience: [engineer, product, leadership]
---
# Demonstrations as acceptance

## The rule in one line

Every increment ends in something a user does for real, and the demonstration is a command that runs offline
against fakes and writes a report with numbers. Acceptance is the report, not a meeting.

## The five demonstrations of an agent that acts

| Demonstration | What it shows | The numbers |
| --- | --- | --- |
| Replay | Past cases replayed through the agent: the context assembled, the first read cited | time to context per case, all under the target; every claim cited; unauthorized actions 0 |
| Live week | A week of real use with actions under confirmation | acknowledged once, replay refused; time to first update; confirmations per case |
| Game day | A seeded fault mitigated under dual control | self-approval refused; owner approval; executed once; verified; postmortem within the hour |
| Corpus | Instruction-bearing inputs by class | every class taints; every proposal refused; unauthorized actions 0 |
| Chaos | Each dependency lost mid-turn | the record intact every time; typed stops; the work continues by hand |

Each is a subcommand of the service (`replay 10`, `liveweek`, `gameday`, `corpus`, `chaos`) so CI runs them on
every change and a reviewer runs them on a laptop. The fakes behind the connectors make this possible; the live
clients follow the same method surface and are exercised on the account later.

## What a good demonstration looks like

- It is seeded and deterministic: the same command gives the same numbers.
- It exits non-zero on the criterion it exists for (the corpus on any unauthorized action).
- Its report is JSON a page can render and a person can diff between releases.
- It names what it does not show (no real traffic, a marker heuristic, a container verified by proxy).

## The account-bound half

A demonstration on fakes proves the code. The ticket closes when the same demonstration runs on the account: the
real replay scored by the users, the real week, the game day on staging. The handover names that step per ticket so
"done here" and "done" are never confused.

## Where it is implemented

The five subcommands in the first responder ([use case 002](../paved-roads/use-case-002-first-responder.md)); the
`production-readiness` and `handover` skills in the collection are the pages that carry the numbers.
