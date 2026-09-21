---
name: security-notes
description: Write the SECURITY.md for an AI service as a threat-model delta table (threat, control, where in the code), a data-classes table, the injection corpus and the known limits.
title: Security notes skill
owner: ai-platform-architecture
status: active
reviewed: '2026-09-20'
tags: [skill, security]
audience: [engineer, risk]
---
# Security notes skill

## When to use
Before the first deployment of a service that gives a model tools, and again whenever its inputs widen (a new
source of text the model reads) or its outputs widen (a new write tool, a new audience). The document is what
Security signs; write it so a reviewer can verify each row against the code.

## Inputs
- The service's tool catalog by tier, its rule bundle, the connectors and their credentials, the text sources the model reads, the audiences it writes to. Internal tier.
- `TEMPLATE.md` in `components/skills/security-notes/`.

## Steps
1. **Threat model delta.** State what changes against the previous state in two sentences: which inputs are now untrusted, which egress paths exist. Then one row per threat: the threat in plain words, the control that stops it, and the file or function where the control lives. A control without a location is not a control.
2. Cover at least: instruction injection through each text source; a confirmation replayed or clicked by someone else; self-approval of a mitigation; a person outside the gate; an unauthenticated request; a credential held by a target; free text toward a customer; PII reaching the model or a room; a resumed session under another person; a restart losing state; malformed model output; the model attempting an action; budget exhaustion.
3. **Data classes.** One row per class of data the service touches (metadata, free text, customer data, credentials, the record) with examples and how each is handled (recorded, masked, never logged, by name only).
4. **The corpus.** Name the command that runs the injection corpus in CI, the number of classes, the acceptance criterion (zero unauthorized actions per release), and where new patterns get added.
5. **Known limits.** What is a heuristic, what is interim (a local signing key before the key service), what waits on a decision.

## Tools
| Tool | Mutating | Notes |
| --- | --- | --- |
| Reading the code | No | Every "where" cell must point at real code |
| The corpus command | No | Run it and paste the counts |

## Checks before finishing
- [ ] Every threat row names a file or function that exists.
- [ ] The corpus command runs green and the counts in the document match its output.
- [ ] No secret, hostname or real identifier appears anywhere in the document.
- [ ] Known limits say who decides what remains open.

## Output format
`SECURITY.md` with the four sections in this order: threat model delta, data classes, the corpus, known limits.

## Evaluation
Reviewed by Security against the code; the row count and the corpus counts are the objective checks.
