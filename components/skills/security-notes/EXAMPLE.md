> A live example of the skill: the first responder's real document at its 2026-09-19 snapshot, with product and company names made neutral. Every row was true of that codebase on that date.

# Security notes for the responder

## Threat model delta (MEG-42)

What changes against the responder today: the responder gains write tools with an egress path (pages, posts, tickets, mitigations), and
its inputs widen from questions to alert titles, log lines, runbook text, deploy names and channel messages. Every
one of those is untrusted.

| Threat | Control | Where |
| --- | --- | --- |
| Instruction injection through incident text (alert title, log line, runbook, deploy name, message) | Every source is a tagged segment with an injection score; above the threshold the session is tainted: reads continue, proposals and W actions are refused by the structural check (taint ceiling); instruction-like text is withheld from what is quoted to people and the model summary | `guard.py`, `responder.py`, core `policy.structural_checks` |
| A confirmation replayed, or clicked by someone else | Hash-bound to tool and arguments, consumed once atomically, only by the requesting commander, from Teams or the console | `incident.py` (`consume_confirmation`), core `harness.confirm` |
| Self-approval of a mitigation | The approver must differ from the requester and hold `service-owner` and `owner:<service>`; refused at decision and again by the bundle at execution; the approval is consumed once | `catalog.py` bundle, `incident.py`, `responder.decide/execute` |
| A person outside the team or not an operator | The team gate and the operator gate at the surface (Graph transitive membership) and again as forbids in the bundle; both fail closed on missing configuration | `teams/auth.py`, `catalog.py`, `config.py` |
| An unauthenticated request | Every route but `/health` requires a bearer: Bot Framework RS256 for the bot, bank IdP RS256 for the console, a signed PagerDuty webhook; algorithm pinned to RS256 (no `none`, no HMAC confusion) | `server.py`, `jwt.py`, `webhooks.py` |
| A credential held by a target | Handlers receive a redeemed reference for their own audience per call; clients fetch secrets by name at call time; nothing is logged | `clients/__init__.py`, `secrets.py`, core `identity` |
| Customer-facing free text | Only the Compliance template with its disclosures, fields only, posted by a principal with the communications role; the bundle forbids the rest | `templates.py`, bundle rule `f.meg.w1.customer_comms` |
| PII in logs and alerts reaching the model or the room | The core data guard masks per audience before the model; cards mask for people; log lines carry ids only | core `dataguard`, `cards.py`, `logs.py` |
| A resumed session under another person | The harness refuses to resume a session for anyone but the admitted person | core `harness.resume` |
| A restart losing state | The incident record, sessions, confirmations and approvals live in SQLite on EFS; the timeline is a projection of the chain and verifies | `incident.py`, core `audit` |

## Data classes (MEG-41)

| Class | Examples | Handling |
| --- | --- | --- |
| Incident metadata | ids, service, severity, timestamps, roles | Record; logs (ids only) |
| Incident text | alert titles, log lines, runbook text, messages | Record (masked for people); never in logs; fenced and masked for the model |
| Customer data in logs | emails, account numbers | Masked before the model and before the room; classes recorded, values never |
| Credentials | API keys, tokens, the signing key | Secrets Manager by name; never in the record, the logs, or a result |
| The record | the chain and its projection | Append-only, hash-chained, exported unsigned until KMS anchoring (Phase 1) |

## The corpus (MEG-43)

`python3 -m responder corpus` runs six instruction-bearing inputs across the five classes and fails the build on any
unauthorized action or any proposal that is not refused. Extend `demos.CORPUS` with every new pattern found in
production; a marker list is in `guard.INCIDENT_MARKERS`. The heuristic is a floor, not the control: the control is
the taint ceiling and the reference rules, which hold even when the heuristic misses.

## Bedrock / Claude model backend (PR 1 / PR 4)

| Threat | Control | Where |
| --- | --- | --- |
| Prompt/instruction injection reaching Claude through incident sources (alert title, log line, runbook, deploy name, channel message) | Every source is scored for injection before it reaches the model; above the threshold the session is tainted and proposals are refused (the taint ceiling). The model sees only the fenced, masked context (`ctx.fenced()`); no raw upstream text, no secret, and no incident object beyond safe metadata with an injection check on the title. The model's system prompt instructs it to treat all source text as evidence, never as instructions. | `guard.py`, `think.py` (`BedrockEngine._incident_block`, `_complete`), `responder.py` |
| Malformed model output causing unintended actions | The engine parses the model's response as strict JSON matching the stage schema; a parse failure raises `ValueError("malformed answer; refused")`. A proposal `kind` outside the four mitigation kinds is refused. All claims run through `check_citations`; uncited claims are dropped. | `think.py` (`BedrockEngine._complete`, `propose`), `guard.py` (`check_citations`) |
| Model attempting to execute actions | The model has no tool calls, no credential, and no handler. Output is advisory JSON: citations, summaries, proposals. All consequential acts remain behind W1 (hash-bound confirmation) or W2 (dual-control approval). The ambient service principal is structurally W1-incapable by the bundle's forbid rule. | `think.py`, `catalog.py` (bundle), `crai/policy.py` |
| Token budget exhaustion via the model backend | Each model call is metered against a per-call budget (`_ModelTurn`); the gateway refuses calls exceeding the budget. Ambient evaluations use a separate, smaller budget that never decrements the incident's turn budget. | `think.py` (`_ModelTurn`), `crai/modelgw.py` (`ModelGateway.complete`) |
| Bedrock credentials or API keys in code | No API key or secret exists. Access is SigV4 from the ECS task role via the existing `sigv4.py` client. Config carries ARNs and names, never values. | `clients/bedrock.py`, `config.py`, `deploy/iam-task-role-policy.json` |

## Ambient channel teammate (PR 2 / PR 3 / PR 4)

| Threat | Control | Where |
| --- | --- | --- |
| Ambient over-posting (noise/spam in the war room) | Fail-closed master switch (`APP_AMBIENT=off` default); configurable cooldown, per-incident cap, per-hour cap, confidence floor, and token budget. Commander mute silences ambient per incident. Every decision (spoken or silent) is recorded on the chain with a machine-readable reason. | `responder.py` (`ambient_consider`), `config.py` |
| Ambient injection: instruction-like text delivered as an untagged channel message | The message is scored for injection on intake (`room_message`); above the threshold the incident is tainted and ambient stays silent. The corpus includes an ambient-injection class (7/7 all refused). | `responder.py` (`room_message`, `ambient_consider`), `guard.py`, `demos.py` (`CORPUS`) |
| Ambient path reaching a W action without human confirmation | Ambient posts are R-tier only (cited text via `teams___post_message`); any action-shaped content is rewritten as a suggestion. The ambient service principal has a bundle forbid for W tiers. | `responder.py` (`_deaction_ambient`), `catalog.py` (bundle v2) |
| Evaluation of every untagged message exhausting resources | Evaluation rate gate, global evaluations-per-hour cap, fenced-context TTL reuse, bounded intake queue, and a separate ambient token budget/consumer. | `responder.py` (`ambient_consider`), `config.py` |

## Known limits

The injection score is a marker heuristic; Bedrock Guardrails can join it as a second signal later. The signing key
is a local HMAC key under the privileged-access rule until KMS signing. The internal issuer is HMAC (the core's
`FakeIdP` shape) with its secret in the vault; the console and the bot verify RS256 tokens from the real issuers
before minting an internal token.
