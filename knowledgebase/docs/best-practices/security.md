---
title: Security for AI systems
owner: ai-platform-architecture
status: active
reviewed: 2026-09-15
tags: [best-practice, security, agents]
audience: [engineer, risk]
---
# Security for AI systems

## Threat model in one paragraph

An LLM application takes untrusted text (user input, documents, web pages, tool
results) and turns it into actions or outputs. An attacker who controls any of that
text can try to change the model's behaviour (prompt injection), extract data the
model can see (exfiltration), or make the application take actions on their behalf
(privilege abuse through tools). Our controls assume all three will be attempted.

## Controls

### Inputs

- Delimit untrusted content and label it as data in the prompt.
- Never let retrieved or user content reach the system prompt.
- Scan uploaded documents for embedded instructions where the corpus is external.

### Tools

- Allow-list per use case; deny unknown tools in the permission gate.
- Mutating tools require a stated reason and are denied in dry-run.
- Tools validate their own inputs. A tool that trusts the model's arguments is a
  vulnerability, not a feature.
- Credentials are held by the tool runtime, never given to the model.

### Outputs

- Treat model output as untrusted input to whatever consumes it: escape before
  rendering, validate against a schema before executing, review before sending.
- Log outputs at the retention tier of the input classification.

### Data

- Classification header on every gateway call; the gateway rejects tier violations.
- Secrets and personal data never appear in prompts, examples, tests or this
  knowledge base. The librarian's sensitive-content check is a control, not a courtesy.

## Checklist for review

- [ ] Untrusted content delimited and labelled.
- [ ] Tool allow-list and gate present; dry-run mode exists and is the default.
- [ ] Outputs validated before use.
- [ ] Classification header set; logging tier correct.
- [ ] Red-team evaluation cases (injection attempts) in the evaluation set.

External reference: the OWASP Top 10 for LLM applications, listed in [Resources](../resources/README.md).
