# Security review sheet: Operator endpoints

| | |
| --- | --- |
| Module id | `api-audits` |
| Kind | backend |
| Code | `kb_librarian/api/routes_audits.py` |
| Tests | `tests/test_api_audits.py`, `tests/test_review_round*.py` |
| Depends on | `api-core` (admission, `require_operator`), `agent`, `actions-reports` |

## Purpose

`GET /api/audits` (list, paginated, filterable), `GET /audits/{id}`, `GET /audits/{id}/export?format=json|md`
(any role: reports are redacted at save time), and the **operator-only** `POST /audits`
(start dry-run/live, agent/offline), `POST /audits/{id}/cancel`, `POST /audits/{id}/actions/{action_id}/rollback`.

## Entry points

The routes above. `require_operator` is a dependency on every `POST`.

## Trust boundaries

Operators hold the shared `KB_API_KEY`. Even an operator cannot obtain a live run unless the
server has `KB_ALLOW_LIVE=true`: `resolve_dry_run` is applied first and the response reports
`forced_dry_run` when the request was downgraded. A live run requires a non-empty `reason`.

## Data handled

Audit reports (findings, actions with hashes, tool inputs, model summary, cost) — redacted
JSON on disk, served as-is. Rollback reasons (10–500 chars) stored on the action.

`requested_by` on a report is `key` (the shared key) or `user:` plus 16 hex digits of the
reader-record digest — a pseudonym viewers may see; the subject itself goes only to the server log
(`audit … requested by … (subject …)`), which operators read.

## Secrets

None.

## External calls

Starting an agent audit calls the model API (via `agent`), and optionally external link
checks (`network: true`) and Atlassian — only through the audit's own tools.

## Mutations

- Start: creates a report; a **live** run may edit pages through the action log.
- Cancel: sets the cancel marker/flag; cancels the in-process task; a run owned by no process
  in this API is recorded as failed so the console stops waiting.
- Rollback: `ActionLog.rollback` under a per-audit lock; only on terminal audits; 404/409 mapped
  from `KeyError`/`ValueError`; `force` explicit.

## Controls in place

- Admission is single-flight (`state.admission`) with reserved budgets so a second request
  cannot slip in while the first is registering; 30 s start timeout → 503.
- `StartAudit` validates `type`, `capabilities` (non-empty when given), `max_turns` 1–200,
  `max_budget_usd > 0` and ≤ server ceiling, `reason` ≤ 500.
- Export serves only files the store wrote, by validated `format`, from the reports directory.

## Residual risks and reviewer attention points

- Report detail (including tool inputs the model chose, e.g. a `reason`) is readable by
  viewers; content is redacted but is model-authored free text.
- Cancel is cooperative: the next tool call is denied; a turn already in flight completes.
- The shared key attributes an action to `key`, not a person; a group operator is attributed by
  pseudonym on the report and by subject in the server log only.

## Reviewer checklist

- [ ] `require_operator` present on start/cancel/rollback; none on reads is intentional.
- [ ] `resolve_dry_run` precedes admission; `forced_dry_run` reported.
- [ ] Rollback holds `lock_for(audit_id)` and re-saves the report after the change.

## Sign-off

Submit with `kb-librarian security submit api-audits`; the reviewer records the decision with
`kb-librarian security sign api-audits …`, which appends a row here and to `security/signoffs/api-audits.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
