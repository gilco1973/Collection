# Security notes for <service>

## Threat model delta

What changes against <the previous state>: <the service> gains <write tools with an egress path>, and its inputs
widen from <questions> to <alert titles, log lines, runbook text, messages>. Every one of those is untrusted.

| Threat | Control | Where |
| --- | --- | --- |
| Instruction injection through <source> | Every source is a tagged segment with an injection score; above the threshold the session is tainted: reads continue, proposals and write actions are refused; instruction-like text is withheld from what is quoted to people | `guard.py`, `policy.structural_checks` |
| A confirmation replayed, or clicked by someone else | Hash-bound to tool and arguments, consumed once, only by the requesting person | `harness.confirm` |
| Self-approval of a mitigation | The approver must differ from the requester and hold the owner role; refused at decision and again at execution | the bundle, `decide/execute` |
| A person outside the team or not an operator | Gates at the surface and again as forbids in the bundle; both fail closed on missing configuration | `auth`, `config.validate` |
| An unauthenticated request | Every route but health requires a bearer; algorithm pinned to RS256 | `server`, `jwt` |
| A credential held by a target | Handlers receive a redeemed reference per call; clients fetch secrets by name at call time; nothing is logged | `secrets`, `identity` |
| Customer-facing free text | Only the Compliance template with its disclosures, fields only, posted by the communications role | `templates`, bundle rule |
| PII reaching the model or a room | Masked per audience before the model; cards mask for people; log lines carry ids only | `dataguard`, `logs` |
| A resumed session under another person | The harness refuses to resume for anyone but the admitted person | `harness.resume` |
| A restart losing state | Record, sessions, confirmations and approvals in a durable store; the timeline is a projection of the chain and verifies | `audit`, the store |
| Malformed model output | Strict JSON per stage; a parse failure is refused, never guessed; uncited claims dropped | `engine` |
| The model attempting an action | No tool calls, no credential, no handler; output is advisory; every act stays behind W1 or W2 | `engine`, the bundle |
| Token budget exhaustion | Per-call and per-turn budgets metered by the gateway | `modelgw` |

## Data classes

| Class | Examples | Handling |
| --- | --- | --- |
| Metadata | ids, service, severity, timestamps, roles | Record; logs (ids only) |
| Free text | alert titles, log lines, runbook text, messages | Record (masked for people); never in logs; fenced and masked for the model |
| Customer data in text | emails, account numbers | Masked before the model and before the room; classes recorded, values never |
| Credentials | API keys, tokens, the signing key | The vault by name; never in the record, the logs, or a result |
| The record | the chain and its projection | Append-only, hash-chained, exported unsigned until the key service anchors it |

## The corpus

`<command>` runs <n> instruction-bearing inputs across <k> classes and fails the build on any unauthorized action or
any proposal that is not refused. Extend `<where>` with every new pattern found in production. The heuristic is a
floor, not the control: the control is the taint ceiling and the rules, which hold even when the heuristic misses.

## Known limits

<The injection score is a marker heuristic. The signing key is local until the key service. Decisions that remain
open and who owns them.>
