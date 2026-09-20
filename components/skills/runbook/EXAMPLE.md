> A live example of the skill: the first responder's real document at its 2026-09-19 snapshot, with product and company names made neutral. Every row was true of that codebase on that date.

# the responder runbook

For the SRE on duty for the responder itself. the responder is one container; its record is a SQLite file on EFS; its inputs are
PagerDuty webhooks, Teams messages and console requests; its outputs leave only through connector tools recorded on
the chain.

## 1. Health

`GET /health` (no auth) returns `{ok, increment, mode, chain_head}`. A change of `chain_head` between two calls means
work happened. `GET /metrics` (console bearer) returns the outcome metrics and the connector call and disagreement
counts; a disagreement count above zero on a release is a stop-ship (the action loop and the connector boundary
evaluated the same rule set differently).

Logs (CloudWatch `/ecs/responder-responder`) carry ids only: incident, session, turn, tool, stop reason. There is no
incident text in a log line by construction; if you see any, that is a Security incident (MEG-18).

## 2. The gates

Every request through the bot passes the team gate (the team's AAD group id in `APP_TEAM_GATE_GROUP_IDS`) and the
operator gate (transitive membership of `APP_OPERATOR_GROUP_ID` through Graph `checkMemberGroups`). A person refused
by a gate gets one reply and nothing runs. To add an engineer: add them to the operators group. To let a team use
the responder: add the team's group id and redeploy. The gates fail closed: an empty setting refuses everyone.

The console verifies the company IdP token and maps its `groups` claim the same way; the service-owner groups per service
are in `APP_OWNER_GROUPS`.

## 3. Kill switches

Scopes: `run` (one session), `board` (one service), `consumer` (all of the responder; quorum of two actors). From the console:
`POST /hub/api/kill {"scope":"board","target":"payments-api"}` with an operator token. A stop lands at the next
hook (≤ one call), is recorded, and the room shows it; a pending confirmation under a stopped scope is refused.
Clear with the core's `kills.clear` (a Hub route for clearing is deliberately absent: clearing is a reviewed
change).

## 4. Rotation

Secrets are read by name at call time from Secrets Manager and cached for five minutes: rotate the secret value in
Secrets Manager and nothing restarts. Rotate the internal issuer secret (`responder/internal-issuer`) only with a
restart: outstanding confirmations bind to sessions whose tokens die with the old secret, which is the intended
effect of a compromise rotation. The catalog signing key (`responder/catalog-signing`) rotation re-signs the catalog on
restart; a session admitted under the old catalog hash refuses to resume (the harness's rule) and its pending
confirmations must be re-requested.

## 5. Degraded modes and running an incident without the responder

| Loss | What happens | What you do |
| --- | --- | --- |
| Teams (Graph or the connector) | Assembly and posts fail with a typed stop (`handler.errors`); the record and the console keep working; reads still run from the console | Run the incident from the console page and PagerDuty; post to the room by hand; the responder resumes posting when Teams returns |
| PagerDuty | Reads and acks fail with a typed stop; a consumed confirmation is not re-run (act once) | Acknowledge in PagerDuty by hand; re-request the action in the responder later; the timeline keeps the failed attempt |
| The engine (the ask engine or Bedrock) | The first read is "unavailable" with a typed stop `vendor.refusal`; the room is assembled; the reads are in the record | Read the sources on the console incident page; `@the responder ask` returns the refusal until the engine is back. If `APP_ENGINE=bedrock`, the failure is a Bedrock Converse timeout or error; same stop, same recovery path |
| Bedrock (model timeout/error mid-incident) | If Bedrock fails after assembly and first read, subsequent asks/proposals are stopped with `vendor.refusal`; the first-read finding is preserved in the record and the Hub; the room stays assembled | Work from the Hub incident page and the reads already collected; no model fallback happens automatically (fail-closed, not fail-over). If persistent, set `APP_ENGINE=deterministic` and restart to return to rules-based reads |
| Observability (New Relic, Elastic, CloudWatch) | The correlated read is partial; the first read says which source is missing; watches end with "read denied" | Watch by hand; restart the watch when the source is back |
| The record volume (EFS) | The service fails its health check and stops; nothing runs without the record | Restore the volume; `python3 -m responder verify /var/responder/meg.db` before returning to service |
| the responder itself | Nothing happens automatically; PagerDuty still pages | The incident process without the responder: PagerDuty for the page and acks, a channel by hand, the runbook from Confluence, the postmortem template from the incident process. When the responder returns, the incident can be opened from the webhook's replay (`incident.triggered` is idempotent per PagerDuty id) |

The chaos drill `python3 -m responder chaos` rehearses these rows on the fakes, including a Bedrock-specific engine failure mid-incident drill; run it on every release.

## 5b. Engine selection

`APP_ENGINE` chooses the think engine: `deterministic` (rules, offline/tests), `http` (the ask engine), or `bedrock`
(Claude via Amazon Bedrock Converse). If unset, the engine is inferred from `APP_ENGINE_URL` (backward compatible).
When `APP_ENGINE=bedrock`, the additional `APP_BEDROCK_*` settings are required in live mode (fail-closed).

To switch engines in production: set `APP_ENGINE`, add or remove the Bedrock config vars, and restart. The engine
selection is a configuration change, not a code change. Bedrock access is SigV4 from the task role (no API keys).

## 5c. Ambient teammate

The ambient teammate (`APP_AMBIENT=on`) follows the war-room conversation and may contribute unprompted. It is off
by default (fail-closed). In `observe` mode it records decisions without posting; in `suggest` mode it posts cited
suggestions under anti-spam caps.

| Control | Env var | Operator action |
| --- | --- | --- |
| Master switch | `APP_AMBIENT` | `on` / `off` (default `off`); a restart changes the mode |
| Mode | `APP_AMBIENT_MODE` | `observe` (record only) / `suggest` (may post) |
| Commander mute | `@the responder quiet` command or card toggle | Silences ambient for the incident; `@the responder speak` restores it |
| Per-incident cap | `APP_AMBIENT_MAX_PER_INCIDENT` | Maximum ambient posts per incident (default 5) |
| Per-hour cap | `APP_AMBIENT_MAX_PER_HOUR` | Global rate limit across incidents (default 20) |
| Cooldown | `APP_AMBIENT_COOLDOWN_S` | Minimum seconds between ambient posts per incident (default 120) |
| Confidence floor | `APP_AMBIENT_MIN_CONFIDENCE` | Below this threshold ambient stays silent (default 0.6) |

Ambient metrics (evaluations, spoke/silent rates, suppression ratio, token spend) are exposed on `/hub/metrics`
and via the metrics API. Every ambient decision is recorded on the chain with a machine-readable reason.

Quiet hours: not implemented yet; set `APP_AMBIENT=off` during maintenance windows.

## 6. Raising the increment

`APP_INCREMENT` goes 1 → 2 → 3, never skipped, each after its demonstration (`HANDOVER.md`) is accepted. Raising it
changes the signed catalog (more tools) and, for 3, needs the task tag `responder-increment=3` for the ECS mitigation
permissions and `APP_COMMS_GROUP_ID` for customer status. Lowering it is the fastest way to remove all W tools.

## 7. Evidence

`GET /hub/api/incidents/<id>/trace` returns the chain records of one incident; `python3 -m responder verify <db>`
walks the whole chain and every incident's projection; the postmortem page carries the chain head at drafting.
