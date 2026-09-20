---
title: The chained record and "not measured"
owner: ai-platform-architecture
status: active
reviewed: '2026-09-20'
tags: [best-practice, governance, observability, model-risk]
audience: [engineer, risk, leadership]
---
# The chained record and "not measured"

## The record

Everything an agent did on someone's behalf is one append-only, hash-chained record: admission, every decision with
the policies that produced it, the intent of every write before it ran, confirmations and approvals with their
hashes, taint, stops with their typed reason, and the model context of every model call (model id, prompt reference
and hash, tokens, duration). Each record carries the hash of the previous one; `verify` walks the chain and stops at
the first broken link; `export` writes JSON lines with the head for reviewers and examiners.

Two consequences:

- **The timeline is a projection.** What people see in the room or on the console is rendered from the chain, and
  the projection is verified against it. Nothing is shown that is not on the record.
- **The postmortem is an export.** The incident record is the input; the draft cites source ids from it and carries
  the chain head at drafting.

A signature from the key service anchors the head in production; until then the export is marked unsigned, and the
readiness page says so.

## "Not measured" is a state

A metric with no measurement is absent, never zero. Model working time is what the adapter reports, never wall time.
Cost per turn is metered from unit prices that are re-verified against the real bill before the cost model is signed.
A dashboard that shows 0 for a phase nobody measured is lying; one that shows "not measured" is asking a question.

The same rule applies to outcome metrics: time to context, time to acknowledge, time to first update, time to
resolve, postmortem within 48 hours. Each has a baseline measured before the agent existed, or the page says the
baseline is not measured yet and who will measure it.

## The zero-disagreement gate

The same signed rule bundle is evaluated twice on every call: in process by the loop, and again at the connector
boundary. A counter compares the two. A disagreement count above zero on a release is a stop-ship, because it means
the two places that decide disagree about what is allowed.

## Where it is implemented

`audit-chain` (the record), `governed-action-loop` (the projection, the telemetry with "not measured", the
disagreement counter) in the collection. The evaluation pipeline on the paved roads consumes the same records.
