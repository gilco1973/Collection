# security-notes

How to write the SECURITY.md a reviewer can verify against the code: a threat-model delta table (threat, control, where), data classes, the injection corpus and known limits.

## Five-minute start

```
cd components/skills/security-notes
cp TEMPLATE.md ../../../myservice/SECURITY.md   # then follow SKILL.md
```

Read `SKILL.md` for the procedure; it is the same page the knowledge base publishes in its skills catalog.

## What is inside

| File | What it is |
| --- | --- |
| `SKILL.md` | The procedure and the checks |
| `TEMPLATE.md` | The four sections with the rows every tool-using AI service needs |

## How to reuse it

Copy the directory, or just `SKILL.md` and the template, into your project. Nothing here depends on the rest of the
collection.

## Where it came from

The first responder's SECURITY.md, which Security reviews row by row.

## Known limits

**Replacement test** (the platform specification's §14.3 rule for an interim): The threat-model delta is the review record Security signs at step 5 of onboarding; the template stays.
