# <service> runbook

For the engineer on duty for <service> itself. <One sentence: what it is, where its record lives, its inputs and
outputs.>

## 1. Health

`GET /health` (no auth) returns `{ok, increment, mode, chain_head}`. A change of `chain_head` between two calls
means work happened. `GET /metrics` returns the outcome metrics and the connector call and disagreement counts; a
disagreement count above zero on a release is a stop-ship.

Logs carry ids only: incident, session, turn, tool, stop reason. There is no free text in a log line by
construction; if you see any, that is a Security incident.

## 2. The gates

Every request passes the team gate (`<TEAM_GATE_GROUP_IDS>`) and the operator gate (`<OPERATOR_GROUP_ID>`). A person
refused by a gate gets one reply and nothing runs. To add an engineer: add them to the operators group. To let a
team use the service: add the team's group id and redeploy. The gates fail closed: an empty setting refuses everyone.

## 3. Kill switches

Scopes: `run` (one session), `board` (one service), `consumer` (all of it; quorum of two). From the console:
`POST /api/kill {"scope":"board","target":"<service>"}` with an operator token. A stop lands at the next hook
(within one call), is recorded, and the room shows it. Clearing is a reviewed change; there is no route for it.

## 4. Rotation

Secrets are read by name at call time and cached for five minutes: rotate the value in the vault and nothing
restarts. Rotate the internal issuer secret only with a restart: outstanding confirmations bind to sessions whose
tokens die with the old secret, which is the intended effect of a compromise rotation. The catalog signing key
re-signs the catalog on restart; a session admitted under the old hash refuses to resume.

## 5. Degraded modes and running without <service>

| Loss | What happens | What you do |
| --- | --- | --- |
| <chat surface> | Posts fail with a typed stop; the record and the console keep working | Work from the console; post by hand; posting resumes when it returns |
| <paging system> | Writes fail with a typed stop; a consumed confirmation is not re-run | Act in the system by hand; re-request later; the timeline keeps the failed attempt |
| The model | The first read is "unavailable" with a typed stop; the room is assembled; the reads are in the record | Read the sources on the console; set the engine to rules mode and restart if persistent |
| <observability> | The read is partial and says which source is missing | Watch by hand; restart the watch when it returns |
| The record volume | The health check fails and the service stops | Restore the volume; run the verify command before returning to service |
| <service> itself | Nothing happens automatically; the paging system still pages | The process without it: <steps>. When it returns, the incident can be opened from the replayed trigger |

The chaos drill `<command>` rehearses these rows on the fakes; run it on every release.

## 6. Raising the increment

`<INCREMENT>` goes 1 → 2 → 3, never skipped, each after its demonstration is accepted. Raising it changes the signed
catalog (more tools). Lowering it is the fastest way to remove all write tools.

## 7. Evidence

`GET /api/<record>/<id>/trace` returns the chain records of one turn; `<verify command>` walks the whole chain.
