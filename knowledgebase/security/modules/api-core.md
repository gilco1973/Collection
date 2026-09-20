# Security review sheet: API application, authorisation, middleware, static console, admission

| | |
| --- | --- |
| Module id | `api-core` |
| Kind | backend |
| Code | `kb_librarian/api/__init__.py`, `app.py`, `deps.py`, `middleware.py`, `static.py`, `admission.py`, `service.py` |
| Tests | `tests/test_api_pages.py`, `tests/test_api_audits.py`, `tests/test_review_round*.py` |
| Depends on | FastAPI, Starlette, uvicorn |

## Purpose

The FastAPI application factory (`create_app`, mountable `router`), application state
(`AppState`), the two roles (`viewer`, `operator`), request-hardening middleware, the
single-page-app static mount, audit admission rules and the read-model helpers (search,
withholding, page summaries).

## Entry points

`create_app(root, settings, cors_origins)`, `kb-librarian-api` (uvicorn on `KB_API_HOST`/`KB_API_PORT`,
default `127.0.0.1:8765`), `install_security_headers(app, prefix)`, `install_error_handlers`,
`mount_console(app, dist)`, `require_operator`, `current_role`, `AppState.catalog_for(lang)`.

## Trust boundaries

- **Viewer**: anyone who can reach the port (no authentication). **Operator**, resolved once per
  request into a `Principal(role, via, user)` by `current_principal` (`auth/principal.py`): either
  the bearer token equal to `KB_API_KEY`, compared with `secrets.compare_digest` (`via = "key"`,
  checked first — break-glass), or a signed-in person whose session carries `operator = True`
  (`via = "group"`, decided by the `auth` module at sign-in from the configured IdP groups). No
  key and no operator group configured → nobody is an operator. `require_operator` answers 403
  "operator role required" otherwise; on the group path it also runs `same_origin`, because that
  path is cookie-authenticated. `Principal.requested_by` (`key`, or `user:<16 hex>` — a pseudonym keyed
  with the session secret; see the `auth` sheet) is what an audit records. **Signed-in user**: the session cookie the `auth` module issues, read by
  `current_user`/`require_user` and refused when its `epoch` differs from the reader's current
  `session_epoch` in the profile store ("sign out everywhere"); it identifies the person for
  per-user data. Because it is a cookie, `require_user` also runs `same_origin` (CSRF guard:
  `Sec-Fetch-Site` must be `same-origin`/`none`, or the `Origin` host must be ours), so a foreign
  page can neither read nor change a reader's data through their browser.
- The console is served from the same origin; CORS is off unless `KB_API_CORS_ORIGINS` names origins.
- `request.client.host` is used for throttles; uvicorn honours `X-Forwarded-For` only from
  `FORWARDED_ALLOW_IPS`.

## Data handled

Page metadata/bodies (withheld pages redacted), reports, contract. Error envelope
`{error: {code, message, request_id}}`; unhandled exceptions return a generic `internal error`.

## Secrets

`KB_API_KEY` via `settings.api_key` (`SecretStr`); compared only inside `auth/principal.py::principal_for`
(constant time), reached through `current_principal` / `role_for`.

## External calls

None.

## Mutations

None here; admission (`validate`) decides whether an audit may start: unknown capabilities →
422, budget above server ceiling → 422, a run already in flight → 409, daily ceiling
(`KB_DAILY_BUDGET_USD`, spent + reserved) → 429. Runs under `state.admission` so two requests
cannot both pass.

## Controls in place

- `BodyCap` (64 KiB, counted as chunks arrive) rejects before the app parses.
- `SecurityHeaders`: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Cache-Control: no-store` on `/api`, and on HTML the CSP
  `default-src 'self'; frame-ancestors 'none'; img-src 'self' data:; base-uri 'none'; form-action 'self'`.
- `catalog_for` is the single whitelist for `lang`; `mount_console` confines static paths to
  `dist` and never shadows `/api`.
- Withholding: `withheld_paths` = pages flagged critical/error by the latest completed audit
  **or** by their current text; withheld pages never match search, contribute no facets, and
  their metadata is redacted (`withheld_summary`). `readable_page(catalog, report, path)` is the
  one lookup the routes that must not confirm a withheld page (profile views and quiz results,
  chat context) use: unknown and withheld both come back `None` → 404.
- Orphaned in-progress reports are marked failed at start-up.

### Observability

- `RequestLog` (`observability.py`, pure ASGI, added by `install_security_headers` as the outermost
  of its three middlewares so body-cap rejections and error responses are covered): a client
  `X-Request-ID` is accepted only when it matches `^[A-Za-z0-9._-]{1,64}$`, otherwise replaced by
  `uuid4().hex[:16]`; the id is stored in `request.state.request_id`, echoed on every response, and
  `_error` puts the same id in the envelope and the header (so a 500 built outside the middleware
  carries it too).
- One access line per request on logger `kb_librarian.api.access` with `method, path, status,
  duration_ms, request_id, client` (`request.client.host`) — never a header value, a cookie, a bearer
  token or the query string.
- `configure_logging(settings)` sets the root logger once from `KB_LOG_LEVEL` (DEBUG/INFO/WARNING/ERROR)
  and `KB_LOG_FORMAT` (`json`: `ts, level, logger, msg` + the record's extras, `exc` on exceptions; or
  `text`). Idempotent — a second call re-targets the same handler — and called by `create_app` and by
  the CLI's `main`. `kb-librarian-api` runs uvicorn with `log_config=None, access_log=False` so every
  line goes through it.
- `GET /api/health` (liveness) is always 200 with `status`, the package `version` and
  `checks: {process: true}`; it touches no disk. `GET /api/health/ready` (readiness) is 200 when the
  catalog loads and `.librarian/` accepts a file (`probe_writable`: create and delete a temp file),
  else 503 `{"status": "not_ready", "version", "checks"}`. Check values are booleans; a load failure
  is logged server-side and never described in the response (no path, hostname or secret).

- The shared operator key remains as break-glass beside the IdP-group path (`auth` sheet);
  its use is attributed as `requested_by = key` only. Leave `KB_API_KEY` unset once every
  operator signs in through a group.
- The viewer role is unauthenticated by design (Internal-tier content behind the platform's
  network perimeter); confirm the ingress enforces the perimeter.
- `/api/docs` and `/api/openapi.json` are exposed to viewers.
- CSP has no `script-src` nonce; Vite emits no inline scripts, so `'self'` suffices today.

## Reviewer checklist

- [ ] `require_operator` on every mutating route (audits start/cancel/rollback).
- [ ] `compare_digest` still used; no logging of the presented token.
- [ ] Middleware order: BodyCap innermost, SecurityHeaders outside it; CSP unchanged or justified.

## Sign-off

Submit with `kb-librarian security submit api-core`; the reviewer records the decision with
`kb-librarian security sign api-core …`, which appends a row here and to `security/signoffs/api-core.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
