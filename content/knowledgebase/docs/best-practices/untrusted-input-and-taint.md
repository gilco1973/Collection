---
title: Untrusted input and the taint ceiling
owner: ai-platform-architecture
status: active
reviewed: '2026-09-20'
tags: [best-practice, security, agents, prompting]
audience: [engineer, risk]
---
# Untrusted input and the taint ceiling

## The rule in one line

Text a model reads is evidence, never an instruction. Every alert title, log line, ticket body, runbook step, chat
message and code comment is a source with an id and a score; a source that looks like an instruction taints the
session, and a tainted session is capped to reads however the rules read.

## What "capped to reads" means

The loop keeps a ladder per session (L0 to L3). A tainted session's effective ladder is L1 whatever it was admitted
at, and W1 and W2 tiers need at least L2. So reads continue, the person still gets the first read and can ask
questions, but no proposal is made and no write tool runs from that session, and the refusal is recorded with the
source that caused it. There is no prompt involved: the check is in the policy library's structural checks.

## The five steps on every turn

1. **Tag.** Each piece of upstream text becomes a source: a stable id, a kind, a reference a reviewer can open, the producing tool.
2. **Score.** A marker heuristic scores the text; two hits reach the threshold. Code is scored on its comments and string literals only, so identifiers never trip it.
3. **Fence and mask.** The model sees every source inside a tagged block with `suspicious="true"` where it applies, and PII masked to class tokens. It never sees raw upstream text interpolated into a prompt.
4. **Withhold from people.** A suspicious source is never quoted in a room or a card; its id stays citable.
5. **Cite or drop.** Every claim the model returns must cite source ids that exist; a claim that does not is dropped. Confidence is the cited share damped by the injection score, never a number the model asserts.

## The corpus

Keep a corpus of instruction-bearing inputs by class (alert title, log line, runbook step, channel message, deploy
name, ticket comment, code file, commit message) with the outcome each must produce, and run it in CI on every
release. The acceptance criterion is zero unauthorized actions and every proposal refused. Extend it with every
pattern found in production. The heuristic is a floor; the taint ceiling is the control.

## Clearing taint

Not by the model, not by the agent, and not silently. The only clearing path is a hash-bound confirmation by the
acting person that names the segment they accept, recorded on the chain, for that run only. Until a product needs
it, leave it out.

## Where it is implemented

The collection's `untrusted-input-guard` component (sources, scoring, masking, fencing, citations, the corpus) and
the structural checks in `governed-action-loop`; the `cited-llm-engine` applies the guard on both sides of the model.
See also [Security for AI systems](security.md) for the wider threat model.
