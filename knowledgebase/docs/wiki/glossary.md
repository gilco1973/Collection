---
title: Glossary
owner: ai-platform-enablement
status: active
reviewed: 2026-09-15
tags: [glossary]
audience: [everyone]
---
# Glossary

**Agent** — a model that chooses which tools to call to complete a task. See [agent design](../best-practices/agent-design.md).

**Assistant** — a conversational feature where a person reads and acts on the answer. See [assistant service](../paved-roads/assistant-service.md).

**Audit trail** — the record of every tool call an agent made, with inputs and outcomes.

**Data classification** — the four-tier label (Public, Internal, Confidential, Restricted) that decides where data may go. See [data classification](../best-practices/data-classification.md).

**Dry run** — an agent mode in which mutating tools are denied and the agent describes intended changes. The default everywhere.

**Evaluation set** — inputs with expected behaviour, used to prove a feature works. See [evaluation pipeline](../paved-roads/evaluation-pipeline.md).

**Frontmatter** — the metadata block at the top of every knowledge-base page (title, owner, status, reviewed, tags, audience).

**Gateway** — the single egress for model calls. See [LLM gateway](../paved-roads/llm-gateway.md).

**Grader** — the deterministic or model-based function that scores an evaluation case.

**Human in the loop** — a named person owns the outcome of an AI-assisted decision. See [ADR-0002](decision-records/ADR-0002-human-in-the-loop.md).

**Librarian** — the agent that maintains this knowledge base. See [librarian agent](../governance/librarian-agent.md).

**Logical model** — a gateway name such as `assistant-default` that maps to a concrete vendor model the platform team can change.

**MCP (Model Context Protocol)** — the standard by which tools are exposed to an agent runtime. The librarian's tools are an in-process MCP server.

**Model owner** — the accountable person for a model or use case throughout its lifecycle.

**Model risk tier** — the classification (1 to 3) that sets the evidence and review cadence a use case needs. See [model risk](../governance/model-risk.md).

**Paved road** — an approved, supported way to build a class of AI system. See [paved roads](../paved-roads/README.md).

**Permission gate** — the code (`can_use_tool`) that decides whether an agent's tool call runs.

**Prompt injection** — untrusted content that tries to change a model's behaviour. See [security](../best-practices/security.md).

**RAG (retrieval-augmented generation)** — answering from retrieved, governed documents rather than model memory. See [RAG service](../paved-roads/rag-service.md).

**Skill** — a `SKILL.md` folder teaching a repeatable procedure. See [skills catalog](../skills/README.md).

**Structured output** — a provider feature constraining the response to a schema.

**Taxonomy** — the fixed list of tags pages may use, defined in `kb.config.yaml` and [taxonomy](../governance/taxonomy.md).
