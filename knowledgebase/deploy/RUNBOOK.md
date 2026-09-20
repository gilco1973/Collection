# Runbook — the knowledge base in production

One container (`deploy/Dockerfile`: API, console, docs tree and the librarian in a single process)
run either by `deploy/compose.yaml` on one host or by the manifests in `deploy/k8s/`. This is the
operator's page; `docs/integrations/platform.md` explains what the unit is and how it is mounted.

## Prerequisites

- A cluster (≥ 1.27) with Pod Security Admission and a CNI that enforces `NetworkPolicy`; `kubectl`.
- A registry the cluster pulls from. Build from the project root and push yourself — CI only builds:
  `docker build -f deploy/Dockerfile --build-arg IMAGE_SOURCE=<repo url> -t <registry>/knowledge-base:0.1.0 .`
- An external secret manager (ExternalSecret, CSI secret provider or sealed secret) able to render a
  Secret named `knowledge-base-secrets` with the keys of `deploy/k8s/secret.example.yaml`.
- Two cluster parameters: the ingress controller's **namespace name** and its **pod CIDR**.
- A storage class for the state PVC, ideally one with volume snapshots.

## First deploy

1. Set the parameters: `networkpolicy.yaml` (ingress namespace label), `configmap.yaml`
   (`FORWARDED_ALLOW_IPS` = ingress pod CIDR; `KB_PROFILE_RETENTION_DAYS`), `pvc.yaml` (storage
   class), and the image reference (`<registry>/knowledge-base:0.1.0`) in `deployment.yaml` **and**
   `cronjob-retention.yaml` — the validator fails when the two differ.
2. `poetry run python scripts/validate_k8s.py deploy/k8s` (the `manifests` CI job runs the same).
3. Apply in this order (the Secret comes from the secret manager between steps 2 and 3 of the list):

```bash
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/configmap.yaml
# knowledge-base-secrets: rendered by the secret manager into the namespace — never from a file in git
kubectl apply -f deploy/k8s/pvc.yaml
kubectl apply -f deploy/k8s/deployment.yaml -f deploy/k8s/service.yaml
kubectl apply -f deploy/k8s/networkpolicy.yaml
kubectl apply -f deploy/k8s/cronjob-retention.yaml
```

4. Route the ingress (TLS termination) to `knowledge-base.knowledge-base.svc:8765`; the readiness
   path for the ingress health check is `/api/health/ready`. `KB_OIDC_REDIRECT_URI` must be the
   public callback URL (`https://<host>/api/auth/callback`).
5. Verify: `kubectl -n knowledge-base rollout status deploy/knowledge-base`, then
   `kubectl -n knowledge-base exec deploy/knowledge-base -- kb-librarian doctor` (offline checks:
   credentials present, gates, retention, session secret length; exit 0 clean, 1 with a WARN, 2 with a
   FAIL — a rejected setting is a `FAIL settings — KB_<VAR>: <reason>` line, never a traceback) and
   `GET https://<host>/api/health/ready`.

## Secrets

Five keys, all read from the environment at start (`envFrom` the Secret): `ANTHROPIC_API_KEY`,
`KB_API_KEY`, `KB_SESSION_SECRET`, `KB_OIDC_CLIENT_SECRET`, `KB_ATLASSIAN_API_TOKEN`. They live in
the secret manager only: `secret.example.yaml` is a template with empty values and CI rejects a
non-empty one; the image bakes nothing; the process never reads a `.env`; the CronJob mounts no
secret at all. A changed Secret is picked up on the next pod start (`kubectl -n knowledge-base
rollout restart deploy/knowledge-base`) — `envFrom` does not hot-reload.

## Configuration reference

Defaults and comments in `.env.example`; the process reads only its environment. One line each:

