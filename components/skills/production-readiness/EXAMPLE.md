> A live example of the skill: the first responder's real document at its 2026-09-19 snapshot, with product and company names made neutral. Every row was true of that codebase on that date.

# Production readiness: the responder

Date: 2026-09-17. Branch `claude/responder-first-responder`. Standalone: no platform, no shared service, nothing outside `responder/` to wait for. What is done here is done and tested offline; what needs the
bank's accounts is named as OPEN with its owner. Increment 1 can go to staging as soon as the OPEN items in its
column are closed; increments 2 and 3 follow their demonstrations.

| Area | Status | Evidence | Open item (owner) |
| --- | --- | --- | --- |
| Functional: increment 1 (assemble, first read, timeline, runbooks, delivery) | DONE | `tests/test_responder.py::Increment1`, `python3 -m responder replay 10`: 10/10 rooms populated and first reads cited inside two minutes, 0 unauthorized actions, 0 connector disagreements | Ten *real* past incidents replayed with duty engineers scoring the first read (MEG-19, SRE) |
| Functional: increment 2 (W1 under confirmation, updates, Jira, watches, handover, Hub) | DONE | `Increment2` tests, `liveweek`: ack once/replay refused, escalation with reason, updates from templates, Jira items with the incident reference, watches end on condition or budget, handover on acknowledgement | A live on-call week with MTTA and update latency against the baseline (MEG-27, SRE) |
| Functional: increment 3 (W2 dual control, proposals, postmortem, memory, customer template) | DONE | `Increment3` tests, `gameday`: self-approval refused, owner approval, execute once, verification read, watch, postmortem drafted within the hour, repeat incident cites its predecessor | A game day on staging with the real pipeline (MEG-36, SRE); the service-owner Entra groups per service (§8.4 of the use case) |
| Security: gates, auth on every route, replay, dual control, taint ceiling, corpus | DONE | `test_control.py::Bundle`, `test_surfaces.py::test_01`, `corpus`: 6/6 classes taint, 0 unauthorized, all proposals refused | Threat model delta signed by Security (MEG-42); corpus reviewed by Security (MEG-43) |
| Identity: Bot Framework RS256, bank IdP RS256, internal issuer, PagerDuty user mapping | DONE (verified against generated keys) | `test_foundations.py::Jwt` | Verify against the real Bot Framework and IdP JWKS in staging; PagerDuty user mapping from the directory instead of the built-in table (Identity engineer) |
| Credentials: none in targets, secrets by name, SigV4 from the task role | DONE | `test_foundations.py::SigV4`, `clients/__init__.require_credential` | Secrets created and scoped per `deploy/README.md` (Integrations engineer); KMS signing of the catalog and rule set as a later hardening |
| Data: PII masked for the model and the room; logs ids only | DONE | `test_pii_in_logs_never_reaches_the_model_or_the_room`, `test_no_incident_text_in_logs` | Privacy review of the data classes table (MEG-41, Privacy) |
| Record: chain-backed timeline, restart resume, verify tool | DONE | `test_ac3_timeline_is_the_chain_projected`, `test_restart_resumes_the_incident_from_the_record`, `python3 -m responder verify` | Retention entry for the record and the trace (MEG-46) |
| Metrics with baseline | DONE ("not measured" as a state) | `metrics.py`, `/hub/metrics` | Baseline re-measured from the SRE log (MEG-41, SRE) |
| Resilience: Teams, PagerDuty, engine, kill switch mid-incident | DONE | `chaos`: four drills, record intact each time | The drill on staging with the real services (MEG-45) |
| Delivery: chunking, no silent failure | DONE | `Formatter` test; every proactive post returns an id or a typed stop | — |
| Packaging: container, non-root, read-only root, health check, fail-closed entrypoint | DONE (image built and run green in CI run 35209799655) | `deploy/Dockerfile`; the container tree copied and run: `check-config` ok in fake mode, exit 2 unconfigured in live mode, `/health` served, `/api/messages` 401 without a token; the CI `image` job builds and runs the image | Base image digest pinned to the company's approved image (Integrations engineer) |
| Deployment: ECS task, IAM least privilege, EFS record, Teams manifest, PagerDuty webhook | WRITTEN | `deploy/` | Applied on the staging account (Integrations engineer); Teams app installed in the on-call team only (the responder author); webhook subscription (SRE) |
| CI | DONE | `.github/workflows/responder-responder.yml`: 61 tests, corpus, demonstrations, fail-closed check, image build | — |
| Model Risk | OPEN | the first-read judge exists as evaluation records (`evaluation.first_read` on the chain); Bedrock-specific records (`evaluation.bedrock.first_read`) carry model id, prompt hash and token counts; ambient evaluation records (`evaluation.ambient`) carry decision, reason and confidence | Judge validated against duty-engineer labels; entry accepted (MEG-44, Model Risk) |
| Bedrock engine: chaos drill | DONE | `chaos` includes a Bedrock-specific drill: the engine fails after assembly and first read; subsequent asks and proposals are stopped; the first-read finding is preserved; the record verifies | — |
| Ambient metrics | DONE | `metrics.py` exposes spoke/silent rates (both in [0,1] over total decisions), suppression ratio (model-evaluated silences / evaluations), per-incident spoke counts, cap utilisation (peak speaks / `max_per_incident`, in [0,1]), and ambient token spend; the Hub metrics page renders the ambient section; "not measured" remains a valid state; arithmetic verified by `test_pr4_governance.py` with exact numeric assertions (the reviewer verdict PR #16 gap A) | — |
| Ambient evaluation records | DONE | every ambient evaluation (speak or silent) writes an `evaluation.ambient` chain record with decision, reason, confidence, citation count and engine name | — |
| Security: Tag/Bedrock/ambient threat model | DONE | `SECURITY.md` gains rows for (a) prompt/instruction injection reaching Claude, (b) malformed model output, (c) model execution, (d) token budget exhaustion, (e) ambient over-posting, (f) ambient injection, (g) ambient reaching W without human confirmation, (h) evaluation resource exhaustion, each mapped to an existing control | — |
| CI matrix: engine × ambient | DONE | `tests/test_pr4_ci_matrix.py` exercises the deterministic engine, `APP_ENGINE=bedrock` (fake) and both ambient on/off configurations in a single test suite | — |
| Ambient default in production | OPEN | `APP_AMBIENT=off` (fail-closed default); the observe-mode noise review must confirm acceptable suppression ratios and cap utilisation before enabling `suggest` in production; the decision to ship `observe` on by default (data gathering, no posting) vs keeping `off` is recorded here | Gil / SRE decide after the observe-mode noise review with real traffic (plan §7 Q3); the ambient metrics (`/hub/metrics` ambient section) are the input to that decision |
| Decommission of the ask engine's bot surface | OPEN | the ask engine stays as the engine behind `HttpEngine`; its bot routes are unused once the responder is installed | MEG-46 after increment 3 (SRE) |

## What "production ready" means here

Everything a release needs that can be done without the company's accounts is done, tested and repeatable: the code,
its tests, the demonstrations, the corpus, the drills, the container, the deployment descriptors, the runbook and
the security notes. The items marked OPEN are account-bound steps with a named owner; none is a design gap. The
first production deployment is increment 1 (reads only); each later increment is a configuration change gated by
its demonstration, not a new build.
