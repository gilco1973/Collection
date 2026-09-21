# Deploying hub-api

One container: the API and the built hub. Everything here carries placeholders in capitals; nothing is a real
account, id or address.

1. **The hub is prebuilt**: use the `hub/dist` from the release bundle (`scripts/bundle.sh` ships it, so no package
   is fetched on the bank's side). It is configured at runtime from the `HUB_WEB_*` variables through `/config.js`,
   so it is never rebuilt to change the identity provider. `hub/.env.production` is only for a hub served by a
   static host without hub-api, where the values are baked in at build time.
2. **Build the image** from the repository root, with the bank's approved, digest-pinned base image as the build argument:
   `docker build --build-arg BASE=REGISTRY/python:3.11-slim@sha256:DIGEST -f services/hub-api/deploy/Dockerfile -t ai-hub:GIT_SHA .`
   (without `--build-arg`, the Dockerfile's default is `python:3.11-slim`).
3. **Mount the configuration**: `identity-map.json` and `consumers.json` on the read-only config volume (the
   example files in `services/hub-api/data/` are the shapes).
4. **Secrets**: `hub/assistant-token` (when `HUB_ASSISTANT=http`) under the `hub/` prefix the task role may read.
5. **Task definition and role**: `ecs-task-definition.json`, `iam-task-role-policy.json`; the record volume is EFS
   with an access point owned by uid 10001.
6. **Verify**: `/api/health` answers and `/api/ready` says `ready` (the load balancer and the task health check use `/api/ready`); `GET /api/me` with a real bearer resolves the expected principal; the checks
   in `CONFIGURATION.md`.

Local, with fakes: `deploy/compose.yaml` at the repository root.
