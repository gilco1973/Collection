---
title: FAQ
owner: ai-platform-enablement
status: active
reviewed: 2026-09-15
tags: [faq, onboarding]
audience: [new-hire, everyone]
---
# FAQ

Questions new joiners asked in their first month, answered by the page owners. Add
yours through the [review process](../governance/review-process.md).

## Access and tooling

**Can I get a vendor API key for local testing?**
No. Development-tier gateway keys are issued instead; they work with the internal SDK
and every tutorial. See [LLM gateway](../paved-roads/llm-gateway.md).

**Can I use a consumer AI chat tool for work?**
Only with Public-tier content, and never for code or documents from our systems. Use the
internal assistant. See [data classification](../best-practices/data-classification.md).

## Building

**Do I need Model Risk approval for an internal prototype?**
A pre-assessment, yes; it takes a day and sets the tier. Prototypes on Internal data at
tier 3 need only the brief. See [model lifecycle](../paved-roads/model-lifecycle.md).

**The paved roads do not fit my use case. What now?**
Write a decision record proposing the deviation and request an architecture review before
writing code. See [decision records](decision-records/README.md).

**When is an agent the right choice?**
Rarely for a first project. Apply the four-question test in [agent design](../best-practices/agent-design.md).

## Evaluations

**How big must my evaluation set be?**
50 for a prototype, 100 for internal release, 300 for customer-facing. See [evaluation pipeline](../paved-roads/evaluation-pipeline.md).

**Can a model grade my evaluation?**
Yes, with a rubric, and only after the grader is checked against a human-labelled sample.

## This knowledge base

**A page is wrong or out of date. What do I do?**
Propose a change, or if you are not sure of the fix, open a Jira issue in `AIKB` with the
page path. The librarian also flags stale pages to their owners automatically.

**Why does the librarian keep flagging my page?**
Because its `reviewed` date is older than the section's review window. Review it and
bump the date; only an owner may do that. See [review process](../governance/review-process.md).
