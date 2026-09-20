# Runbook: the collection's deployables

Two services run: `ai-hub` (hub-api and the hub) and `agent-incident-first-read` (the agent runtime). Both are one
container each, a record on a persistent volume, and a fail-closed entrypoint. Logs carry ids and route
templates, never content.

## Health

- Hub: `GET /api/health` → `{"status":"ok","env","auth","assistant","components","record"}`. `record: "memory"` in staging or production is a misconfiguration; the entrypoint should have refused it.
- Agent: `GET /health` → the wiring by name (`identity`, `signing`, `engine`, `targets` as class names) and `records`, the chain's length after a verify. A fake class name in production is a misconfiguration.

## When it will not start

The entrypoint prints `config: <variable>: <problem>` lines and exits 2. Fix the variable; the value is never
printed. `AGENT_*`: `verify-record` exits 1 on a broken chain; do not start over it, see "The record is broken".

## Common operations

| Situation | What to do |
| --- | --- |
| Roll out a new build | Build the image with the new `GIT_SHA`, update the task definition, deploy; both services are stateless beyond their volume, so a rolling deploy is safe |
| A component was signed off | Download the queue's export on the hub, `python3 tools/shelf.py --apply-signoffs`, commit, `--write`, rebuild the image (the shelf's `collection.json` is shipped in it) |
| Add a listing the hub should show | Edit `consumers.json` on the config volume and restart the hub task |
| Grant a person a role | Add their group to `identity-map.json`, or add them to the group; the hub reads the map at start |
| Change which systems the agent writes to | `AGENT_TARGETS`; a target not named is a fake and refused outside the sandbox |
| Stop the agent now | The kill switch is in the record: `python3 -m agentrt` has no remote stop by design; scale the service to zero, then set the kill switch through the harness before scaling back (`actionloop.kill`) |
| Rotate a credential | Rotate it in the secrets provider under the same name; nothing restarts, the next call reads the new value (a five-minute cache) |
| Export the chain | `python3 -m agentrt export-audit` inside the task (a scheduled task nightly); `latest.json` in the bucket points at the newest object |

## The record is broken

`verify-record` fails when a row was edited or removed. Do not repair rows. Restore the volume from its last
snapshot, compare the chain's head with the last `latest.json` in the bucket, and open an incident: a chain that
does not verify is a security event.

## Upstream outages

The connectors raise typed errors; the harness records `handler.errors` and the run answers 502 with the
session id. Nothing is retried on a write. When the system is back, the person runs again; the parked write (if
any) was never sent.

## Escalation

The hub's footer names the office hour and the platform lead; the agent's owner is the manifest's `owner`.
