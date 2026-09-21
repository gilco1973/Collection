---
name: handover
description: Write the handover document for a delivery so the next person can run, verify and continue it; what it is, what changed since the last handover, tickets completed with what remains on the company's accounts, decisions, layout, what it does not do, next steps.
title: Handover skill
owner: ai-platform-enablement
status: active
reviewed: '2026-09-20'
tags: [skill, governance]
audience: [engineer, leadership]
---
# Handover skill

## When to use
At the end of every delivery and at every increment, before the package leaves the author's hands. Also when the
author changes. A handover is versioned; a new version adds a row to the history table, never rewrites history.

## Inputs
- The test and demonstration outputs from the machine the handover is written on, with numbers.
- The backlog (ticket keys) and the specification version.
- `TEMPLATE.md` in `components/skills/handover/`.

## Steps
1. **Header.** Date, author, branch, folder, the specification version it was built to, what it depends on.
2. **What this is.** One paragraph a newcomer can read first, then the commands that run it and the numbers from the last run on this machine.
3. **Since the last handover.** A table: change, where, commit.
4. **Tickets completed, in the self-contained sense.** One table per epic: ticket, done here (the code and tests that exist), remains on the company's account (the step that closes the ticket). "Done here" never claims an account-bound step.
5. **Decisions taken while building.** Each with its reversal path, so the next revision of the specification can accept or undo it.
6. **Layout.** The folder tree with one line per directory.
7. **What it does not do.** Honest and specific: what was never exercised, what is a heuristic, what was verified by proxy.
8. **Next steps.** The first ticket to pick up and the path to staging.

## Tools
| Tool | Mutating | Notes |
| --- | --- | --- |
| The test and demonstration commands | No | Numbers come from a run, not from memory |
| The package script | Writes the zip | Refuses a dirty tree or an unlisted version |

## Checks before finishing
- [ ] Every number in the page comes from a run on this machine today.
- [ ] Every ticket row names what remains, or says nothing remains.
- [ ] The document stays under 200 lines; detail links out.
- [ ] The version appears in the history table and in the package name.

## Output format
`HANDOVER.md` with the eight sections; a versioned package built from the tracked files plus this document.

## Evaluation
The next person runs the commands in "What this is" and gets the same numbers.
