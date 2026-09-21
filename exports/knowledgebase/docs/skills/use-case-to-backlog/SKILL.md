---
name: use-case-to-backlog
description: Turn a use-case specification into a Jira-ready backlog (epics, tickets, phases, critical path, CSV) from one plan file, so the plan and the backlog never drift.
title: Use case to backlog skill
owner: ai-platform-enablement
status: active
reviewed: '2026-09-20'
tags: [skill, paved-road]
audience: [engineer, product]
---
# Use case to backlog skill

## When to use
A use case has a written specification with increments and acceptance criteria, and a team needs the backlog in
Jira with owners, points, dependencies and a critical path. Also when the specification changes: edit the plan,
rebuild, re-import. Not for a backlog that lives only in Jira with no specification behind it.

## Inputs
- The specification's increments (phases), owners (role codes), epics and tickets with acceptance criteria and references. Internal tier; no customer data belongs in a ticket.
- `build_backlog.py` and a plan file in the shape of `example_plan.py` (in the collection under `components/skills/use-case-to-backlog/`).

## Steps
1. Copy `example_plan.py` next to the specification and fill `PHASES`, `OWNERS`, `EPICS` and one `t(...)` per ticket: key, type, epic, phase, weeks, owner code, points, priority, dependencies, summary, description, acceptance criteria as a list, references. Keys are placeholders (`PROJECT-n`) until the Jira project exists.
2. Every ticket names its owner role and at least one acceptance criterion that a demonstration can show.
3. Run `python3 build_backlog.py plan.py jira/`. It writes one file per epic and per ticket, `README.md` with the totals, the by-phase table, all tickets, the critical path (the longest dependency chain by points) and the owner codes, and `jira-import.csv` for Jira's importer (epics first, tickets with `Epic Link` and `Blocked by`).
4. Read the critical path. If it does not match the specification's intended order, the dependencies are wrong; fix the plan, not the output.
5. Commit the plan and the generated folder together; the specification's plan section renders from the same file.

## Tools
| Tool | Mutating | Notes |
| --- | --- | --- |
| `build_backlog.py` | Writes files under the output folder only | Re-run replaces them |
| Jira CSV import | Yes | A person imports; keys are assigned by Jira and mapped back by summary |

## Checks before finishing
- [ ] Totals in `README.md` (epics, tickets, points) match the specification's plan section.
- [ ] Every ticket has an owner, points, at least one acceptance criterion and a reference.
- [ ] The critical path ends at the last increment's demonstration ticket.
- [ ] `python3 -m unittest discover -s tests -t .` passes for the builder.

## Output format
A folder: `README.md` (index), `<KEY>-<slug>.md` per epic and ticket (a field table, description, acceptance
criteria as checkboxes, references, a footer naming the specification version), `jira-import.csv`.

## Evaluation
`tests/test_build_backlog.py`: the example plan builds ten files with the right totals, links, checkboxes, CSV rows
and critical path.
