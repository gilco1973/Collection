# Deploying hub-api

One container: the API and the built hub. Everything here carries placeholders in capitals; nothing is a real
account, id or address.

1. **Build the hub** for the environment: `cd hub && cp .env.production.example .env.production` (fill in the
   identity provider's values) `&& pnpm install --frozen-lockfile --offline && pnpm build`. Behind an air gap, use
   the release bundle (`scripts/bundle.sh` ships `hub/dist` prebuilt, so no package is fetched on the bank's side).
2. **Build the image** from the repository root: `docker build -f services/hub-api/deploy/Dockerfile -t ai-hub:GIT_SHA .`
   with the base image digest pinned to the bank's approved image.
3. **Mount the configuration**: `identity-map.json` and `consumers.json` on the read-only config volume (the
   example files in `services/hub-api/data/` are the shapes).
4. **Secrets**: `hub/assistant-token` (when `HUB_ASSISTANT=http`) under the `hub/` prefix the task role may read.
5. **Task definition and role**: `ecs-task-definition.json`, `iam-task-role-policy.json`; the record volume is EFS
   with an access point owned by uid 10001.
6. **Verify**: `/api/health` answers and `/api/ready` says `ready` (the load balancer and the task health check use `/api/ready`); `GET /api/me` with a real bearer resolves the expected principal; the checks
   in `CONFIGURATION.md`.

Local, with fakes: `deploy/compose.yaml` at the repository root.
