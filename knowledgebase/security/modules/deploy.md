# Security review sheet: Container, single-process server, deployment manifests and CI workflows

| | |
| --- | --- |
| Module id | `deploy` |
| Kind | deploy |
| Code | `deploy/` (`Dockerfile`, `compose.yaml`, `serve.py`, `RUNBOOK.md`, `k8s/`: `namespace`, `configmap`, `secret.example`, `pvc`, `deployment`, `service`, `networkpolicy`, `cronjob-retention`, `cronjob-index`), `.github/` (workflows), `scripts/` (`validate_k8s.py` — static manifest invariants; `verify-layout.sh`; `console-smoke.mjs`; `handover.sh` — builds the versioned handover zip from tracked files at HEAD, refuses a dirty tree or an undocumented version) |
| Tests | `tests/test_validate_k8s.py` (shipped manifests clean; a root container, a drifting image tag and a filled-in secret are named without echoing the value), `scripts/console-smoke.mjs` (Chromium smoke against the served console), the `container` and `manifests` CI jobs |
| Depends on | Docker, Kubernetes ≥ 1.27 (Pod Security Admission, a CNI enforcing NetworkPolicy), GitHub Actions, PyYAML (validator) |

## Purpose

Builds the console and packages API + console + docs into one image; `serve.py` runs uvicorn with
the SPA mount. `compose.yaml` runs the image hardened on one host; `deploy/k8s/` runs it in a cluster
with a daily retention CronJob; `validate_k8s.py` keeps the manifests' invariants in CI; `RUNBOOK.md`
is the operator's page. CI runs lint/tests/layout/contract checks, the console suite, the browser
smoke, an image build and the manifest validator; scheduled workflows run the nightly dry-run audit
and the opt-in weekly live audit.

## Entry points

- `python deploy/serve.py` (container `CMD`); `docker compose -f deploy/compose.yaml up`.
- `kubectl apply -f deploy/k8s/…` in the RUNBOOK's order; CronJob `knowledge-base-retention`
  (`kb-librarian profiles purge --live`, daily 03:30 UTC, `Forbid`).
- `python scripts/validate_k8s.py deploy/k8s` (exit 1 names each violation).
- Workflows `ci` (jobs `quality`, `console`, `console-smoke`, `container`, `manifests`),
  `librarian-nightly`, `librarian-weekly-live`.

- Workflow `live-smoke` (`.github/workflows/live-smoke.yml`, `workflow_dispatch` + weekly,
  `contents: read`): its first step sets an output `present` from `secrets.ANTHROPIC_API_KEY` and every
  other step is skipped when it is empty; otherwise it serves `deploy/serve.py` locally with that
  credential (never `KB_ALLOW_LIVE`; `KB_CHAT_DAILY_BUDGET_USD=1.0`), waits for `/api/health` and runs
  `scripts/live-smoke.py` (stdlib only: `/api/health`, `/api/health/ready`, one real chat turn;
  `PASS|FAIL name` per check, exit 1 on any failure).
- Workflow `librarian-eval` (`.github/workflows/librarian-eval.yml`, nightly + `workflow_dispatch`,
  `contents: read`, secret-gated exactly like `live-smoke`): runs `kb-librarian eval --json --budget
  "$KB_MAX_BUDGET_USD"` (`KB_MAX_BUDGET_USD=5`, `KB_CHAT_MAX_BUDGET_USD=0.5`, never `KB_ALLOW_LIVE`),
  appends the Markdown report to the job summary and uploads `.librarian/evals/*.json` and `*.md`
  (golden questions, answers, cited paths; no page body) as a 30-day artifact.

## Trust boundaries

- Image runs as non-root `librarian` (uid 10001, `HOME=/home/librarian`). Root filesystem read-only
  in compose (`read_only`, tmpfs `/tmp` and `/home/librarian`) and in k8s (`readOnlyRootFilesystem`,
  `emptyDir` for both); the only persistent state is `.librarian/` on the named volume / PVC.
  `docs/` is an image layer (k8s: read-only) or a bind mount (compose, for live edits only).
- Compose: port on `127.0.0.1` only, `cap_drop ALL`, `no-new-privileges`, cpu/memory/pids limits,
  healthcheck, `restart: unless-stopped`.
- k8s: namespace enforces Pod Security `restricted`; pods run 10001/10001/`fsGroup` 10001, drop ALL,
  seccomp `RuntimeDefault`, no privilege escalation, `automountServiceAccountToken: false`,
  requests/limits. ClusterIP only. The NetworkPolicy admits ingress solely from pods in the namespace
  labelled `kubernetes.io/metadata.name: ingress` on 8765, and egress only to DNS 53 and TCP 443 —
  to **any** destination, because the three dependencies (model API, IdP, Atlassian) are named by
  host, which a NetworkPolicy cannot express; narrow the 443 rule with `to:` (`ipBlock` /
  `namespaceSelector`) or an FQDN policy where the CNI supports one. The cluster API is reachable
  at network level on 443 but no service-account token is mounted, so it answers as anonymous.
- `FORWARDED_ALLOW_IPS`: compose keeps `*` (only the docker bridge can connect); the ConfigMap ships
  `127.0.0.1` (trust no proxy, fail-safe) and the RUNBOOK requires narrowing it to the ingress CIDR.
- CI: `persist-credentials: false` on checkouts; `contents: read` except the weekly live job
  (`contents: write`, `pull-requests: write`) which opens a PR rather than pushing to the base.

## Data handled

Docs tree in the image. On the state volume: audit reports, snapshots, reader problem reports,
reader records (hashed file names) and the chat spend ledger — all covered by the PVC backup and the
retention purge. CI uploads **Markdown** reports only (no tool inputs, no page text) as artifacts
(30/90 days). Validator output names files, kinds, containers and keys, never a value.

