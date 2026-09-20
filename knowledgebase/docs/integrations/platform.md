---
title: Platform integration
owner: ai-platform-engineering
status: active
reviewed: 2026-09-15
tags: [atlassian, agents, paved-road]
audience: [engineer]
---
# Platform integration

The knowledge base and its librarian are offered to the AI Platform as one deployable
unit: a JSON API, a static console, and the content tree they serve.

## API

`kb_librarian.api.app` exposes two entry points:

- `create_app(root, settings, cors_origins)` — a standalone FastAPI application,
  served by `poetry run kb-librarian-api` (env `KB_API_HOST`, `KB_API_PORT`,
  `KB_API_CORS_ORIGINS`). OpenAPI at `/api/openapi.json`, docs at `/api/docs`.
- `router` — an `APIRouter` the platform mounts under its own application:

```python
from pathlib import Path

from fastapi import FastAPI

from kb_librarian.api.app import install_error_handlers, install_security_headers, router
from kb_librarian.api.deps import build_state

platform = FastAPI()
platform.state.kb = build_state(root=Path("/srv/knowledge-base"))
platform.include_router(router, prefix="/knowledge-base/api")
install_error_handlers(platform)  # the {error: {code, message, request_id}} envelope the console expects
install_security_headers(platform, prefix="/knowledge-base")  # body cap + headers under the mount only
```

(`install_error_handlers` and `install_security_headers` are exported from `kb_librarian.api.app`
next to `router`. The body cap is only as outer as its position: call `install_security_headers`
after any host middleware that reads request bodies, and pass the mount prefix so the host's own
routes keep their limits and headers.) Run the platform behind its ingress with `FORWARDED_ALLOW_IPS` set to the
ingress address so `request.client.host` is the real client: the anonymous problem-report
throttle keys on it, and behind an unconfigured ingress every reader would share one bucket.
Two more operating notes: `POST /pages/{path}/reports` is the one anonymous write (a problem
report, redacted and capped); and the API marks any `in_progress` report it does not own as
`failed` at startup, so do not deploy the API while a CLI live audit is running against the same
tree; cancelling such a run from the console writes the cancel marker (the CLI stops at its next
tool call) and records the report as failed until the CLI saves its own final status. Build
the console with `VITE_API_BASE=/knowledge-base/api` and `VITE_BASE=/knowledge-base/` so
its requests and assets resolve under the mount prefix.

Authorisation is deliberately thin so the platform can wrap it: every request is a
`viewer`; a signed-in person in one of `KB_OIDC_OPERATOR_GROUPS`, or a bearer token equal to
`KB_API_KEY` (break-glass), is an `operator`. Viewers can read
every page that is not withheld, every audit report and the contract, all Internal tier;
front the API with the platform's session so that "viewer" means an authenticated employee. Only operators can
start, cancel or roll back audits. A platform with its own identity provider replaces the
dependency `require_operator` in `kb_librarian.api.deps` with its own claim check.

Server-side gates are unchanged behind the API: `KB_ALLOW_LIVE` forces every audit to a
dry run unless true, and `KB_ATLASSIAN_ALLOW_WRITE` gates Confluence and Jira writes.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/me`, `/contract`, `/sections`, `/sections/{id}/pages`, `/pages`, `/pages/{path}`, `/pages/{path}/findings`, `/search` | Reading |
| `POST /api/pages/{path}/reports` | Reader problem reports (to `.librarian/problems/`) |
| `GET /api/audits`, `/audits/{id}`, `/audits/{id}/export` | Operating: inspect |
| `POST /api/audits`, `/audits/{id}/cancel`, `/audits/{id}/actions/{action_id}/rollback` | Operating: act (operator only) |

## Console

`web/` builds to static files (`npm run build` → `web/dist`) that call the API at `/api`.
Serve them from the platform's static host or from the container below; the Vite dev
server proxies `/api` to `KB_API_URL` for local work.

## Container

`deploy/Dockerfile` builds the console and packages the API with it; `deploy/compose.yaml`
runs it against a mounted knowledge base:

```bash
docker compose -f deploy/compose.yaml up --build
# API on http://localhost:8765/api, console on http://localhost:8765/
```

Secrets (`ANTHROPIC_API_KEY`, `KB_API_KEY`, Atlassian credentials) are injected by the
platform's secret manager as environment variables; nothing is baked into the image.

For a cluster, `deploy/k8s/` holds the manifests: a namespace enforcing the restricted Pod
Security profile, the ConfigMap (both gates `false`), a Secret *template* with empty values,
the state PVC, a single-replica Deployment on `Recreate` with a read-only root filesystem and
probes on `/api/health` and `/api/health/ready`, a ClusterIP Service, a NetworkPolicy (ingress
from the ingress namespace only, egress DNS and 443 only) and the daily retention CronJob.
`scripts/validate_k8s.py` checks their invariants in CI. `deploy/RUNBOOK.md` is the operator's
page: first deploy and apply order, secrets from the secret manager, every `KB_*` variable,
upgrade and rollback, rotating `KB_SESSION_SECRET` and `KB_API_KEY`, backup and restore of the
PVC, retention, what "not ready" means, log fields and alerts, and why the two gates stay off.

## Platform catalog entry

Register the unit as use case 001 (see
[use case 001](../paved-roads/use-case-001-knowledge-base.md)) with the API base path,
the console URL, the model owner and the monitoring page fed from `GET /api/audits`.