- `ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN` — model credential the Agent SDK reads (one of the two).
- `KB_MODEL`, `KB_EFFORT` — model id and effort level (`low|medium|high|xhigh|max`) for audits and chat.
- `KB_MAX_TURNS`, `KB_MAX_BUDGET_USD` — per-audit ceilings; `KB_DAILY_BUDGET_USD` — daily audit spend ceiling.
- `KB_CHAT_MAX_TURNS`, `KB_CHAT_MAX_BUDGET_USD` — per-question chat ceilings; `KB_CHAT_DAILY_BUDGET_USD` — daily chat ceiling (429 past it).
- `KB_ALLOW_LIVE` — server-side gate: every audit is a dry run unless `true` (see "The two gates").
- `KB_ATLASSIAN_ALLOW_WRITE` — gate for Confluence/Jira writes (needs a live run too).
- `KB_ATLASSIAN_BASE_URL`, `KB_ATLASSIAN_EMAIL`, `KB_ATLASSIAN_API_TOKEN` — Atlassian Cloud reads (all three or none).
- `KB_API_KEY` — operator bearer key (break-glass, ≥ 16 chars); empty means nobody is an operator by key.
- `KB_OIDC_ISSUER`, `KB_OIDC_CLIENT_ID`, `KB_OIDC_CLIENT_SECRET`, `KB_OIDC_REDIRECT_URI`, `KB_OIDC_SCOPES` — sign-in (https only; all-or-none except the secret).
- `KB_OIDC_GROUPS_CLAIM`, `KB_OIDC_OPERATOR_GROUPS` — claim name and comma-separated IdP groups that grant the operator role.
- `KB_SESSION_SECRET` (≥ 32 chars), `KB_SESSION_TTL_HOURS` — session cookie signing key and lifetime.
- `KB_PROFILE_RETENTION_DAYS` — inactivity purge period for reader records; empty = no automatic purge.
- `KB_LOG_LEVEL` (`DEBUG|INFO|WARNING|ERROR`), `KB_LOG_FORMAT` (`json|text`) — root logger.
- `KB_REPORTS_DIR`, `KB_MAX_PROBLEM_REPORTS` — report directory under the root; cap on stored reader problem reports.
- `KB_API_HOST`, `KB_API_PORT`, `KB_API_CORS_ORIGINS`, `KB_ROOT` — bind address, port, allowed origins, project root (`serve.py` and every `kb-librarian` command).
- `FORWARDED_ALLOW_IPS` — proxies whose `X-Forwarded-For` uvicorn trusts (the ingress CIDR; `127.0.0.1` trusts none).

## Upgrade

Bump the tag in `deployment.yaml` and `cronjob-retention.yaml` together (`app.kubernetes.io/version`
too), run the validator, `kubectl apply` both. `Recreate` stops the old pod before the new one starts,
so an upgrade is a short outage (readiness fails, the ingress returns 503) and never two writers on
the RWO volume. Do not upgrade while an audit is running (`GET /api/audits` shows `in_progress`): the
new process marks it `failed`. To pin a digest once the registry has scanned the image, append it to
the same reference (`knowledge-base:0.1.0@sha256:<digest>` from `docker buildx imagetools inspect`);
base images in the Dockerfile are pinned the same way (`node:22-alpine@sha256:…`,
`python:3.11-slim@sha256:…`) — resolve the digests in your registry, the build sandbox cannot.

## Rollback

`kubectl -n knowledge-base rollout undo deploy/knowledge-base` (or re-apply the previous tag in both
manifests). The state volume is forward-compatible within a release line: reports and records written
by the newer version are read by the older one. Rolling back a *content* change is a git revert of
`docs/` plus a rebuild; rolling back one audit's edits is `kb-librarian rollback` / the console's
rollback, which uses the snapshots on the volume.

## Rotating secrets

- `KB_SESSION_SECRET`: set the new value in the secret manager, restart the deployment. Every
  session cookie is signed with the old key and becomes invalid: **everyone is signed out** and
  signs in again through the IdP. Do it in a quiet window and say so.
- `KB_API_KEY`: rotate in the secret manager, restart; hand the new key to the operators who use
  the break-glass path (group-based operators are unaffected). `kb-librarian doctor` confirms length.
- `KB_OIDC_CLIENT_SECRET` / `KB_ATLASSIAN_API_TOKEN`: rotate at the provider, then here, then restart.

## Backup and restore

