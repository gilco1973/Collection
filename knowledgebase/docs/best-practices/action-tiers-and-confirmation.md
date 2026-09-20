---
title: Action tiers and confirmation
owner: ai-platform-architecture
status: active
reviewed: '2026-09-20'
tags: [best-practice, agents, security, governance]
audience: [engineer, risk]
---
# Action tiers and confirmation

## The rule in one line

Every tool an agent can call has a tier, and the tier decides who has to say yes before it runs: reads run, a
reversible write needs the acting person's confirmation once, a mitigation needs a second person, and money is a
tier of its own. The tier is data on the catalog entry, signed with it, not a judgement the model makes at runtime.

## The tiers

| Tier | What it covers | Who says yes | Structural rule |
| --- | --- | --- | --- |
| R | Reads: incidents, metrics, logs, tickets, runbooks | Nobody; the rule bundle permits by role | Always available at ladder L1 |
| W1 | Reversible writes: acknowledge, comment, post an update, open a ticket | The acting person, once | Refused without a confirmation reference |
| W2 | Mitigations: roll back, scale, toggle a flag, restart | A second person who owns the service, never the requester | Refused without an approval reference; self-approval refused |
| MONEY | Anything that moves money | Out of scope until a road exists | Forbidden by the bundle |

An irreversible action can never be W1; declaring one fails the catalog build. A W2 tool declares its verification
read and its undo on the catalog entry, so the proposal card can show them.

## How a confirmation works

1. The agent (or a person's command) asks for a W1 call. The loop looks the tool up, validates the arguments, evaluates the rules, and, finding no confirmation reference, parks the call with a hash of the tool and its arguments. The person sees a card: exactly what will happen, and the hash.
2. Only the acting person can confirm, and only that hash. The confirmation is consumed once; a second click, or a click by anyone else, is refused and recorded.
3. The call runs with the reference, the result is verified with a read, and everything lands on the record.

A W2 call is the same shape with two people: the requester proposes (expected effect, risk, undo, verification), a
service owner who is not the requester approves from the card or the console, the requester executes once, the loop
verifies and starts a watch on the recovery.

## Why the model never decides

The model reasons and cites; it never calls a tool, holds a credential, or reaches a handler. Its output is advisory
JSON that a command layer turns into calls, and the loop decides. A prompt that says "never act without asking" is
not a control; a tier that structurally refuses a call without a reference is.

## Rollout by increment

Ship reads first, then W1 under confirmation, then W2 under dual control, each after its demonstration is accepted.
The increment is a configuration value that changes the signed catalog: raising it adds tools, lowering it is the
fastest way to remove every write tool.

## Where it is implemented

The collection's `governed-action-loop` component (the harness, the policy library with its structural checks, the
catalog builder) and the `comm-templates` component for the one W1 that reaches customers. The first responder in
[use case 002](../paved-roads/use-case-002-first-responder.md) runs all three tiers.

## Checks a reviewer makes

- Every catalog entry has a tier; every W2 entry has an undo and a verification.
- The structural checks cannot be waived by any bundle.
- The corpus shows zero unauthorized actions: no injected text ever became a W call.
