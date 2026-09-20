# handover

The versioned handover document that lets the next person run, verify and continue a delivery: what it is with the commands and last numbers, what changed, tickets done here versus what remains on the company's account, decisions with their reversal, layout, limits, next steps.

## Five-minute start

```
cd components/skills/handover
cp TEMPLATE.md ../../../myservice/HANDOVER.md
```

Read `SKILL.md` for the procedure; it is the same page the knowledge base publishes in its skills catalog.

## What is inside

| File | What it is |
| --- | --- |
| `SKILL.md` | The procedure and the checks |
| `TEMPLATE.md` | The eight sections and the history table |

## How to reuse it

Copy the directory, or just `SKILL.md` and the template, into your project. Nothing here depends on the rest of the
collection.

## Where it came from

The first responder's handovers (three versions) and the knowledge base's (five versions).

## Known limits

**Replacement test** (the platform specification's §14.3 rule for an interim): Material changes re-enter onboarding step 4 (PLT-ONB-6); the handover names the step per ticket.
