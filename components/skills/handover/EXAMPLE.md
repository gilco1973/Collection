> A live example of the skill: the first responder's real document at its 2026-09-19 snapshot, with product and company names made neutral. Every row was true of that codebase on that date.

# Handover: the responder, the first-responder surface

Date: 2026-09-19 (first issued 2026-09-17). Author: the responder's author with a coding agent. Branch `claude/responder-first-responder`, folder
`crossriver-ai-platform-agentcore/responder/`, built to use case 2 (`../usecases/responder/`, version 0.2, standalone edition).
the responder depends on no platform: its core (`crai/`, vendored here) is the action loop, the rules, the record, identity,
the data guard, kill switches, budgets and telemetry, as a standard-library package.

## What this is

The full implementation of the responder for the three increments of the use case, runnable on a laptop with Python 3.11 and
nothing else, and deployable as one container with the descriptors in `deploy/`. The core, the responder, the
surfaces and the clients are real code; in fake mode PagerDuty, New Relic,
Elastic, CloudWatch, Azure DevOps, Jira, Confluence, Teams, the flags service, ECS and the engine are in-process
fakes behind the interfaces the live clients implement. The next person points the configuration at the real
services; nothing above `wiring.py` changes.

```
cd crossriver-ai-platform-agentcore/meg
python3 -m unittest discover -s tests -t .     # 66 tests
python3 -m responder replay 10 && python3 -m responder liveweek && python3 -m responder gameday && python3 -m responder corpus && python3 -m responder chaos
```

Last run on this machine: 66 tests passed; replay 10/10 inside two minutes, all claims cited, 0 unauthorized
actions, 143 connector calls, 0 disagreements between the two rule evaluations, 175 chained records; live week: ack once and replay
refused on 3/3, handover on acknowledgement 3/3; game day: self-approval refused, owner approval, executed once,
replay refused, postmortem drafted 0.001 s after close, the repeat incident cites its predecessor; corpus 6/6
tainted and refused with 0 unauthorized actions; chaos 4/4 with the record intact.

## Since the first handover (2026-09-17 → 2026-09-19)

| Change | Where | Commit |
| --- | --- | --- |
| Use case 2 rewritten as the standalone edition (0.2): no platform dependency; the core vendored into `crai/` so this folder builds, tests and ships alone | `../usecases/responder/`, `crai/` | 5bbe941 |
| The in-room explanation: the how-to card with prompt pills right after the incident card, the grouped `@the responder help`, a one-line first-time hint, the five-step guide at `/hub/help` | `responder/onboarding.py`, `teams/bot.py`, `hub/api.py`, `tests/test_onboarding.py` | 0098f5c |
| Release 2 specified and planned (not implemented): the investigation engine, change feed, catalog and dependencies, impact-based severity, verification plans, transcripts, the regulatory clock, learning, earned autonomy; increments 4 to 6 as MEG-5 to MEG-9, 28 tickets, 189 points | `../usecases/responder-release2/` | 4264402 |
| The walkthrough video pipeline: real screens from the running the responder, a 15-slide deck, frames, narration providers (ElevenLabs, Edge, captions-only), ffmpeg assembly; `out/the responder_Walkthrough_v1.mp4` built captions-only here | `walkthrough/` | 80e0cdc |

Release 2 is a specification and a backlog only. The code in this folder is release 1 complete, plus the
in-room onboarding. The first release 2 ticket to pick up is MEG-54 (grouping and triage) together with MEG-51
(the hypothesis tree); `../usecases/responder-release2/jira/README.md` has the critical path.

## MEG tickets this work completes, in the self-contained sense

"Completes" means the code, tests and behaviour the ticket describes exist and pass here, with a fake in place of
the company service where one is needed. The account-bound step that closes the ticket in Jira is named per row.

### MEG-1 · Onboard the responder and assemble the war room (increment 1)

