---
title: Onboarding components and the people who sign them
owner: ai-platform-enablement
status: active
reviewed: '2026-09-20'
tags: [onboarding, governance, security, agents]
audience: [engineer, leadership]
---
# Onboarding components and the people who sign them

The [collection](../components/README.md) grows in two ways: components make their way to the shelf, and people
take on the roles that put them there. This page is the whole process for both. The hub shows the same facts live
under Build: the sign-off queue and the onboarding tracker.

## What a component is

An AI component is one of six categories. The category says who it is for and what it must contain.

- **Agent**: an AI agent, for operators. It needs a template (role, stages, tools by tier, what it never does), the tools it may call and the harness it runs inside; the agent's catalog is built from its template, so it can call exactly what the template lists.
- **Harness**: the loop an agent runs inside, for engineers building one: fixed hooks, [action tiers](../best-practices/action-tiers-and-confirmation.md), budgets, kill switches, a chained record. Any brief that names a tool carries the harness set automatically (the loop, the input guard, the cited engine, the audit chain, ids-only logging); the hub writes it in when the brief is filed and it cannot be removed.
- **Tool**: code with one clear surface and a test; an agent calls one through its harness.
- **Integration**: a client for an external system with an in-memory fake behind the same methods.
- **Pattern**: a small reference implementation of one practice, with the practice page it belongs to.
- **Skill**: a procedure anyone can follow, a person or a coding assistant, with nothing to run; the [skills catalog](../skills/README.md) lists them.

Every component, whatever its category, carries a version, two sign-offs bound to that version, a step-by-step
walkthrough and a live example.

## A component's way to the shelf

Six stages, each read from the component's manifest, never guessed. The tracker shows every component's stage and
what has to happen next.

1. **Scaffolded**: the scaffold made the directory with version 0.1.0, both sign-offs pending, a specification entry and a tag from the taxonomy.
2. **Built**: README, walkthrough, live example and tests are filled and green; the status is ready.
3. **Used once for real**: the manifest names the project it ran in; the owner records it on the sign-off form.
4. **Owner signed**: the owner signed at this version after running the tests and the example.
5. **AI security signed**: an AI security engineer signed at this version after reading the rules and the walkthrough and running the example.
6. **On the shelf**: both sign-offs name the current version; the hub lists it as generally available and this knowledge base says so on its page. A version bump returns it to stage 3.

Deprecated is past the shelf: the directory stays until consumers have moved to the replacement.

## Who signs, and what they attest

- **The owner** signs by name: the manifest names them, and the hub lets that person and no one else sign as owner.
- **An AI security engineer** signs by role: the security team lead grants the role on the platform principal, and the hub lets anyone holding it sign for AI security.
- **Both attest** on the form that the tests are green, the live example ran, the walkthrough was read end to end, and the rules and known limits were read. The server refuses a form with a box unticked; the API cannot be used to skip it.
- **The owner also names** the project of the first real use; without one the owner cannot sign.
- **A sign-off given at another version is stale**: the person read a different component, so it is skipped and asked for again.

The repository's manifest is the record and the commit is the signature. The hub records the sign-off against the
version it was given at, the queue exports the file, and the shelf tool writes it into the manifest after re-running
the tests. Nothing is signed by hand and nothing is ever invented: a pending sign-off stays pending until a named
person gives it.

## Onboarding people

### A new champion, week one

- Read [the programme](ai-champions.md) and its cadence, then this page.
- Sign in to the hub, open Discover, and run one live example from the Tools tab in a terminal.
- Start an [initiative brief](ai-champions-initiative-brief.md) for your team's first use.
- Bring one thing to the next meeting: a demonstration, a page, or a scaffolded component.

### A component owner

- Your handle is the manifest's owner field; that is what lets you sign, and the listing names you as support.
- Keep the README's known limits honest; bump the version on any change a consumer would notice.
- Use the component once for real and sign; after a version bump, the stale sign-off is yours to renew.
- Answer questions in the champions channel; hand the component over with the [handover skill](../skills/handover/SKILL.md) when you leave.

### An AI security engineer

- Ask the security team lead for the AI security role on your platform principal.
- Before the first review, read the practices the components enforce: [untrusted input and taint](../best-practices/untrusted-input-and-taint.md), [action tiers](../best-practices/action-tiers-and-confirmation.md), [fail closed and ids-only logs](../best-practices/fail-closed-and-ids-only.md).
- For each component: read the rules and the walkthrough, run the tests and the example, then sign; say in the note what you looked at hardest so the owner fixes it in the next version.
- An agent gets one more read: its template's never list against its tests, one test per line.

## What the enablement lead keeps

- The tracker's counts at each meeting: how many on the shelf, how many waiting on an owner, how many on AI security.
- The list of AI security engineers and their reviewing load; two is the minimum so no component waits on one person.
- This page, reviewed each quarter with the contributing guide it mirrors.
