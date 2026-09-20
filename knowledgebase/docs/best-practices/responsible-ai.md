---
title: Responsible AI
owner: ai-platform-architecture
status: active
reviewed: 2026-09-15
tags: [best-practice, governance, model-risk]
audience: [everyone]
---
# Responsible AI

## The commitments

- **Accountability**: every AI outcome has a named human owner. See
  [ADR-0002](../wiki/decision-records/ADR-0002-human-in-the-loop.md).
- **Fairness**: use cases that affect customers are evaluated for disparate outcomes
  across protected characteristics before release and on a schedule afterwards.
- **Transparency**: people are told when they are interacting with an AI system and
  how to reach a person.
- **Explainability**: decisions that affect a customer can be explained in terms the
  customer and the regulator understand. If the model cannot support that, the model
  does not make the decision; it informs a person who does.
- **Robustness**: evaluation, monitoring and incident response are part of the build,
  not the aftermath.

## Where a human must own the outcome

| Situation | Requirement |
| --- | --- |
| Credit, pricing or eligibility decisions | Human decision; model provides input only |
| Customer communications | Human review before send, or an approved template with evaluation |
| Complaints and disputes | Human handling; AI may draft and summarise |
| Internal productivity (summaries, drafts, code) | Author reviews and owns the output |
| Autonomous agents acting on systems | Dry-run default; live actions within an approved allow-list |

## Practical steps for a new use case

1. Write down who is affected and how they would be harmed if the system is wrong.
2. Decide the human ownership point from the table above.
3. Add fairness and refusal cases to the evaluation set.
4. Record all of the above in the use-case brief for Model Risk pre-assessment.

External reference: the NIST AI Risk Management Framework, in [Resources](../resources/README.md).
