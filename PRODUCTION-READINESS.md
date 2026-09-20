# Production readiness: the collection

Date: 2026-09-20. Branch `claude/ai-champions-reusable-components-hnq6n4`. What can be done without the bank's
accounts is done, tested and repeatable; what needs an account or a person is OPEN with a named owner. Nothing
open is a design gap. The first deployment is the hub in `staging` with the `http` assistant or none, and the
agent runtime with `AGENT_TARGETS=tickets,deploys` reading real systems; the first write to a real system is a
configuration change gated by its demonstration, not a new build.

| Area | Status | Evidence | Open item (owner) |
| --- | --- | --- | --- |
| Components: 29 in six categories, each with a version, two sign-offs, a walkthrough, a live example, tests | DONE | `scripts/verify.sh python` and `typescript`: every suite and example green; `tools/shelf.py --check` | Sign-offs: every component is at stage 2, "built"; the owner and an AI security engineer sign on the hub after one real use (owners; security team lead names the engineers) |
| The hub (front end): pixel-identical to the design, configured at runtime by hub-api, self-hosted fonts | DONE | `cd hub && pnpm verify` and the pixel guard at 0 px; the default build ran through hub-api's `/config.js` in a browser and signed a component | The redirect URI registered on the app registration (identity engineer) |
| hub-api: the hub's contract behind the bank's identity provider | DONE | 16 tests: the contract route by route, OIDC through a generated RSA key, the three assistants, SSE and the static SPA over HTTP; `check-config` refuses mock identity and the fake assistant in production | Group ids in `identity-map.json`; the consumers file with the bank's listings (platform team); the assistant runtime URL or the Bedrock inference profile (model risk approves the model) |
| Agent runtime: one agent over MCP and a run API, wired by configuration | DONE | 6 tests: the sandbox end to end, the bank wiring with doubles (JWKS identity, KMS, Bedrock, both connectors), the refusals; `check-config` refuses every fake in staging and production | The KMS key, the inference profile, the Jira service account, the Azure DevOps PAT, the group ids (integrations engineer); a sandbox Jira project for the first real read (SRE) |
| Identity: RS256 through the JWKS, groups to roles, mock refused in production | DONE (against generated keys) | `services/hub-api/tests/test_oidc.py`, `governed-action-loop/tests/test_production_adapters.py` | Verified against the real JWKS in staging; the `groups` claim configured on both app registrations (identity engineer) |
| Credentials: none held; names in the secrets provider; SigV4 from the task role; KMS for signing | DONE | `secrets-by-name`, `aws-sigv4`, `signing.KmsKey` tests; connectors' tests show no token in a URL | Secrets created under `hub/` and `agents/`; the task roles applied from `deploy/iam-task-role-policy.json` (integrations engineer) |
| Data: sources fenced, PII masked, cite-or-drop, taint stops before the model; logs ids only | DONE | `cited-llm-engine`, `untrusted-input-guard`, `hub-api/tests/test_assistant.py`, the agent's `never` tests | Privacy review of the data classes the assistant may cite (privacy) |
| Record: the chain, restart resume, verify at every start, export to S3 | DONE | `agent-runtime/tests`: export puts the chain and a pointer; `entrypoint.sh` runs `verify-record` | The bucket with KMS encryption and a retention entry for the chain (platform team) |
| Packaging: containers non-root, read-only root, health checks, fail-closed entrypoints | DONE (trees proven; images built by the bank) | `scripts/smoke-container-tree.sh` assembles each Dockerfile's COPY set, starts the entrypoint, checks health and that production refuses the tree's fakes; `deploy/compose.yaml` | Base image digests pinned to the bank's approved image; images built in the bank's registry (integrations engineer) |
| Deployment: ECS task definitions, least-privilege task roles, EFS records | WRITTEN | `services/*/deploy/` | Applied on the staging account (integrations engineer) |
| Offline delivery: a release bundle with the hub prebuilt and nothing to fetch | DONE | `scripts/bundle.sh`; the bundle unpacked in a clean directory verifies its manifest and passes `scripts/verify.sh python` without network or Node | The bundle transferred through the bank's approved channel and its sha256 recorded (release manager) |
| CI: one script, two runners | DONE | `scripts/verify.sh`; `.github/workflows/ci.yml` and `ci/azure-pipelines.yml` call it | The pipeline created on the bank's runner with a pnpm store for the hub job (platform team) |
| Knowledge base: pages published into the product, its checks at zero | DONE | `tools/publish_kb.py`, `kb-librarian check` on a checkout | The pages published into the bank's knowledge base checkout (enablement lead) |
| MCP: a tool server with elicitation and 403 on taint, a gateway for external servers, a read-only shelf server | DONE | the three components' tests, including the HTTP transport end to end | The official MCP conformance suite run against the tool server with a reviewed expected-failures file (PLT-HAR-33) (platform team) |
| Model risk | OPEN | the think step records the engine, stage and token counts on the chain; the hub's feedback question is stored per turn | The judge and labels for the first read; the inference profile approved (model risk) |
| Operations: readiness routes for the load balancer, request ids end to end, per-person rate limits, a versioned record that refuses a newer schema, online backups, the chain exported from inside the task | DONE | `services/*/tests/test_ops.py`; `scripts/smoke-container-tree.sh` hits `/ready` in both trees | The backup job and the alarm on `/ready` created on the bank's account (integrations engineer) |
| Demonstration video tooling (`demo/`) | OPTIONAL | needs ffmpeg and Chromium; excluded from the bundle | — |

## What "production ready" means here

Every gate runs offline and green; the deployables start only with a complete configuration; fakes cannot reach
production; credentials are never held; the record survives a restart and leaves the task; the bundle carries
everything the bank's build needs. The OPEN items are accounts, ids, keys and people, each named. When they are
closed, the deployment is a configuration change on the same build that passed here.