## Secrets

Runtime environment from the secret manager; nothing in image layers, no `.env`. k8s: `envFrom` a
Secret `knowledge-base-secrets` whose **template** `secret.example.yaml` holds five keys
(`ANTHROPIC_API_KEY`, `KB_API_KEY`, `KB_SESSION_SECRET`, `KB_OIDC_CLIENT_SECRET`,
`KB_ATLASSIAN_API_TOKEN`) with empty values — the validator fails on any non-empty value; the
retention CronJob mounts the ConfigMap only. CI reads `secrets.ANTHROPIC_API_KEY` for scheduled
jobs; the weekly live job runs only when repository variable `KB_WEEKLY_LIVE == 'true'` and passes
`KB_ALLOW_LIVE=true` to that job alone.

## External calls

Model API, the IdP and Atlassian Cloud over 443 (the only egress the NetworkPolicy allows);
`npm ci`/`pip`/`poetry` installs at build time; Playwright Chromium download in the smoke job;
`HEALTHCHECK` and probes loop back to port 8765.

## Mutations

- `cronjob-index.yaml` runs `kb-librarian index --embeddings` daily on the state volume
  (`.librarian/index/embeddings.sqlite`): it reads the image's docs and writes only that file; with
  `KB_EMBED_URL` set, page text goes to that endpoint (the ConfigMap comment says so); empty = the
  offline hash embedder. Same security context and PVC pinning as the retention job.

- The retention CronJob deletes reader records whose `updated_at` is older than
  `KB_PROFILE_RETENTION_DAYS` (inactivity-based; `--live` is explicit in the manifest, the CLI is
  dry-run without it); `Forbid` prevents overlap; with the variable empty it exits 2 and removes nothing.
- The weekly live workflow may change `docs/` and opens a PR with the diff and the report artifact.
- Every manifest and compose set `KB_ALLOW_LIVE` and `KB_ATLASSIAN_ALLOW_WRITE` to `"false"`; the
  hosted image cannot hold a live edit (read-only docs layer, nothing commits).

## Controls in place

- Non-root, read-only root filesystem, dropped capabilities, seccomp, no service-account token,
  resource limits — in compose and k8s alike, plus Pod Security `restricted` at the namespace.
- `scripts/validate_k8s.py` in the `manifests` CI job: every pod-spec invariant above, no
  `hostNetwork`/`hostPID`/`hostIPC`, no `hostPath` volume, no `hostPort`, no added capability beyond
  `NET_BIND_SERVICE`, replicas 1 + `Recreate`, probes on exactly `/api/health` and
  `/api/health/ready` port 8765, one image tag across all containers (tag kept next to a digest),
  empty Secret template, `Forbid` on the CronJob.
- `serve.py` and the CLI turn a rejected setting into `FAIL settings — KB_<VAR>: <reason>` and exit
  2 (no traceback, no value); an empty variable reads as unset, so the shipped ConfigMap and Secret
  template (`KB_PROFILE_RETENTION_DAYS`, `KB_SESSION_SECRET` empty) start the pod.
- `HEALTHCHECK`/liveness on `/api/health`, readiness on `/api/health/ready`; OCI labels (title,
  description, source via build-arg, version); pinned Poetry; `PYTHONDONTWRITEBYTECODE`.
- `verify-layout.sh`: required files/sections, 200-line file limit, organisation-neutrality scan.
- CI runs pytest with `-W error::claude_agent_sdk.CanUseToolShadowedWarning` so an
  `allowed_tools` regression fails the build. Nightly audit never sets `KB_ALLOW_LIVE`.

## Residual risks and reviewer attention points

- No digest pinning: base images (`node:22-alpine`, `python:3.11-slim`) and the application image
  are tag-pinned; appending digests is an operator step (RUNBOOK) because the build sandbox has no
  registry access. Image scanning belongs to the registry.
- No cluster test in CI: manifests are validated statically only. The readiness path, the JSON log
  fields and the CronJob's `profiles purge` command are contracts with the API and CLI, not exercised
  against a running cluster here.
- Two operator parameters widen or block trust silently if wrong: the ingress namespace label in the
  NetworkPolicy and `FORWARDED_ALLOW_IPS` (too wide → spoofable `X-Forwarded-For`, shared throttle).
  A CNI that ignores NetworkPolicy applies the manifest and protects nothing.
- RWO PVC: the CronJob is pinned to the API's node by podAffinity; with that node gone the purge
  waits, and a restore requires scaling the deployment to zero.
- `pipx install poetry` in workflows is unpinned. The compose `FORWARDED_ALLOW_IPS=*` default must
  not be carried to a deployment where the port is reachable beyond the host.
- `emptyDir`/tmpfs size limits cap scratch space; the SDK CLI's home-directory state is discarded on
  every restart (intended).

## Reviewer checklist

- [ ] `python scripts/validate_k8s.py deploy/k8s` prints `k8s manifests ok`; every value in `secret.example.yaml` is empty.
- [ ] `KB_ALLOW_LIVE` and `KB_ATLASSIAN_ALLOW_WRITE` are `"false"` in `configmap.yaml` and `compose.yaml`.
- [ ] NetworkPolicy ingress label and `FORWARDED_ALLOW_IPS` reviewed against the target cluster.
- [ ] Weekly live job gated by a repository variable and opens a PR, never pushes to the base.
- [ ] Artifacts contain Markdown reports only.
- [ ] Runtime user is non-root, root filesystem read-only; no secret in `Dockerfile`, compose or manifests.

## Sign-off

Submit with `kb-librarian security submit deploy`; the reviewer records the decision with
`kb-librarian security sign deploy …`, which appends a row here and to `security/signoffs/deploy.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
