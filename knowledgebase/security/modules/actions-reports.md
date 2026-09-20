# Security review sheet: Action log, snapshots, rollback and report persistence

| | |
| --- | --- |
| Module id | `actions-reports` |
| Kind | backend |
| Code | `kb_librarian/actions.py`, `kb_librarian/reports.py` |
| Tests | `tests/test_actions_tools.py`, `tests/test_review_round*.py` |
| Depends on | pydantic |

## Purpose

`ActionLog` is the **only** writer of pages: every change is recorded as a `LibrarianAction`
with before/after SHA-256, full-text snapshots under `.librarian/snapshots/`, compare-and-swap
against the text the caller read, and rollback. `ReportStore` persists audit reports
(`.librarian/reports/<id>.json|.md`) after redaction and indexes them for the API.

## Entry points

`ActionLog.write_page(...)`, `ActionLog.rollback(action_id, reason, force=)`,
`ReportStore.save/load/entries/latest/latest_completed`, `render_markdown`.

## Trust boundaries

Called by write tools (agent-driven, behind the permission gate), by the translate sync, by the
CLI `rollback` and by the operator-only API rollback route. `rel_path` may originate from the
model; `_resolve()` refuses any path that resolves outside the docs root.

## Data handled

Page text (Internal tier) in snapshots; report JSON containing findings, tool inputs, action
descriptions and the model's summary. **Page text never enters a report** — only hashes.

## Secrets

None. Every string leaf of a report is passed through `checks.sensitive.redact` before saving.

## External calls

None (filesystem under `.librarian/` and `docs/` only).

## Mutations

- `write_page`: in **dry-run** records the action and both snapshots, touches nothing under
  `docs/`. Live: writes the page after a CAS check (`expected_text`).
- `rollback`: refuses dry-run proposals, already-rolled-back actions, missing/hash-mismatched
  snapshots, and (unless `force`) a page changed since the action.

## Controls in place

- Path confinement (`_resolve`), CAS on write, hash-verified snapshots on rollback.
- Dry-run decided by `report.dry_run`, which came from `resolve_dry_run` — the tool cannot pass
  its own mode.
- Reports are redacted on save; the markdown rendering carries no tool inputs; the index
  tolerates corrupt/half-written files without failing.

## Residual risks and reviewer attention points

- Snapshots hold full page text; `.librarian/` must stay on a protected volume and out of git
  (it is git-ignored; the container keeps it on a named volume).
- `force=True` rollback overwrites a page edited after the action; only operators can request
  it, with a ≥10-character reason recorded.
- Rollback restores a page but not derived artefacts (e.g. an index regenerated afterwards).

## Reviewer checklist

- [ ] `_resolve` still refuses parents outside `docs_root`; symlink behaviour understood.
- [ ] `sanitized()` applied on every save path.
- [ ] No report field carries page text.

## Sign-off

Submit with `kb-librarian security submit actions-reports`; the reviewer records the decision with
`kb-librarian security sign actions-reports …`, which appends a row here and to `security/signoffs/actions-reports.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
