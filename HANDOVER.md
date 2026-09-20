# Handover: the collection

## What this is

One repository with three parts and two deployables. `components/` holds 29 AI components in six categories
(agent, harness, tool, integration, pattern, skill), each self-contained with a manifest, tests, a walkthrough and
a live example. `hub/` is the employee AI hub front end. `services/hub-api` is the hub's API behind the bank's
identity provider; `services/agent-runtime` serves one agent of the collection over MCP and a run API. The
knowledge base and the first responder are standalone products; this repository lifts pieces from them and
publishes pages into the knowledge base.

## Where to start

1. `README.md` (how the parts fit), then `CONTRIBUTING.md` (the component contract and the onboarding process).
2. `scripts/verify.sh python` on a laptop with Python 3.11: every Python gate, no network.
3. `deploy/compose.yaml`: both deployables locally with fakes; sign in to the hub as a persona; run the agent's first read with `curl`.
4. `CONFIGURATION.md` and `config/collection.env.example`: what the bank has to supply.
5. `PRODUCTION-READINESS.md`: what is done and what is open, with owners.

## Decisions worth knowing

- The manifest is the record of a sign-off and the commit is the signature; the hub only records requests.
- Fakes exist for the sandbox and are refused by configuration in staging and production.
- Services vendor component files (`services/vendor.json`) the way components vendor from each other; a change is made in the component, then copied.
- The hub's mock API and the hub-api service implement the same contract; the browser flow was proven against both.
- Categories, not directories, say what a component is; `agents/`, `python/`, `typescript/`, `skills/` are groups.

## Owners

Every component's `owner` field; the enablement lead runs the programme; the AI security engineers sign.
`PRODUCTION-READINESS.md` names an owner per open item.
