---
title: "Tutorial 4: RAG basics"
owner: ai-platform-enablement
status: active
reviewed: 2026-09-15
tags: [tutorial, rag]
audience: [engineer, data-scientist]
---
# Tutorial 4: RAG basics

## Goal

Answer questions over a small sample corpus with citations, and refuse when the corpus
does not support an answer.

## Steps

1. Take the sample corpus (ten Internal-tier procedure pages provided with the tutorial).
   Each has `owner`, `version` and `reviewed` metadata; the ingestion step rejects any
   page missing them.
2. Chunk by heading, embed through the gateway's embedding route, and store the vectors
   with the chunk text and metadata.
3. For a question: retrieve the top five chunks, drop any below the similarity threshold,
   and build the prompt with the chunks in a delimited `<context>` block labelled by
   source and version.
4. Instruct the model to answer only from the context and to cite chunk ids; if the
   context is empty, return a refusal that names the corpus owner.
5. Evaluate: 20 answerable questions (expected citation present) and 5 unanswerable
   ones (expected refusal). Measure retrieval recall and answer faithfulness separately.

## What you learned

- Governance at ingestion is what keeps answers current.
- Refusal is a feature with its own evaluation.
- Retrieval and generation are measured separately.

Next: [Tutorial 5](05-evaluations.md).
