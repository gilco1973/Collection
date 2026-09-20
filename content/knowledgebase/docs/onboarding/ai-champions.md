---
title: The AI champions programme
owner: ai-platform-enablement
status: active
reviewed: '2026-09-20'
tags: [onboarding, agents, paved-road]
audience: [engineer, leadership, everyone]
---
# The AI champions programme

One engineer per team, meeting every two weeks, each carrying one initiative that helps their own team and the
company, built from the [collection](../components/README.md) on a [paved road](../paved-roads/README.md), with the
result brought back as a component, a page or a demonstration everyone can reuse.

## Why

The first two internal use cases ([the knowledge base](../paved-roads/use-case-001-knowledge-base.md) and
[the first responder](../paved-roads/use-case-002-first-responder.md)) produced working controls, connectors,
documents and habits that every team building with AI needs and none should rebuild. The programme is how they
spread: not by a platform team pushing, but by one person per team pulling what their team needs and returning
what they learn.

## Who

- **A champion** is an engineer on the team, chosen by the team, with two to four hours a week for the programme. Not necessarily the most senior; the one who will actually try things and write them down.
- **The enablement lead** runs the meetings, keeps this page and the collection's contributing guide, and clears blockers with the platform and security teams.
- **Reviewers** from architecture, security and model risk attend when an initiative reaches a gate.

## The cadence

Every two weeks, forty-five minutes, always the same three parts:

1. **Ten minutes: what shipped.** Each champion in one sentence: what moved, what is blocked, what they need.
2. **Twenty minutes: one deep dive.** One champion shows a working thing (a demonstration, a component, a page), the room asks how to reuse it, and the enablement lead notes what becomes a collection entry.
3. **Fifteen minutes: the collection.** New components and pages since last time, one practice explained in five minutes, the next deep dive chosen.

Between meetings: the champions channel for questions, an office hour with the enablement lead, and the
[contributing guide](../components/README.md#contributing-one) for anything that becomes reusable.

## An initiative

One per champion at a time, written as a one-page [initiative brief](ai-champions-initiative-brief.md) and filed
through the hub's intake so it gets a road, a risk tier and a reviewer. A good first initiative:

- solves a problem the champion's own team feels this month;
- reuses at least one component and one skill from the collection;
- ends in a demonstration that runs offline with numbers, within six weeks;
- returns at least one thing to the collection: a component, a fake for a system others use, a practice page, a corpus entry, a template.

Examples of the right size: a bot that answers the team's runbook questions with citations (guard, engine, a
connector); a review agent for the team's pull requests under a W1 confirmation (the action loop, ids-only logs);
a knowledge-base section for the team's paved road, kept healthy by the librarian.

## The first meeting

1. Why we are here (five minutes): the two use cases and what they left behind.
2. The collection on the hub (ten minutes): Discover's Tools and Knowledge tabs, one listing page, the README, the tests running in a terminal.
3. Three practices in fifteen minutes: [action tiers](../best-practices/action-tiers-and-confirmation.md), [untrusted input](../best-practices/untrusted-input-and-taint.md), [demonstrations as acceptance](../best-practices/demonstrations-as-acceptance.md).
4. Picking initiatives (ten minutes): each champion names one problem; the room matches it to components.
5. Close (five minutes): the brief is due before the next meeting; the first deep dive is chosen.

## What success looks like after a quarter

Every team has a champion; every champion has filed a brief and shown one demonstration; the collection has grown
by at least one entry per team; the first initiative is in production on a paved road; the readiness and handover
pages exist for it. Numbers, not adjectives: the enablement lead keeps them on this page's companion in the hub.

## Joining

Ask your team to name you, then post in the champions channel with the problem you want to solve. Your first week:
clone the repository, run one component's tests, read one practice page, and write the first draft of your brief.
When your initiative produces a component, [onboarding components](component-onboarding.md) is its way to the shelf.
