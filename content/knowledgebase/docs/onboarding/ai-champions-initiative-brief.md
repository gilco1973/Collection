---
title: The initiative brief
owner: ai-platform-enablement
status: active
reviewed: '2026-09-20'
tags: [onboarding, paved-road, governance]
audience: [engineer, product]
---
# The initiative brief

One page per initiative, written by the champion and filed through the hub's intake. It is the platform's use-case
brief, step 1 of onboarding: the same six sections the intake form asks for, in the same order, so a champion's brief
needs no translation. A read-profile consumer on an open road registers itself from it; the platform lead confirms
only the road, within two working days. Write and money profiles need the lead's confirmation of the brief.

## 1. Use case

- **Name** and **team** (the champion's own team).
- **The problem, in a few sentences a teammate would recognise:** what happens today, who feels it, how often.
- **Road**, chosen from the consumer classes: tools and knowledge, internal agent, batch with a review queue,
  knowledge service. Customer and partner assistants are not a champion's first initiative.
- **Owner:** the champion.

## 2. People

- **Business owner** and **product owner** (they may be the same person on a small team).
- **Domain expert** and their weekly labelling allowance in hours; the evaluation suite is written with them.
- **Approvers** for any W2 action, and the rule that nobody approves their own request.

## 3. Data and tools

- **Systems of record** it reads from and writes to, each with a recorded contract or the owner who will record one.
- **Tools needed** (at most fifteen per session) and the **tier ceiling**: R only, W1 under confirmation, or W2 under
  dual control. Money is out of scope for an initiative.
- **Data classes read**, and the channel (operator for a champion's initiative).
- **From the collection:** the components and skills reused, and what the initiative returns to it.

## 4. Model

- **Model need:** what the model reads, what it produces (cited JSON, a draft, a classification), what it never does.
- **Prompts** live in the repository, loaded by version, with an evaluation suite before anything leaves the sandbox.
- **Substitute:** what happens when the model is unavailable (rules mode, a queue, a person).

## 5. Outcome

- **One outcome metric** with its unit, **today's baseline** and the date it was measured (or "not measured" and who
  will measure it), and the **target**.
- **Increments:** three at most, each ending in a demonstration a teammate uses, the first within six weeks.

## 6. Review

- **Materiality tier** proposed under [model risk](../governance/model-risk.md), and why.
- **What remains on an account** (identity, secrets, a webhook) and who owns each step.
- Acknowledged by the champion and the team lead: what happens next is registration, the bootcamp, and a build on
  the road's template with the platform's embedded engineer for the first two weeks.

## After filing

The enablement lead confirms the road within two working days. The champion opens the repository folder, copies the
components named in section 3, writes the first failing test, and brings the first demonstration to a deep dive
within six weeks. The `production-readiness` and `handover` skills in the collection are the pages that close it.
