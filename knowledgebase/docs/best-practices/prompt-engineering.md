---
title: Prompt engineering
owner: ai-platform-architecture
status: active
reviewed: 2026-09-15
tags: [best-practice, prompting, evaluation]
audience: [engineer, data-scientist]
---
# Prompt engineering

## Principles

1. **Evaluation first.** Before editing a prompt, have a set of inputs and expected
   behaviours that the edit should improve. Otherwise you are guessing with a dashboard.
2. **Prompts are code.** They live in source control, are reviewed, versioned and
   tested in CI. A prompt in a database or a chat window is not on a paved road.
3. **Say what to do, not what not to do.** Current models follow positive, specific
   instructions better than lists of prohibitions. State the goal, the audience, the
   format and the constraints.
4. **Give the model the facts, not the memory.** Anything that can change (policy,
   product, rates, names) is retrieved and placed in the prompt, never assumed.
5. **Separate instructions from data.** Put untrusted content (documents, user text,
   tool results) in clearly delimited blocks and tell the model it is data. This is
   the first line of defence against [prompt injection](security.md).
6. **Structured output where a machine reads the answer.** Use the provider's
   structured-output feature with a schema instead of parsing free text.

## A working template

```
System: role, audience, non-negotiable rules, output format.
User:   task statement
        <context> retrieved facts, labelled with source and date </context>
        <input> the thing to act on </input>
        what a good answer looks like (one short example if format matters)
```

## Model-specific notes

- Newer models take fewer, higher-level instructions well; very prescriptive
  step-by-step prompts written for older models often reduce quality. Re-run the
  evaluation set when the gateway routes a logical model to a new version.
- Use the provider's prompt caching for large stable prefixes (system prompt, tool
  definitions, reference documents). Keep volatile content after the cached prefix.

## Anti-patterns

- Pasting the whole policy manual into the system prompt (use RAG).
- Prompt edits with no evaluation diff in the pull request.
- "Be accurate" and "do not hallucinate" as instructions. Give sources instead.
