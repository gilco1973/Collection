# Configuring the collection for the bank's systems

Everything that touches a system outside this repository is named in one place, `config/collection.env.example`,
and read by one settings module per deployable. Nothing is hard-wired: the identity provider, the model, the secrets
provider, the ticket and deploy systems, the knowledge base and the record's location are configuration. Every
settings module fails closed: `check-config` lists every problem by variable name (never a value) and exits 2, and
the container's entrypoint runs it before the process listens. Fakes and mock identity exist for sandbox and
demonstrations and are refused in production by the same check.

## The rule for credentials

A variable that ends in `_NAME` is the name of a secret in the secrets provider (`HUB_SECRETS=aws` is AWS Secrets
Manager reached with the task role's SigV4 credentials; `file:/path.json` is a mounted file; `env` is for a
developer's shell and refused in staging and production). A service holds no credential of its own; targets are
called with references the harness mints per call. Model access is IAM from the task role, never an API key.

## Systems, one by one

| System | Variables | What is needed from the bank |
| --- | --- | --- |
| Identity provider (OIDC, RS256) | `*_IDP_ISSUER`, `*_IDP_AUDIENCE`, `*_IDP_JWKS_URL` (optional); for the browser `HUB_WEB_OIDC_AUTHORITY`, `HUB_WEB_OIDC_CLIENT_ID` | An app registration per deployable with `aud` set to its client id; the `groups` claim on tokens; the group ids for `HUB_IDENTITY_MAP` and `HUB_AI_SECURITY_GROUP` |
| Directory groups to hub grants | `HUB_IDENTITY_MAP` (a JSON file, `services/hub-api/data/identity-map.example.json` is the shape) | Which groups grant which roles (`ops.lead`, `ops.investigator`, `platform.lead`, `ai.security`), entitlements (consumer ids), teams and ladders |
| The bank's own listings | `HUB_CONSUMERS_FILE` (`consumers.example.json` is the shape) | The consumers the hub lists beyond the collection's components, and the registry of systems and tools a brief may name |
| The record | `HUB_DB`, `AGENT_DB` | A persistent volume (EFS in ECS); the record must survive a restart |
| Model | `*_BEDROCK_*` | An inference profile approved by model risk; the VPC endpoint; the task role allowed `bedrock:InvokeModel` on the profile |
| Secrets | `*_SECRETS`, `AWS_REGION`, the `*_NAME` variables | Secrets created under the service's prefix and the task role allowed `secretsmanager:GetSecretValue` on that prefix |
| Catalog signing | `AGENT_SIGNING=kms`, `AGENT_KMS_KEY_ID` | An asymmetric KMS key; the task role allowed `kms:Sign` and `kms:GetPublicKey` on it |
| Ticket system (Jira) | `AGENT_JIRA_URL`, `AGENT_JIRA_TOKEN_NAME` | A service account with read on the incident projects and comment on them |
| Deploy system (Azure DevOps) | `AGENT_DEPLOYS_URL`, `AGENT_DEPLOYS_PROJECT`, `AGENT_DEPLOYS_PAT_NAME` | A PAT scoped to read pipelines and releases |
| Knowledge base | `HUB_KB_URL`, `HUB_KB_SEARCH_URL` | The console URL and, for the bedrock assistant, a search endpoint that returns `[{source, chunk_ref, classification, text}]` |
| The platform runtime | `HUB_ASSISTANT=http`, `HUB_ASSISTANT_URL`, `HUB_ASSISTANT_TOKEN_NAME` | The runtime that owns the employee assistant and streams `event: view` turns on the same contract |
| Audit export | `AGENT_AUDIT_EXPORT` | A bucket the task role may `s3:PutObject` to; the chain's export lands there with its head |

## Two environments, one build

The same image runs in sandbox with fakes and in production against the bank: only the environment changes.
`sandbox` allows mock identity, the fake assistant, the rules engine and fake targets; `staging` and `production`
refuse them, require https public URLs, a file-backed record, a non-environment secrets provider and, for the
agent, KMS signing. Increments are configuration too: `AGENT_TARGETS` names which systems are real, so a first
production deployment reads from real systems and writes to none.

## The hub's build

The hub is built once, anywhere, and configured at runtime: hub-api serves `/config.js` from its `HUB_WEB_*`
settings (the identity provider's authority and client id, the redirect URI, the knowledge base URL, the build
sha), and the page reads it before anything else. So the `hub/dist` in the release bundle is the production hub;
the bank never needs Node or a package store to point it at its identity provider. `HUB_STATIC_DIR` serves it
from the same process, so a deployable is one container. Fonts are served from the same origin; no request
leaves the bank's network for the page itself. `hub/.env.production.example` remains for a hub served by a
static host without hub-api, where the values are baked in at build time instead.

## What to check before the first deployment

1. `python3 -m hubapi check-config` (and the agent's) exit 0 with the production values.
2. A token from the bank's identity provider resolves to the expected principal: `GET /api/me` with a real bearer.
3. `GET /api/shelf` shows the components and the right `youMaySign` for an owner and for an AI security engineer.
4. The record's volume survives a task restart: a brief saved before is there after.
5. The audit export lands in the bucket with a verifying head.
