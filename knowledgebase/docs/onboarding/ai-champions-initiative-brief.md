---
title: The initiative brief
owner: ai-platform-enablement
status: active
reviewed: '2026-09-20'
tags: [onboarding, paved-road, governance]
audience: [engineer, product]
---
# The initiative brief

One page per initiative, written by the champion, filed through the hub's intake so it gets a road, a risk tier and
a reviewer. It mirrors the intake brief's six sections; the answers here are the ones the intake form asks for.

## 1. The use case

- **Team and champion.**
- **The problem, in one sentence a teammate would recognise.**
- **Who feels it and how often.** People, times per week, minutes each time.
- **What "better" measures.** The outcome metric and its baseline today (or "not measured" and who will measure it).

## 2. The road and the model

- **Road.** Tools and knowledge, internal agent, retrieval service, batch with a review queue; pick one from the [paved roads](../paved-roads/README.md).
- **Model use.** What the model reads, what it produces, what it never does.
- **Increments.** Three at most, each ending in a demonstration a teammate uses.

## 3. Data and tools

- **Text the model will read** and its classification; every source is untrusted input.
- **Systems it reads from and writes to**, each with a recorded contract or a named owner who will record one.
- **The tier ceiling.** R only, W1 under confirmation, or W2 under dual control. Money is out of scope.

## 4. People

- **Owner** (the champion), **business owner**, **domain expert and hours per week**, **approvers** for W2.
- **Who confirms** each write, and who is never allowed to approve their own request.

## 5. From the collection

| Reused | Component or skill | What it saves |
| --- | --- | --- |
| | | |

| Returned | What the initiative gives back | When |
| --- | --- | --- |
| | | |

## 6. Review

- **Risk tier** proposed under [model risk](../governance/model-risk.md), and why.
- **The first demonstration**, its command and the numbers it will report.
- **What remains on an account** (identity, secrets, a webhook) and who owns each step.
- Acknowledged by the champion and the team lead.

## After filing

The enablement lead confirms the road within two working days. The champion opens the repository folder, copies
the components named in section 5, writes the first failing test, and brings the first demonstration to a deep dive
within six weeks. The `production-readiness` and `handover` skills in the collection are the pages that close it.
