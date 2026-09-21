# Runbook: the collection's deployables

Two services run: `ai-hub` (hub-api and the hub) and `agent-incident-first-read` (the agent runtime). Both are one
container each, a record on a persistent volume, and a fail-closed entrypoint. Logs carry ids and route
templates, never content.

## Health

- Hub: `GET /api/health` → `{"status":"ok","build","env","auth","assistant","components","record"}`. `record: "memory"` in staging or production is a misconfiguration; the entrypoint should have refused it.
- Agent: `GET /health` → the wiring by name (`identity`, `signing`, `engine`, `targets` as class names) and `records`, the chain's length after a verify. A fake class name in production is a misconfiguration.
- Readiness, for the load balancer and the task health check: `GET /api/ready` and `GET /ready` answer 200 with each check named (`record`, `identity`, `catalog`, and the hub's `guide`) or 503 with the failing check's exception class. A task that is up but not ready is taken out of rotation, not restarted; the usual cause is the identity provider's key set being unreachable.
- Every response carries `X-Request-Id`: the hub's own id when it sent one, else one minted by the service. A person's support line quotes it; every log line for that request carries `rid=<id>`.
- Limits: `429 Too many requests` with `Retry-After` when one person exceeds `HUB_RATE_PER_MINUTE` or `AGENT_RUNS_PER_MINUTE`. A person seeing it steadily is a runaway client, not a capacity problem.

## When it will not start

The entrypoint prints `config: <variable>: <problem>` lines and exits 2. Fix the variable; the value is never
printed. The hub prints one `record: the record is at schema version N; this build knows M` line and exits 2
when its record was written by a newer build (every `hubapi` command does, never a traceback): restore the
record from before the newer build, or roll the build forward. `AGENT_*`: `verify-record` exits 1 on a broken
chain; do not start over it, see "The record is broken".

## A person cannot sign in

`401` from `/api/me` with a real token: the response's `detail` names the check (`aud`, `iss`, expiry, key). `403`
with `groups.overage`: the directory left the groups out of the token; the identity team filters the claim or emits
app roles, the hub never guesses. Every reload returning to sign-in: silent renew is refused, see the hub's browser
console; `offline_access` in `HUB_WEB_OIDC_SCOPE` switches renew to a refresh token. `scripts/smoke-oidc.sh`
reproduces the whole path against a stand-in provider on any machine with a Chromium.

## Common operations

| Situation | What to do |
| --- | --- |
| Roll out a new build | Build the image with the new `GIT_SHA`, update the task definition, deploy; both services are stateless beyond their volume, so a rolling deploy is safe. On SIGTERM the hub stops accepting, gives the requests in flight (a turn mid-stream) up to 25 s to finish and be written, closes the record and exits 0; give the task at least 30 s of stop grace |
| A component was signed off | Download the queue's export on the hub, `python3 tools/shelf.py --apply-signoffs`, commit, `--write`, rebuild the image (the shelf's `collection.json` is shipped in it) |
| Add a listing the hub should show | Edit `consumers.json` on the config volume and restart the hub task |
| Grant a person a role | Add their group to `identity-map.json`, or add them to the group; the hub reads the map at start |
| Change which systems the agent writes to | `AGENT_TARGETS`; a target not named is a fake and refused outside the sandbox |
| Stop the agent now | `python3 -m agentrt stop board <board> --by <your id>` (or `run <run id>`, or `consumer self`, which needs two people) sets the kill switch in the record and names you on the chain; the next hook of every run stops. `resume` votes to clear it. The commands need the record volume: run them in the task (`ecs execute-command`) or on a host that mounts it; there is no remote stop by design |
| Rotate a credential | Rotate it in the secrets provider under the same name; nothing restarts, the next call reads the new value (a five-minute cache) |
| Apply the retention now | `python3 -m hubapi prune` inside the task; `serve` does the same once a day. Conversations past `HUB_CONVERSATION_RETENTION_DAYS` go, with their feedback rows, and replays older than `HUB_IDEMPOTENCY_TTL_S`; the command prints both counts; nothing else is touched. `serve` runs it a minute after start, then daily |
| Back up the record | `python3 -m hubapi backup /var/hub/backup.db` and `python3 -m agentrt backup /var/agent/backup.db` inside the task (SQLite's online backup: consistent while serving), then copy the file off the volume; restore by stopping the task and putting the file back as the record (remove `<record>-wal` and `<record>-shm` first, see "The record is broken"). `hubapi backup` opens the source read-only and refuses a `HUB_DB` that is not an existing file, so a typo never backs up an empty record or migrates the live one. A record from a newer build refuses to open under an older one (the hub's refusal is the `record:` line above); restore before rolling back |
| Export the chain | `python3 -m agentrt export-audit` inside the task, or set `AGENT_AUDIT_EXPORT_INTERVAL_S` and the task exports itself (a failed export is logged and retried at the next interval; the chain stays local meanwhile); `latest.json` in the bucket points at the newest object |

## The record is broken

`verify-record` fails when a row was edited or removed. Do not repair rows. Restore the volume from its last
snapshot, compare the chain's head with the last `latest.json` in the bucket, and open an incident: a chain that
does not verify is a security event.

When putting a restored hub record back: stop the task, remove `<record>-wal` and `<record>-shm` before putting
the file back, then start. A stale `-wal` beside a restored file is replayed over it at the next open (the old
writes come back on top of the restore). A clean stop checkpoints and removes both files; a killed task leaves them.

## Upstream outages

The connectors raise typed errors; the harness records `handler.errors` and the run answers 502 with the
session id. Nothing is retried on a write. When the system is back, the person runs again; the parked write (if
any) was never sent.

## Escalation

The hub's footer names the office hour and the platform lead; the agent's owner is the manifest's `owner`.
