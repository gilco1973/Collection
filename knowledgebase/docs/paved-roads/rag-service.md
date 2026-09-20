---
title: RAG service
owner: ai-platform-architecture
status: active
reviewed: 2026-09-15
tags: [paved-road, rag, data, evaluation]
audience: [engineer, data-scientist]
---
# RAG service

Retrieval-augmented generation grounds answers in a governed corpus so that the model
cites what it was given rather than what it remembers. Use it whenever the answer must
reflect current policy, product or procedure documents.

## Reference architecture

```
documents ─► ingestion (classify, chunk, embed) ─► vector index (per corpus, per tier)
                                                          │
question ─► retriever (top-k + filters) ─► prompt builder ─► LLM gateway ─► answer + citations
```

## Corpus rules

- One corpus per data classification tier. Never mix tiers in one index.
- Every document carries an owner, a source system, a version and a review date. The
  ingestion job rejects documents without them, exactly as the librarian rejects pages
  without frontmatter.
- Deletions propagate: a document removed from the source is removed from the index in
  the next ingestion run, and the run is logged.

## Answer rules

- The answer cites the chunks used. An answer with no retrieved support is a refusal,
  not a guess. Evaluate this explicitly.
- Retrieval quality is measured separately from generation quality: recall at k on a
  labelled question set, then answer faithfulness against the retrieved context.

## Getting started

[Tutorial 4](../tutorials/04-rag-basics.md) builds a small RAG loop against a sample
corpus. The production service exposes the same interface with the governance above.

## Related

- [Data classification](../best-practices/data-classification.md)
- [Evaluation pipeline](evaluation-pipeline.md)
