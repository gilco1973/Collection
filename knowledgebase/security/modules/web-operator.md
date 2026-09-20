# Security review sheet: Operator pages

| | |
| --- | --- |
| Module id | `web-operator` |
| Kind | frontend |
| Code | `web/src/pages/Audits.tsx`, `AuditDetail.tsx`, `RunAudit.tsx`, `Rollback.tsx`, `Settings.tsx`; `components/AuditHeader.tsx`, `AuditParts.tsx`, `AuditTrail.tsx`, `ConfirmWithReason.tsx`, `Badges.tsx`, `States.tsx`, `Tabs.tsx`, `InsightsPanel.tsx` |
| Tests | `web/src/test/operator.test.tsx`, `web/src/test/authz.test.tsx`, `web/src/test/insights.test.tsx`, `web/src/test/round*.test.tsx` |
| Depends on | `web-api-client`, `web-markdown` |

## Purpose

Audit list and detail (findings, actions, review queue, tool trail, model summary), starting
an audit (type, dry-run/live, capabilities, ceilings, reason), cancelling, rolling an action
back with a reason (and explicit force), and Settings (identity — signed-in name, "Sign out",
"Sign out everywhere" with its one-line help — the persona card for signed-in readers — the
`PersonaPicker` reviewed under `web-reader` — "your data", operator key, UI language, contract
view, and the "Suggestions" switch — `SuggestionsToggle`, whose state is the `kb.nudges.<hash>`
browser-storage entry reviewed under `web-shell`). "Delete my data" also calls `clearNudgeState`
so that entry goes with the server-side record. The role row states how the operator role was
granted (`operator_via`: the operator key or the identity provider group); it is informational.

The Audits page carries, for operators only, an **Insights** tab (`InsightsPanel`, `?tab=insights`):
three tables from `GET /api/insights` — pages by problem reports, pages by quiz fail rate,
unanswered questions by mode and language — a "Refresh" button (`POST /api/insights/refresh`),
an empty state until a run generated the file (the API's 404 is rendered as "No insights yet"),
and a note that reader-derived numbers are hidden for pages below `k` readers (such cells read
"hidden"). Everything shown is a page path, a count or a rate; no reader, message or problem text
reaches the console. A viewer gets no tab and the panel's query never fires.

## Entry points

Routes `/audits` (`?tab=insights` for operators), `/audits/new`, `/audits/:id?tab=…`,
`/audits/:id/actions/:actionId/rollback`, `/settings`.

## Trust boundaries

Viewers never see the audit-running UI: the Audits menu entry, the home page's "Run an audit"
link and "Keep it healthy" band are operator-only, and `/audits/new` shows a viewer only the
operators-only notice (no form). Cancel/rollback controls are likewise hidden from viewers and
the live option is locked when the server reports `live_allowed: false`. **Authorisation is
server-side** (`require_operator`); these are presentation choices, not controls.

## Data handled

Reports (redacted server-side), including the model's summary and tool inputs in the trail;
the operator key typed into Settings (password field, `autoComplete="off"`, stored in `localStorage`).

## Secrets

The operator key (see `web-api-client`). It is never displayed after saving except as a masked
field value the operator typed in this session.

## External calls

None beyond the API client. Export links point at `/api/audits/{id}/export`.

## Mutations

Start audit, cancel audit, rollback (with reason ≥ 10 chars; `force` is a separate explicit
checkbox), save/clear the key (local only), sign out, sign out everywhere (server-side
revocation of every session of the reader; a plain button, no confirmation — it is reversible by
signing in again and destroys no data).

## Controls in place

- The model's summary renders through `Markdown` with `plainLinks`: **links in model-authored
  text are never clickable**.
- Tool trail shows tool name, input and summary as text; read-tool responses are lengths only
  (server-side rule).
- `ConfirmWithReason` requires a reason before a live or destructive action is sent.
- `forced_dry_run` from the server is surfaced as a notice so an operator sees a downgraded run.
- Tab state is in the URL and validated against a fixed list.

## Residual risks and reviewer attention points

- Tool inputs chosen by the model (e.g. `reason`, JSON `fields`) are shown to operators as
  text; a crafted page could steer the model into writing misleading text there — social
  engineering of the operator, not code execution.
- Settings stores the key in the browser (shared machines: clear it).

## Reviewer checklist

- [ ] `plainLinks` on every render of model-authored text.
- [ ] Rollback UI sends `force` only when the checkbox is explicitly ticked.
- [ ] No operator-only control is the sole guard for a server action.

## Sign-off

Submit with `kb-librarian security submit web-operator`; the reviewer records the decision with
`kb-librarian security sign web-operator …`, which appends a row here and to `security/signoffs/web-operator.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
