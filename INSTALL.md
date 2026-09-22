# Installing the Collection inside the bank

This is the page for the engineer who has the zip and has to make it run against the bank's own systems. It
goes in order: check the delivery, run it with fakes, gather the bank's values, build the images, roll out to
staging, then production. Every value the bank has to supply is a variable in one file; every credential is a
name in the secrets provider; nothing is patched in code. Placeholders are in capitals and look like placeholders.

## What you have

The zip unpacks to one directory, `collection-<sha>/`, which is the repository itself with the deliverables beside it.

| In `collection-<sha>/` | What it is |
| --- | --- |
| `components/`, `tools/`, `services/`, `hub/`, `deploy/`, `scripts/`, the `*.md` pages | The repository: components, tools, the two services, the hub's source **and its built `hub/dist`**, deploy files, documentation |
| `MANIFEST.sha256` | Every file in the zip with its sha256, the deliverables included |
| `deliverables/user-manual.pdf`, `technical-guide.pdf`, `leadership-brief.pdf` | The three documents, current for this build |
| `deliverables/collection-walkthrough.mp4` (+ `.en.vtt`) | The walkthrough video, just under nine minutes, captions burned in |
| `deliverables/teaching-the-collection.html` | The teaching guide: every screen, every on-screen sentence, every flow and process in plain words, with a 45-minute first lesson. Opens in any browser |
| `deliverables/confluence/` | The teaching guide split into one Confluence page per chapter, with the images as attachments and `upload.py` to put them into a space; `README.md` there says how |
| `deliverables/screenshots/` | The hub and the guide as they render in this build |
| `INSTALL.md` (this page), `HANDOVER.md`, `DELIVERY.txt` | How to install it; how the parts fit and who owns what; the build's sha and date |

Nothing in the zip fetches anything: no package is downloaded on the bank's side, the hub is prebuilt, and the
Python gates run without Node or network.

## 0. Check the delivery (five minutes)

```
sha256sum -c collection-<sha>.zip.sha256          # the zip is what was sent
unzip collection-<sha>.zip && cd collection-<sha>
sha256sum -c --quiet MANIFEST.sha256              # every file is what was packaged, the deliverables included
scripts/verify.sh python                          # every Python gate, offline: components, services, container trees
```