| Ticket | Done here | Remains on the company's account |
| --- | --- | --- |
| MEG-11 the responder on its own core: the action loop, the catalog by tier, the rule set, the ask engine as the think step | `catalog.py` (34 tools, three tiers, increment gate refusing W entries in increment 1), bundle `meg.responder` with the team and operator gates as forbids, `think.py` with the the ask engine adapter and the citation and confidence assertions recorded as `evaluation.first_read` | Run the contract check against the recorded contracts in CI on every change |
| MEG-12 Durable incident sessions | `incident.py`: one incident, many turns, each a harness session saved beside the record; `test_restart_resumes_the_incident_from_the_record` | EFS volume and the ECS service |
| MEG-13 Connectors, read tier | `clients/` live clients for PagerDuty, New Relic, Elastic, CloudWatch, Azure DevOps, repositories through the engine; handlers refuse a call without a redeemed credential | Keys in Secrets Manager by name; the contract check |
| MEG-14 The war room, assembled | `responder.assemble`: channel, card, pin, on-call mention, roles from PagerDuty and the owner map; `test_ac1_ac2_room_and_first_read_within_two_minutes` | Teams app installed in the on-call team; RSC permissions granted |
| MEG-15 The live timeline | timeline entries carry the chain seq they project; `verify_projection`; the postmortem exports it with the chain head | Reviewers accept the export format |
| MEG-16 Correlated first read | `responder._context` (alerts, deploys, error rate, signatures, log lines, runbook, similar incidents), the deterministic engine's hypothesis and citations; injection in any source taints and never becomes an action | Duty engineers score usefulness on ten real incidents (MEG-19) |
| MEG-17 Runbooks as a knowledge service | `IncidentStore.add_runbook/search_runbooks`: owner required, ACL by role, freshness flag | Ingest the operations runbooks; the retrieval report (PLT-RET-7) |
| MEG-18 Teams delivery fixed | `clients/graph.chunk` (4,000-character parts, numbered), every proactive post returns an id or a typed stop, `logs.py` ids only with a test that no incident text reaches a log line | — |
| MEG-19 Increment 1 demonstration | `python3 -m responder replay 10` and `out/replay.json` with time-to-context per incident | The real replay with SRE scoring |

### MEG-2 · Act with confirmation (increment 2)

| Ticket | Done here | Remains |
| --- | --- | --- |
| MEG-21 PagerDuty write tools as W1 | acknowledge, add responder, escalate, page a service, resolve; confirm once, act once, verify once; replay refused; escalation names level and reason on the card | PagerDuty user mapping from the identity service |
| MEG-22 Stakeholder updates from templates | `templates.py` (status, leadership, handover, customer), fields only, registry hash; `responder.update` under confirmation | Templates signed with the catalog in the prompt and skill registry |
| MEG-23 Action items to Jira | `add_action_item` / `file_action_items`: the issue carries the incident id and the timeline reference; the item is linked back | Jira project and labels |
| MEG-24 Watch mode | `start_watch` / `watch_tick` / `scheduler.py`: ends on the condition, the budget, a stop or a closed incident, never silently; posts attributed to the watch | — |
| MEG-25 The the responder console | `hub/api.py`: incident list, incident page, approvals queue, confirmation page, metrics, trace; a confirmation from the console consumes the same row as Teams | The bank IdP audience `responder-hub` with a `groups` claim |
| MEG-26 Shift handover | `handover` / `accept_handover`: the outgoing engineer remains commander until the incoming one acknowledges; watches transfer | — |
| MEG-27 Increment 2 demonstration | `python3 -m responder liveweek`: MTTA, time to first update, confirmations per incident | The live week |

### MEG-3 · Mitigate under dual control and learn (increment 3)

| Ticket | Done here | Remains |
| --- | --- | --- |
| MEG-31 Mitigation tools as W2 | rollback (pipeline run), flag, scale, restart, each with its verification read and declared undo in `catalog.MITIGATIONS`; executes only from an approval by a different person with the owner role | Pipeline variables for the rollback; the task tag `responder-increment=3` |
| MEG-32 Mitigation proposals | `propose`: expected effect, risk, undo, verification; refused on a tainted session (`test_proposal_refused_on_tainted_session`) | — |
| MEG-33 The postmortem | `draft_postmortem` at close (root cause, contributing factors, citations, action items, customer-impact statement, timeline, chain head); `publish_postmortem` as W1 to Confluence | Confluence space |
| MEG-34 Incident memory | `memory.py` over closed incidents and postmortems; the repeat incident cites its predecessor in the first read | Nothing: memory is the responder's own record |
| MEG-35 Customer-facing status | only `customer_status@1` with the disclosures; the bundle forbids customer audience without the communications role | Compliance signs the template |
| MEG-36 Increment 3 demonstration | `python3 -m responder gameday` | The game day on staging |

### MEG-4 · Governance, security and operations

| Ticket | Done here | Remains |
| --- | --- | --- |
| MEG-41 System record, data classes, outcome metric with baseline | `SECURITY.md` data classes; `metrics.py` with the reported baseline and "not measured" as a state | Baseline re-measured; record entry published |
| MEG-42 Threat model delta | `SECURITY.md` | Signed by Security |
| MEG-43 Injection corpus | `demos.CORPUS`, `python3 -m responder corpus` in CI, non-zero exit on any unauthorized action | Security review; extension from production findings |
| MEG-44 Model Risk entry and judge validation | `evaluation.first_read` records (confidence, cited, tainted) on the chain | Judge validated against labels; entry accepted |
| MEG-45 Chaos on the surface | `python3 -m responder chaos`; `RUNBOOK.md` §5 | The drill on staging |
| MEG-46 Decommission the ask engine's bot | the engine adapter keeps the ask engine as the think step; nothing else of it is used | After increment 3 |

