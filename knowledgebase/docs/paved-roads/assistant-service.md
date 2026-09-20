---
title: Assistant service
owner: ai-platform-architecture
status: active
reviewed: 2026-09-15
tags: [paved-road, prompting, evaluation]
audience: [engineer, product]
---
# Assistant service

Use this road for conversational assistants and question answering over approved content
where a person reads and acts on the answer. It is the most common first project.

## Reference architecture

```
user ──► channel (web / internal chat) ──► assistant service ──► LLM gateway ──► model
                                             │        ▲
                                             ▼        │
                                       conversation  approved
                                          store      content (RAG, optional)
```

- **Channel**: one of the approved internal channels. Customer-facing channels require the
  customer-facing tier of the [model lifecycle](model-lifecycle.md).
- **Assistant service**: a stateless service holding the system prompt, guardrails and
  the conversation-store client. Written on the paved Python stack.
- **Conversation store**: retention follows the data classification of the channel.

## Requirements before release

1. System prompt and guardrails in source control, reviewed with the code.
2. An evaluation set of at least 100 representative conversations with graded expected
   behaviour, run in CI ([evaluation pipeline](evaluation-pipeline.md)).
3. Refusal and hand-off paths: what the assistant says when it cannot help, and how a
   person takes over. Tested, not just designed.
4. Monitoring page: latency, cost, refusal rate, user feedback, evaluation trend.
5. Model risk record at the tier matching the channel.

## Common mistakes

- Putting policy text into the prompt instead of retrieving it: it goes stale silently.
  Use the [RAG service](rag-service.md) for anything that changes.
- Skipping the hand-off path because "the assistant is only internal". Internal users are
  still relying on it for decisions.
- Measuring quality by spot-checking transcripts. Write the evaluation first.
