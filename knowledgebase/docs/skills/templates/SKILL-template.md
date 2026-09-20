---
title: Skill template
owner: ai-platform-enablement
status: active
reviewed: 2026-09-15
tags: [skill]
audience: [engineer]
---
# SKILL template

Copy everything below the line into `skills/<name>/SKILL.md` and replace the placeholders.
Keep the knowledge-base frontmatter fields (owner, status, reviewed, tags, audience) and
add `name` and `description`.

---

```markdown
---
name: <skill-name>
description: <One sentence: when an agent or person should reach for this skill.>
title: <Skill title>
owner: <owning-team>
status: draft
reviewed: <YYYY-MM-DD>
tags: [skill]
audience: [engineer]
---

# <Skill title>

## When to use
<Trigger conditions. Be specific enough that the wrong situations are excluded.>

## Inputs
<What must be available before starting. Data classification of each input.>

## Steps
1. <Step>
2. <Step>

## Tools
| Tool | Mutating | Notes |
| --- | --- | --- |

## Checks before finishing
- [ ] <Check>

## Output format
<Exact structure of the result.>

## Evaluation
See `evals/` — <number> cases, graded by <method>.
```
