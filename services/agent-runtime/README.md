# agent-runtime

One agent of the collection, deployed: served over MCP and a small run API, wired to the bank's systems by
configuration, with fakes for the sandbox that production refuses.

## What it does

| Area | Behaviour |
| --- | --- |
| The agent | `incident-first-read-agent`, vendored: its `TEMPLATE.md` is the catalog, its `agent.py` the loop's client. `/runs` runs a first read (read the ticket and the last deploy, think, propose, park the W1 comment); `/runs/{session}/confirm` posts it once the person confirms the exact hash |
| MCP | `mcp-tool-server`'s transport on `/mcp`: the template's tools, W1 as elicitation, taint and scope as 403, RFC 9728 metadata, sampling disabled |
| Identity | `AGENT_IDENTITY=oidc`: the bank's RS256 tokens through the JWKS (`JwksIdP`), directory groups to the operator and approver roles; `fake` in the sandbox |
| Signing | `AGENT_SIGNING=kms`: the catalog and rule bundle signed and verified on an asymmetric KMS key from the task role; `local` in the sandbox |
| The think step | `AGENT_ENGINE=bedrock`: the cited engine behind Bedrock Converse through the VPC endpoint, the template's role as the system prompt; `rules` in the sandbox |
| Targets | `AGENT_TARGETS` names which of the template's targets are real: `tickets` is the Jira connector, `deploys` the Azure DevOps connector, each with a credential by name; the rest are the fakes, refused in staging and production |
| The record | SQLite on a persistent volume; `verify-record` walks the chain at every start; `export-audit` puts the chain and a `latest.json` pointer to S3 with SigV4; the pointer only moves forward (a chain shorter than the last export, or one the last head is not on, is refused) |
| Health, logs | `/health` names the wiring (never a value); logs carry ids only |

## Run it

```
cd services/agent-runtime
python3 -m unittest discover -s tests -t .        # the sandbox end to end, the bank wiring with doubles, the refusals
python3 -m agentrt check-config
python3 -m agentrt serve                          # sandbox: fake identity, local key, rules, fake targets
TOKEN=$(python3 -m agentrt token u_dana)
curl -s -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"ticket_key":"INC-7","service":"checkout"}' http://127.0.0.1:8081/runs
```

Against the bank: the `AGENT_` block of `config/collection.env.example`; `CONFIGURATION.md`; `deploy/`.

## Files

| File | What it is |
| --- | --- |
| `agentrt/settings.py` | Configuration that fails closed; production refuses every fake and requires a real system for every target the template names |
| `agentrt/wiring.py` | `build(settings)`: the harness from the template with the identity provider, key, engine and targets the settings choose; injection points for tests |
| `agentrt/app.py` | `/health`, `/runs`, `/runs/{session}/confirm`, and the MCP transport |
| `agentrt/export.py` | The chain to S3 |
| `agentrt/vendor/` | Copies from components (`services/vendor.json`) |
| `deploy/` | Dockerfile, fail-closed entrypoint, ECS task definition, task role policy |

## Adding another agent

A second agent of the collection is a second vendored template and client behind the same wiring; `KNOWN_AGENTS`
and `CONNECTORS` in `settings.py` name what the runtime knows how to serve, `template_targets()` reads what the
agent's template names from the vendored `TEMPLATE.md`, and a target the template names that has no connector is
a build failure, not a fake in production.
