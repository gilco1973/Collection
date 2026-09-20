# runbook

The runbook for the engineer on duty for the service itself, at night, without the code: health, gates, kill switches, rotation, degraded modes as a table, raising the increment, evidence.

## Five-minute start

```
cd components/skills/runbook
cp TEMPLATE.md ../../../myservice/RUNBOOK.md
```

Read `SKILL.md` for the procedure; it is the same page the knowledge base publishes in its skills catalog.

## What is inside

| File | What it is |
| --- | --- |
| `SKILL.md` | The procedure and the checks |
| `TEMPLATE.md` | The seven sections with the degraded-modes table |

## How to reuse it

Copy the directory, or just `SKILL.md` and the template, into your project. Nothing here depends on the rest of the
collection.

## Where it came from

The first responder's runbook, rehearsed by its chaos drill on every release.
