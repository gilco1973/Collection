---
name: policy-qa
description: Answer an internal policy question with citations from the governed policy corpus, or refuse when unsupported.
title: Policy Q&A skill
owner: ai-platform-enablement
status: active
reviewed: 2026-09-15
tags: [skill, rag]
audience: [everyone]
---
# Policy Q&A skill

## When to use
A person asks what a policy or procedure says. Not for interpreting a policy for a
specific customer case; that is a human decision.

## Inputs
- The question (Internal tier).
- Access to the governed policy corpus through the [RAG service](../../paved-roads/rag-service.md).

## Steps
1. Retrieve the top passages; if none score above the threshold, refuse and name the policy owner.
2. Answer only from retrieved text; quote the passage and cite document title, section and version.
3. If passages conflict, say so and cite both; do not resolve the conflict.
4. End with the policy owner and the document's review date.

## Tools
| Tool | Mutating | Notes |
| --- | --- | --- |
| Corpus search | No | |

## Checks before finishing
- [ ] Every claim has a citation.
- [ ] Refusal path used when support is missing.

## Output format
Answer, then `Sources:` list, then `Owner:` line.

## Evaluation
`evals/` — 30 questions with expected citations and 10 unanswerable questions expecting refusal.