The PVC (`.librarian/`) is the only state: `reports/` (audit reports), `snapshots/` (rollback
material), `problems/` (reader problem reports), `users/` (reader records, hashed file names) and
`chat-spend.json` (daily chat totals). Prefer storage-class `VolumeSnapshot`s on a schedule; otherwise
`kubectl -n knowledge-base exec deploy/knowledge-base -- tar czf - -C /srv/knowledge-base .librarian > kb-state-$(date +%F).tgz`
(a consistent copy needs no running audit). Restore: scale the deployment to 0, start a one-off pod
from the same image with the PVC and the same security context, `kubectl exec -i … -- tar xzf - -C
/srv/knowledge-base < kb-state-….tgz`, delete it, scale back to 1. Reader records are personal data:
the backup inherits the retention period below and the same access controls as the secret manager.

## Retention

`cronjob-retention.yaml` runs `kb-librarian profiles purge --live` daily at 03:30 UTC with
`concurrencyPolicy: Forbid`, on the same image and PVC, pinned to the API's node (RWO). It removes
reader records whose `updated_at` — moved by every reader activity — is older than
`KB_PROFILE_RETENTION_DAYS`; while that value is empty the job exits 2 and removes nothing. A record
holding a "sign out everywhere" epoch is kept until `KB_SESSION_TTL_HOURS` have passed since its last
activity, so a purge can never revive a revoked session. Check with
`kubectl -n knowledge-base get jobs` and the job log (counts only, never identities);
`kb-librarian profiles stats` shows count and oldest/newest. Compose equivalent, from the host's cron:
`docker compose -f deploy/compose.yaml exec knowledge-base kb-librarian profiles purge --live`.

## Search index

`cronjob-index.yaml` runs `kb-librarian index --embeddings` daily at 01:00 UTC on the same volume,
so hybrid search and the librarian's `semantic_search` have an index (until the first run the API
answers `"mode": "keyword"` and `doctor` warns). `KB_EMBED_URL`/`KB_EMBED_MODEL` in the ConfigMap and
`KB_EMBED_API_KEY` in the Secret choose the provider; empty = the offline hash embedder (no page text
leaves the pod, token overlap only). Run it once by hand after the first deploy:
`kubectl -n knowledge-base create job --from=cronjob/knowledge-base-index index-now`. Compose:
`docker compose -f deploy/compose.yaml exec knowledge-base kb-librarian index --embeddings`.
Readers can also delete their own record from the console at any time.

## Health endpoints

- `GET /api/health` → 200 `{"status":"ok","version":…,"checks":{…}}` while the process is up (liveness;
  the Dockerfile `HEALTHCHECK` and the compose healthcheck call it too).
- `GET /api/health/ready` → 200 when the catalog loads and `.librarian/` is writable; 503
  `{"status":"not_ready","checks":{…}}` otherwise (readiness). Neither carries a secret, a hostname or a path.

**Not ready** means the pod is up but cannot serve correctly: the volume is missing, full or not
writable by uid 10001 (`fsGroup` mismatch after a restore), or the docs tree failed to load. The pod
is removed from the Service and not restarted, so the cause stays inspectable
(`kubectl -n knowledge-base describe pod`, then the JSON log).

## Logs and alerts

One JSON line per request on logger `kb_librarian.api.access` with `method, path, status,
duration_ms, request_id, client` (`client` is the resolved address, never a cookie or bearer;
`request_id` is echoed as `X-Request-ID` and inside every error envelope). Alert on: readiness
failing for > 2 minutes; liveness restarts; `status` 5xx rate; 429 on `/api/chat` (daily budget
reached); the retention Job failing twice in a row; PVC usage > 80 %. Ship stdout/stderr to the
platform pipeline; the process writes no log file (the root filesystem is read-only).

## The two gates

`KB_ALLOW_LIVE=false` forces every audit to a dry run whatever a caller asks; `KB_ATLASSIAN_ALLOW_WRITE=false`
blocks Confluence/Jira writes even in a live run. Both are `"false"` in every manifest and in compose,
because a leaked operator key must never be able to change content, and because the hosted image is
the wrong place for live edits anyway: its docs tree is a read-only image layer. A live audit needs a
**writable docs volume** (compose bind mount, `chown -R 10001 docs`) **and a process that commits the
result to git** — otherwise the edit lives only in a container and is lost on the next deploy. Keep
live runs on a host that has both (the weekly CI workflow opens a PR), and keep the hosted
deployment dry-run only.
