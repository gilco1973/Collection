# Production readiness: <service>

Date: <YYYY-MM-DD>. Branch `<branch>`. <Standalone or what it depends on.> What is done here is done and tested
offline; what needs the company's accounts is named as OPEN with its owner.

| Area | Status | Evidence | Open item (owner) |
| --- | --- | --- | --- |
| Functional: increment 1 | DONE | `tests/...`, `<demo command>`: <numbers> | <the real replay scored by users> (<owner>) |
| Functional: increment 2 | DONE | | |
| Security: gates, auth on every route, replay, dual control, taint ceiling, corpus | DONE | `<corpus command>`: <n/n> classes taint, 0 unauthorized | Threat model signed (<Security>) |
| Identity | DONE (verified against generated keys) | `tests/...` | Verify against the real JWKS in staging (<owner>) |
| Credentials: none in targets, secrets by name | DONE | | Secrets created and scoped (<owner>) |
| Data: PII masked; logs ids only | DONE | `test_...` | Privacy review of the data classes (<Privacy>) |
| Record: chain-backed, restart resume, verify tool | DONE | | Retention entry (<owner>) |
| Metrics with baseline | DONE ("not measured" as a state) | | Baseline re-measured (<owner>) |
| Resilience: dependencies down mid-turn | DONE | `<chaos command>`: <n> drills, record intact | The drill on staging (<owner>) |
| Packaging: container, non-root, read-only root, health check, fail-closed entrypoint | DONE | image built and run in CI | Base image pinned to the approved digest (<owner>) |
| Deployment descriptors | WRITTEN | `deploy/` | Applied on the staging account (<owner>) |
| CI | DONE | `<workflow>`: <n> tests, corpus, demonstrations, fail-closed check, image build | |
| Model risk | OPEN | evaluation records exist on the chain | Judge validated against labels; entry accepted (<Model Risk>) |

## What "production ready" means here

Everything a release needs that can be done without the company's accounts is done, tested and repeatable: the
code, its tests, the demonstrations, the corpus, the drills, the container, the deployment descriptors, the runbook
and the security notes. The items marked OPEN are account-bound steps with a named owner; none is a design gap. The
first production deployment is <increment 1>; each later increment is a configuration change gated by its
demonstration, not a new build.