### In-room onboarding (no ticket in release 1; asked for on 2026-09-19)

| Piece | Done here | Remains |
| --- | --- | --- |
| The how-to card at assembly and on `@the responder help`: three things to know, prompt pills grouped as read, act, mitigate, wrap up, filtered by increment and roles, who does what, what the responder never does, guide link | `onboarding.py` (`welcome_card`, `PILLS`, `visible_pills`), posted in `responder.assemble` | Wording reviewed by SRE with the pilot rota |
| Prompt pills as card actions that run the command as if typed | `teams/bot.py` (`meg: command`) | — |
| First-time hint, once per person per incident | `incident.py` (`first_contact`), `teams/bot.py` | — |
| The five-step guide | `onboarding.py` (`guide_html`), `/hub/help` | — |
| The walkthrough video and its pipeline | `walkthrough/` | Narration with an ElevenLabs key (`build_narration.py`); SRE review of the script in `deck.py` |

## Decisions taken while building (for the use case's next revision)

- **PQ-MEG-2 (acks as confirmation):** implemented as *the responder's confirmation card is always required*; a PagerDuty acknowledgement outside the responder is read, never treated as a confirmation. Reverse by having the webhook consume the pending confirmation on `incident.acknowledged` by the same person.
- **Assembly is not an external action.** Creating the channel, posting and pinning the card and mentioning the on-call are R-tier tools inside the company's Teams tenant; every message still runs through the action loop and lands on the chain. Posting a *templated update* is W1.
- **The commander is the confirmer.** W1 confirmations and handovers are the commander's; command moves only by an acknowledged handover. A service owner approves W2 and never executes; the requester executes once.
- **A tainted incident stays tainted.** Taint from any turn is written on the incident and applied to every later session; there is no clearing command yet (a service owner's hash-bound clearing is the obvious next step).
- **Standalone by decision (PD-MEG-1, PD-MEG-6, PD-MEG-9).** Version 0.1 of the use case placed the responder on an AI platform; version 0.2 removes that dependency. The code did not change shape: the core was always a library; it is now vendored here, so `responder/` builds, tests and ships with nothing outside it.
- **Core changes** (made in `../phase0/crai` and vendored here as `crai/`, all covered by that folder's 30 tests): policy ops `contains` / `not_contains`; a consumer-supplied `resource_fn` adding resource attributes; result-shape fields marked `"id"` kept verbatim by the data guard; handler failures raised as the typed stop `handler.errors` with a record; `resume` bound to the admitted person.

## Layout of this folder

```
crai/            the the responder core (vendored): harness, policy, catalog, audit, identity, dataguard, kill, telemetry, signing, gateway
responder/       the service: config, catalog and rules, incident record, guard, think step, templates, responder, cards, commands, onboarding,
                 memory, metrics, wiring, clients/, teams/, hub/, webhooks, scheduler, server, app, demos, main
tests/           66 tests: foundations, control layer, the acceptance criteria, the HTTP surface, onboarding
deploy/          Dockerfile, entrypoint, ECS task definition, IAM policy, Teams manifest, env.example, deploy README
walkthrough/     the video pipeline and the captured shots (outputs under out/, frames/, build/ are not committed)
README.md RUNBOOK.md SECURITY.md PRODUCTION-READINESS.md HANDOVER.md
```

## What it does not do

No real Teams, PagerDuty, observability or change-system traffic was exercised here (no accounts); the live clients
follow the public APIs and are covered by the recording transport in tests, not by the services. The injection
score is a marker heuristic (the control is the ceiling, see `SECURITY.md`). The image was built and run in CI's
job, not on this machine (no Docker daemon); the container layout and the fail-closed entrypoint were verified by
running the copied tree. The the ask engine HTTP engine's stage prompts for `incident-first-read`, `incident-ask`,
`incident-propose` and `incident-rca` are named here and must be added to the ask engine's registry with the JSON
shapes `think.py` parses.

## Taking it to staging

1. `deploy/README.md` steps 1 to 7 with `APP_INCREMENT=1`.
2. `GET /health`; a PagerDuty test incident; the room inside two minutes; `python3 -m responder verify` on a copy of the record.
3. The real replay (MEG-19) and the SRE scoring; then `APP_INCREMENT=2`, the live week (MEG-27); then `APP_INCREMENT=3` with the task tag, the game day (MEG-36).
