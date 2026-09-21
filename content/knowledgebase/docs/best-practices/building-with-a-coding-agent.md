---
title: Building with a coding agent
owner: ai-platform-enablement
status: active
reviewed: '2026-09-20'
tags: [best-practice, agents, governance]
audience: [engineer, leadership]
---
# Building with a coding agent

How the knowledge base, the first responder and the collection itself were built: a person and a coding agent, with
the controls in the process rather than in the person's attention.

## The shape of a delivery

1. **A use case first.** A written specification with increments, acceptance criteria and open questions, rendered from source; the backlog builds from the same plan file (the `use-case-to-backlog` skill).
2. **A plan pull request before code.** The plan is docs only, names its hard constraints ("preserved, never weakened") and the questions only the owner can answer, and is reviewed as a pull request. Code follows in increment pull requests, each with its own acceptance criteria and tests.
3. **Tests seen failing first.** Every behaviour ships with a test that failed before the change and a note of which.
4. **Demonstrations, not demos.** Each increment ends in a command that writes a report with numbers ([demonstrations as acceptance](demonstrations-as-acceptance.md)).
5. **A pre-ship verdict.** Before merge, a second agent (or a review panel of several lenses: security, backend, product, adversarial) judges the change against the plan and the acceptance criteria and ranks the gaps. Gaps resolved on merge are named in the merge; the rest become follow-ups with owners.
6. **A versioned handover.** Every delivery ends in a handover document and package (the `handover` skill), so the next person can run, verify and continue without the author.

## Rules for the agent

- The repository's agent instructions file is the contract: layout, gates, what never changes, what to run before "done".
- Files stay short (the knowledge base enforces 200 lines); one concern per module.
- No secret, real id, hostname or customer data in the repository; placeholders look like placeholders.
- The agent never weakens a gate to get past a missing account; a missing account is escalated by name.
- Numbers in documents come from a run on this machine today, never from memory.

## Rules for the person

- Answer the plan's open questions; they are the decisions the agent must not make.
- Read the verdict, not the diff, first; then the diff where the verdict points.
- Keep the increments small enough that a demonstration fits in a day.
- When the agent says "done here, remains on the account", believe both halves.

## Related

[Agent design](agent-design.md), [prompt engineering](prompt-engineering.md), the
[review process](../governance/review-process.md), and the AI champions programme in
[onboarding](../onboarding/ai-champions.md).
