---
name: production-readiness
description: Write the production-readiness page for an AI service as one table (area, status, evidence, open item with owner) so what is done, what is proven and what waits on an account are never confused.
title: Production readiness skill
owner: ai-platform-engineering
status: active
reviewed: '2026-09-20'
tags: [skill, governance]
audience: [engineer, leadership]
---
# Production readiness skill

## When to use
When a service is about to leave the sandbox, and at every increment after. The page is the honest state: DONE
with evidence, WRITTEN (exists, not yet applied), or OPEN with a named owner. It replaces the status meeting.

## Inputs
- The test suite, the demonstrations, the corpus and drill outputs, the deployment descriptors, the CI runs.
- `TEMPLATE.md` in `components/skills/production-readiness/`.

## Steps
1. One row per area: functional per increment, security, identity, credentials, data, record, metrics,
   resilience, delivery, packaging, deployment, CI, model risk, and anything the service adds.
2. **Status** is one of DONE, WRITTEN, OPEN. DONE means tested and repeatable here; WRITTEN means the artefact exists
   and has not been applied on an account; OPEN means an account-bound step remains.
3. **Evidence** names the test, the command and the numbers from its last run. Paste numbers, never adjectives.
4. **Open item** names the step and its owner (a role or a person), never "TBD".
5. Close with a paragraph on what "production ready" means here: everything without an account is done, and each
   OPEN item is a step with an owner, not a design gap. Say which increment ships first and how later ones are gated.

## Tools
| Tool | Mutating | Notes |
| --- | --- | --- |
| The test and demonstration commands | No | Run them; paste the counts |

## Checks before finishing
- [ ] Every DONE row has evidence with a number or a named test.
- [ ] Every OPEN row has an owner.
- [ ] The date and branch at the top are today's.
- [ ] Nothing in the page requires a reader to trust the author.

## Output format
`PRODUCTION-READINESS.md`: a dated header, the table, the closing paragraph.

## Evaluation
The next reviewer runs one evidence command at random; if the number differs, the page is stale.