The manifest at the top covers the whole zip (`scripts/package.sh` writes it over everything, so the release
bundle's own manifest, which covered the repository tree alone, is replaced by it). The last command ends with
`ok: every gate passed (python)`. If it does not, stop and send the output back; nothing below will work on a
delivery that fails here.

**Prerequisites.** Python 3.11 or later; a container runtime (Docker or the bank's equivalent) to build the
images; a place to run two containers with a persistent volume each (ECS with EFS is what the task definitions
assume; anything that runs a container with a volume works). Node and pnpm are needed only to rebuild the hub,
which the bank does not need to do (see §2, the hub is configured at runtime).

## 1. Run it with fakes (ten minutes)

```
docker compose -f deploy/compose.yaml up --build
```

This builds from the public `python:3.11-slim`; to build from the bank's approved image instead, set the build
argument: `BASE=<registry>/python:3.11-slim@sha256:<digest> docker compose -f deploy/compose.yaml up --build`.

The hub is at `http://localhost:8080` (sign in as a persona), the agent at `http://localhost:8081`. This is the
sandbox: mock identity, the fake assistant, the rules engine, fake ticket and deploy systems. Walk through the
user manual's screens here before touching a real system; everything the bank will see is already visible.

## 2. Gather the bank's values

Copy `config/collection.env.example` to `config/collection.env` and fill it in. The table says which team supplies
what and which variables it lands in; `CONFIGURATION.md` explains each system in more depth.

| From | What to ask for | Variables |
| --- | --- | --- |
| Identity (IdP team) | Two app registrations (hub, agent) with `aud` set to each client id; the `groups` claim on tokens; the OIDC issuer URL; the group ids for each role | `HUB_IDP_ISSUER`, `HUB_IDP_AUDIENCE`, `HUB_WEB_OIDC_AUTHORITY`, `HUB_WEB_OIDC_CLIENT_ID`, `HUB_AI_SECURITY_GROUP`, `HUB_OWNER_DOMAIN` (the directory's email domain), `AGENT_IDENTITY=oidc`, `AGENT_IDP_*`, `AGENT_OPERATOR_GROUP_ID`, `AGENT_APPROVER_GROUP_ID`; the group ids in `identity-map.json` |
| Platform team | The record volumes; the secrets (`hub/assistant-token`, `agents/jira-token`, `agents/ado-pat`, under the prefixes `hub/` and `agents/`) and the task roles allowed to read them; an asymmetric KMS key the agent's role may `Sign` with; a bucket the agent's role may `PutObject` to | `HUB_DB`, `AGENT_DB`, `*_SECRETS=aws`, `AGENT_KMS_KEY_ID`, `AGENT_AUDIT_EXPORT` |
| Model risk | An approved inference profile and the VPC endpoint for Bedrock; the roles allowed `InvokeModel` on it | `*_BEDROCK_REGION`, `*_BEDROCK_ENDPOINT`, `*_BEDROCK_INFERENCE_PROFILE_ARN` (or `_MODEL_ID`) |
| Integrations | A Jira service account with read on the incident projects and comment on them; an Azure DevOps PAT with read on pipelines; the pipeline id per service | `AGENT_JIRA_URL`, `AGENT_JIRA_USER`, `AGENT_JIRA_AUTH`, secret `agents/jira-token`; `AGENT_DEPLOYS_URL`, `AGENT_DEPLOYS_PROJECT`, `AGENT_DEPLOYS_PIPELINES`, secret `agents/ado-pat` |
| Knowledge base owners | The console URL and, if the assistant is answered here, a search endpoint | `HUB_KB_URL`, `HUB_KB_SEARCH_URL` |
| The hub's owners | The bank's own listings (assistants, agents, knowledge services) in the shape of `services/hub-api/data/consumers.example.json`; the group-to-role map in the shape of `identity-map.example.json` | `HUB_CONSUMERS_FILE`, `HUB_IDENTITY_MAP` (mounted files) |
| Security / records | The retention for a person's conversations; the per-person limits if the defaults do not suit | `HUB_CONVERSATION_RETENTION_DAYS`, `HUB_RATE_PER_MINUTE`, `AGENT_RUNS_PER_MINUTE` |

Two rules save most of the friction:

- **A variable ending in `_NAME` is the name of a secret, never a value.** Create the secret under the service's
  prefix; the task role reads it at call time. No credential is in the environment, the image or the record.
- **The hub is configured at runtime.** hub-api serves `/config.js` from the `HUB_WEB_*` variables and the page
  reads it first, so the prebuilt `hub/dist` is the production hub. Do not rebuild it to change the identity provider.

Check the file before building anything. The path variables (`HUB_IDENTITY_MAP`, `HUB_CONSUMERS_FILE`,
`HUB_COLLECTION_FILE`, `HUB_GUIDE_FILE`, `HUB_STATIC_DIR`) are container paths, so a check on the host overrides
them with the files in the repository; the agent has no such paths:

```
set -a; . config/collection.env; set +a
(cd services/hub-api && HUB_IDENTITY_MAP=data/identity-map.example.json HUB_CONSUMERS_FILE=data/consumers.example.json \
  HUB_COLLECTION_FILE=data/collection.json HUB_GUIDE_FILE=data/guide-corpus.json HUB_STATIC_DIR=../../hub/dist python3 -m hubapi check-config)
(cd services/agent-runtime && python3 -m agentrt check-config)
```

Or check inside the built images (§3), where the container paths are right as they are. After sourcing the file
as above, `env | grep '^HUB_\|^AWS_' > hub.env`, then, with the directory that holds `identity-map.json` and
`consumers.json` mounted where the task definition mounts it:

```
docker run --rm --env-file hub.env -v "$PWD/config:/app/config:ro" --entrypoint python3 ai-hub:<sha>   -m hubapi  check-config
docker run --rm --env-file agent.env                              --entrypoint python3 ai-agent:<sha> -m agentrt check-config
```

(`agent.env` from `env | grep '^AGENT_\|^AWS_'`; `--entrypoint` because the image's entrypoint would otherwise go
on to serve.) Both exit 0 when the configuration is complete, or list every problem by variable name and exit 2.
In staging and production they refuse mock identity, the fake assistant, the rules engine, fake targets, local
signing, an in-memory record, an environment secrets provider and an http public URL, by design.

## 3. Build the images

From the repository root. The base image is the build argument `BASE`; pass the bank's approved image by digest
(without it, the Dockerfiles default to the public `python:3.11-slim`):

```
BASE=<registry>/python:3.11-slim@sha256:<digest>
docker build --build-arg BASE=$BASE -f services/hub-api/deploy/Dockerfile       -t ai-hub:<sha>   .
docker build --build-arg BASE=$BASE -f services/agent-runtime/deploy/Dockerfile -t ai-agent:<sha> .
```

Push them to the bank's registry. The same image runs in every environment; only the environment changes.

## 4. Staging

1. **Task definitions and roles**: `services/*/deploy/ecs-task-definition.json` and `iam-task-role-policy.json`,
   with the placeholders replaced. The record volumes are EFS access points owned by uid 10001 (hub) and 10002 (agent), the
   users the Dockerfiles create.
2. **Mounted files**: `identity-map.json` and `consumers.json` on hub-api's read-only config volume.
3. **Health checks**: the load balancer and the task health check point at `/api/ready` (hub) and `/ready`
   (agent). A task that answers 503 there is taken out of rotation, and the answer names the failing check.
4. **First increment, read-only**: set `AGENT_TARGETS=tickets,deploys` with the real systems but keep the agent
   at reads by leaving the operators' group small; the agent's first write is a separate decision gated by a
   demonstration (see the leadership brief). Nothing writes without a named person confirming the exact action.
5. **The checks** (`CONFIGURATION.md`, "What to check before the first deployment"): a real token resolves to the
   expected principal on `GET /api/me`; `GET /api/shelf` shows the right `youMaySign` for an owner and for an AI
   security engineer; a brief saved before a task restart is there after; the audit export lands in the bucket
   with a verifying head.
6. **The knowledge base**: `python3 tools/publish_kb.py <checkout of the bank's knowledge base>`, then that
   product's `kb-librarian index --write` and `kb-librarian check`. Idempotent; run it again whenever the
   Collection changes.

## 5. Production

The same images, `*_ENV=production`, the production values. `check-config` in the entrypoint refuses to start
with anything missing or fake. Then the two things only people can do:

- **Sign-offs.** Every component ships unsigned on purpose: a sign-off is a named person's word. The owner and
  an AI security engineer sign on the hub's queue (`Build → Sign-offs`), an engineer downloads the queue's export
  and applies it with `python3 tools/shelf.py --apply-signoffs`, and the commit is the signature. The user manual's
  section on signing components off is the walkthrough.
- **The programme.** Name the enablement lead and two AI security engineers; the champions page in the knowledge
  base holds the cadence and the first meeting's outline.

## 6. Operations from day one

`RUNBOOK.md` is the page to have open. In short: `/ready` for the load balancer; every response carries
`X-Request-Id` and every log line `rid=<id>`; a per-person `429` is a runaway client, not capacity; the record is
versioned and refuses a newer schema (restore before rolling back); `python3 -m hubapi backup <path>` and
`python3 -m agentrt backup <path>` are the backup job; conversations are pruned past the retention daily; the
chain is exported on `AGENT_AUDIT_EXPORT_INTERVAL_S` or by a scheduled `export-audit`; `verify-record` failing
is an incident, never a repair.

## Integration points, and where to change one

Everything the services reach is behind one small adapter each, on the Python standard library. If a bank
system speaks a different dialect, the adapter is the only file to touch; the loop, the policies and the
record do not change.

| System | Protocol as implemented | Adapter |
| --- | --- | --- |
| Identity provider | OIDC discovery, JWKS, RS256; `aud`, `iss`, `exp`, `nbf` checked; `groups` claim to roles; groups overage refused; proven end to end in a browser by `scripts/smoke-oidc.sh` | `services/hub-api/hubapi/auth.py`, `actionloop/identity.py` (`JwksIdP`), `scripts/fake_idp.py`, `hub/tools/oidctest.cjs` |
| Secrets | AWS Secrets Manager (`GetSecretValue` over SigV4), a mounted JSON file, or the environment (sandbox only) | `secretsbyname.py` |
| Signing | AWS KMS `Sign`/`Verify` (asymmetric), or a local key (sandbox only) | `actionloop/signing.py` (`KmsKey`) |
| Model | Bedrock Converse through the bank's VPC endpoint; the rules engine in the sandbox | `bedrock.py`, `engine.py` |
| Tickets | Jira REST v2 (issue get, comment add), basic or bearer | `jira.py` |
| Deploys | Azure DevOps REST (pipeline runs, releases) | `ado.py` |
| Audit export | S3 `PutObject` over SigV4 | `services/agent-runtime/agentrt/export.py` |
| Knowledge base | `GET /search?q=` returning `{items:[{path,title,section,excerpt}]}` (for citations) | `services/hub-api/hubapi/assistant.py` (`normalise`) |
| The platform runtime (optional) | `POST /conversations/{id}/turns` streaming `event: view` (SSE) on the hub's contract | `services/hub-api/hubapi/assistant.py` (`HttpRelayAssistant`) |
| AI clients | MCP 2025-06-18 over Streamable HTTP with elicitation; RFC 9728 resource metadata | `mcpserver/transports.py` |

The hub's API contract is `hub/api/openapi.yaml`; the mock in the browser and hub-api both implement it, so a
platform team that wants to serve the hub from its own runtime has the contract to build against.

## When something does not work

| Symptom | Where to look |
| --- | --- |
| The container exits with `config: <VARIABLE>: <problem>` lines | The variable named; the value is never printed. `check-config` in §2 reproduces it outside the container |
| `/api/ready` answers 503 | The body names the check: `identity` means the JWKS is unreachable from the task; `record` means the volume is not writable |
| `401` on `/api/me` with a real token | `aud` does not match `HUB_IDP_AUDIENCE`, or the issuer differs from `HUB_IDP_ISSUER`; the response's `detail` says which. On a provider that binds tokens to a scope, `HUB_WEB_OIDC_SCOPE` must name the API's scope; `check-config` prints the note |
| `403 groups.overage` on `/api/me` ("Groups not in the token") | The directory left the `groups` claim out because the person is in too many groups. Filter the claim to the hub's groups on the app registration, or emit app roles; the hub never downgrades such a person to an employee |
| Every reload sends the person back to sign in | Silent renew is failing: the browser console shows the provider refusing `prompt=none` in a frame, or a Content-Security-Policy line. Add `offline_access` to `HUB_WEB_OIDC_SCOPE` to renew by refresh token instead, or allow framing on the provider's side |
| A person sees no components or the wrong `youMaySign` | Their groups in `identity-map.json`, and `HUB_AI_SECURITY_GROUP` |
| The agent refuses every write | Intended until a person confirms; a `403` naming `taint` means the ticket text read as an instruction |
| The hub page loads blank | The browser console will show a Content-Security-Policy violation: something is being served from another origin. The hub and its API are one origin by design |
| `verify-record` fails at start | The chain was edited or a row removed. Do not repair; restore the volume from its last backup and treat it as an incident |

## The documents

`README.md` (how the parts fit), `CONFIGURATION.md` (every system), `RUNBOOK.md`, `SECURITY.md`,
`PRODUCTION-READINESS.md` (what is done and what only the bank can supply, with owners), `HANDOVER.md`,
`CONTRIBUTING.md` (the component contract), the three PDFs in `deliverables/`, and every component's `README.md`
and `WALKTHROUGH.md`.
