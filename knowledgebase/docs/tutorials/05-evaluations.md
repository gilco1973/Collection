---
title: "Tutorial 5: evaluations"
owner: ai-platform-enablement
status: active
reviewed: 2026-09-15
tags: [tutorial, evaluation]
audience: [new-hire, engineer, data-scientist]
---
# Tutorial 5: evaluations

## Goal

Write a first evaluation set and a runner that fails CI when quality drops.

## Steps

1. Pick the feature from Tutorial 1 (the three-bullet explainer). Decide what "good" is:
   exactly three bullets, each under 30 words, no claims beyond the provided context.
2. Write 50 inputs: 35 ordinary, 10 edge cases (empty context, contradictory context),
   5 adversarial (instructions hidden in the context). Store them as JSON in the
   repository next to the prompt. Internal tier only.
3. Write graders: deterministic for bullet count and length; model-graded with a rubric
   for "no claims beyond context", checked against 10 human-labelled samples.
4. Write the runner: run every case, compute the score, write a JSON result, and exit
   non-zero if the score is below the main-branch score minus the tolerance.
5. Wire it into CI on changes to the prompt file. Break the prompt on purpose and watch
   CI fail; fix it and watch it pass.

## What you learned

- The evaluation is the specification.
- Graders are tested too.
- A prompt change without an evaluation delta is not reviewable.

Back to [Tutorials](README.md).
