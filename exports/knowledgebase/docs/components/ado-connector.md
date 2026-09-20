---
title: "Ado connector"
owner: ai-platform-engineering
status: active
reviewed: '2026-09-19'
tags: [agents, security, paved-road]
audience: [engineer]
---
# ado-connector

> A component of the collection: `components/python/ado-connector/` in the repository (category integration, python, status ready). Copy it from there; this page is its README, published by the shelf tool. It is an interim implementation of the platform design specification §4.12, §4.1, §5.2 (PLT-CAT-6, PLT-ID-6, PLT-AC-16); the replacement test is under Known limits. Version 1.0.0; sign-off: owner pending; AI security pending; walkthrough `WALKTHROUGH.md`; live example `example.py`.


Azure DevOps as a harness target: recent runs, the latest deploy before a trigger, run a pipeline as a rollback;
a fake; the PAT a name; gated handlers.

## What it is for

The deploy system is the first thing an incident agent reads ("what changed?") and the last thing it may act on
(a rollback, under dual control). This is Azure DevOps as a gateway target: the recent runs of a pipeline, the
latest finished deploy shaped as the agent reads it (run id, service, minutes before the trigger), and running a
pipeline as the rollback action, with an in-memory fake behind the same methods.

## Five-minute start

```
cd components/python/ado-connector
python3 example.py
python3 -m unittest discover -s tests -t .
```

## What is inside

| File | What it is |
| --- | --- |
| `ado.py` | `AdoClient` (`recent_runs`, `get_run`, `latest_deploy`, `run_pipeline`), `FakeAdo`, `handlers(client, audience, pipelines)` where `pipelines` maps a service to its pipeline id |
| `example.py` | The fake seeded with two runs, the unknown-service refusal, a rollback, the real client against a recording double |
| `tests/test_ado.py` | URLs and auth, minutes-before-the-trigger, the service map and the credential rules |

## How to reuse it

Copy `ado.py`. Build the client with your HTTP and secrets provider, the organisation URL, the project and the
PAT's name. Register `handlers(client, "deploys", pipelines={"checkout": 42})` as the target the agent's template
names: `deploys.recent` and `deploys.runs` are R; `deploys.rollback` is W2 and runs only with the approval
reference the harness demands. The PAT needs read on pipelines and, for the rollback, queue on the one pipeline.

## Rules it enforces

- A service not in the pipeline map is refused before any call; the agent cannot name a pipeline id directly.
- No handler runs without a redeemed reference for its audience; the rollback records the acting person and the reason in the run's variables.
- The PAT is a name resolved at call time; it appears only in an Authorization header.

## Where it came from

`meg-first-responder`, `meg/responder/clients/change.py` (`AdoClient`, `FakeChange`), snapshot 2026-09-19.
Extraction: `latest_deploy` added for the incident agent's read; the service-to-pipeline map moved into the
handlers so the template names services, not ids.

## Known limits

Pipelines API 7.1 only; releases (the classic API) are not read. The rollback is "run the pipeline with a target
run": the pipeline itself must implement it.

**Replacement test:** the same operations are a recorded contract in the registry with generated clients
behind a Gateway target; the handlers here bind to the same contract operations, and the harness's conformance
tests through the target pass on both.
