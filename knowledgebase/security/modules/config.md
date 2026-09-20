# Security review sheet: Settings, contract and models

| | |
| --- | --- |
| Module id | `config` |
| Kind | backend |
| Code | `kb_librarian/__init__.py`, `kb_librarian/config.py`, `kb_librarian/kbconfig.py`, `kb_librarian/models.py`, `kb.config.yaml`, and the backend dependency set `pyproject.toml` + `poetry.lock` (a supply-chain change moves this module's version) |
| Tests | `tests/test_config_models.py` |
| Depends on | pydantic, pydantic-settings, PyYAML |

## Purpose

Runtime settings read from the process environment (`LibrarianSettings`, prefix `KB_`), the
knowledge-base contract (`kb.config.yaml` validated into `KbConfig`) and the persisted models
(`Finding`, `ToolCall`, `LibrarianAction`, `ManualReviewItem`, `AuditReport`).

## Entry points

- `LibrarianSettings()` — constructed by the CLI, the API factory and the chat/translate runners.
- `load_kb_config(path)` / `find_kb_root()` — the contract; `find_kb_root` walks up from cwd.
- Models are constructed by checks, tools, the runner and the report store.

## Trust boundaries

- The environment is trusted (it is the secret manager's output). `env_file=None`: a `.env` in
  the working directory is **never** read, so a stray file cannot flip a gate.
- `kb.config.yaml` is trusted repository content, reviewed like code.
- Model instances are built from trusted code paths; `AuditReport` is also re-validated from
  JSON on disk under `.librarian/reports/` (runtime state written by this process only).

## Data handled

Internal configuration. `api_key`, `atlassian_api_token` and `embed_api_key` are `SecretStr`
(repr-redacted). No personal or customer data.

## Secrets

`KB_API_KEY` (operator bearer key), `KB_ATLASSIAN_API_TOKEN`, `KB_EMBED_API_KEY` (the embedding
endpoint's key). All `SecretStr`, exposed only via `get_secret_value()` at the point of use
(`deps.operator_key`, `AtlassianClient.from_settings`, `retrieval.embedder.embedder_from_settings`).
Block R (`embed_url`, `embed_model`, `embed_api_key`, `embed_dim`): `embed_url` passes the same
https-only validator as the IdP URLs and requires `embed_model` (`_model_with_endpoint`); unset means
the offline hash embedder and no network call.
Model credentials (`ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN`) are read by the Agent SDK,
never by this module.

## External calls

None.

## Mutations

None. `resolve_dry_run()` is the **server-side live gate**: unless `KB_ALLOW_LIVE=true`, every
run is forced to dry-run whatever the caller asked.

## Controls in place

- Gates default closed: `allow_live=False`, `atlassian_allow_write=False`.
- Numeric ceilings validated (`gt=0`): turns, budgets, daily budget, problem-report cap.
- `extra="ignore"`: unknown `KB_*` variables cannot inject fields.
- `yaml.safe_load` only; contract validation fails closed on any shape error; section ids unique.
- Settings docstring states the `.env` rule; CLAUDE.md forbids code paths that bypass the gates.

## Residual risks and reviewer attention points

- Anyone who can set the process environment controls the gates — by design; confirm the
  deployment restricts who can edit the container/env definition.
- Default model is a paid model; budgets are enforced between turns by the SDK (one turn can
  overshoot the cap).
- `find_kb_root` picks the nearest `kb.config.yaml` upward from cwd: running the CLI inside an
  untrusted directory would use that directory's contract. The API is started with an explicit root.

## Reviewer checklist

- [ ] `env_file=None` still present; no `.env` loading anywhere in the package.
- [ ] `resolve_dry_run` unchanged and the only place `allow_live` is consulted for mode.
- [ ] No new `SecretStr` field is logged, serialised or returned by an endpoint.

## Sign-off

Submit with `kb-librarian security submit config`; the reviewer records the decision with
`kb-librarian security sign config …`, which appends a row here and to `security/signoffs/config.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
