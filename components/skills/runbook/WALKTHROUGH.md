# Walkthrough: runbook

## 1. Read the live example

`EXAMPLE.md` is the first responder's runbook: health, the gates, kill switches, rotation, degraded modes as a table with "what you do" per row including running without the service, engine selection, raising the increment, evidence.

## 2. Start from the template

```
cp components/skills/runbook/TEMPLATE.md /path/to/your-service/RUNBOOK.md
```

## 3. Fill the seven sections for the engineer at night

Health (the endpoint, what a changing chain head means, the stop-ship metric); gates (how to add a person, a team; empty refuses everyone); kill switches (scopes, the command, how fast, why clearing is reviewed); rotation (what restarts, what a rotation invalidates); degraded modes (one row per dependency plus the service itself); raising the increment; evidence commands.

## 4. Make every row a drill

Each degraded-modes row is a chaos drill on the fakes; run the drill on every release and keep the row honest.

## 5. Run every command as written

Nothing in the page may be a command that does not run. No hostname, group id or secret value; names and placeholders only.

## 6. Test it on a person

A new on-duty engineer walks one degraded-mode row from the page alone during the game day.
