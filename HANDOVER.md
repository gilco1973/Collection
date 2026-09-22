# Handover: the collection

## What this is

One repository with three parts and two deployables. `components/` holds 29 AI components in six categories
(agent, harness, tool, integration, pattern, skill), each self-contained with a manifest, tests, a walkthrough and
a live example. `hub/` is the employee AI hub front end. `services/hub-api` is the hub's API behind the bank's
identity provider; `services/agent-runtime` serves one agent of the collection over MCP and a run API. The
knowledge base and the first responder are standalone products; this repository lifts pieces from them and
publishes pages into the knowledge base. `playground/` is the AI Playground, a standalone test bench (standard
library only, imports nothing from the rest) that engineers and AI security engineers point at a solution before
it is onboarded: the contract, 29 probes, the tester's own cases, and a report the signers read.

## Where to start

1. `README.md` (how the parts fit), then `CONTRIBUTING.md` (the component contract and the onboarding process).
2. `scripts/verify.sh python` on a laptop with Python 3.11: every Python gate, no network.
3. `deploy/compose.yaml`: both deployables locally with fakes; sign in to the hub as a persona; run the agent's first read with `curl`.
4. `CONFIGURATION.md` and `config/collection.env.example`: what the bank has to supply.
5. `PRODUCTION-READINESS.md`: what is done and what is open, with owners.

## Decisions worth knowing

- The manifest is the record of a sign-off and the commit is the signature; the hub only records requests.
- An AI Playground report is evidence for a sign-off, never one: it has no path to the manifest. Its probes judge by markers they plant, not by wording; what only a person can judge is `review`.
- Fakes exist for the sandbox and are refused by configuration in staging and production.
- Services vendor component files (`services/vendor.json`) the way components vendor from each other; a change is made in the component, then copied.
- The hub's mock API and the hub-api service implement the same contract; the browser flow was proven against both.
- Categories, not directories, say what a component is; `agents/`, `python/`, `typescript/`, `skills/` are groups.
- Operations live in the services, not beside them: `/ready` for the load balancer, request ids end to end, per-person limits, a versioned record with `backup` and `prune` commands, the chain exported on an interval. RUNBOOK.md is the page to have open.
- The guide in the hub answers only from the repository's own pages (`POST /guide/ask`); adding a page or a README changes what it can say, nothing else does.

## Owners

Every component's `owner` field; the enablement lead runs the programme; the AI security engineers sign.
`PRODUCTION-READINESS.md` names an owner per open item.
