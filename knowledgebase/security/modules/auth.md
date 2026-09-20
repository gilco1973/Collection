# Security review sheet: Enterprise identity (OpenID Connect) and sessions

| | |
| --- | --- |
| Module id | `auth` |
| Kind | backend |
| Code | `kb_librarian/auth/` (`oidc.py`, `session.py`, `principal.py` — a leaf package: protocol, cookie codec, role decision), `kb_librarian/api/routes_auth.py` (the HTTP surface) |
| Tests | `tests/test_auth.py`, `tests/test_auth_routes.py`, `tests/test_authz_groups.py`, `tests/test_session_epoch.py`, `tests/fake_idp.py` (fake IdP behind `httpx.MockTransport` with an RSA test key; its token endpoint verifies grant type, redirect URI, client auth and the PKCE verifier; a test sets the group claim it issues) |
| Depends on | PyJWT (`pyjwt[crypto]`), httpx, `config.is_secure_url`, `api-core` (`current_user`, `current_principal`, `require_user`, `require_operator`, `same_origin`), `profile` (`ProfileStore.session_epoch` / `bump_session_epoch`) |

## Purpose

Sign-in against the organisation's identity provider with OpenID Connect (authorization code
flow + PKCE S256), verification of the ID token, and a stateless HMAC-signed session cookie that
identifies the reader to the API. Identity is what per-user features (progress, persona) hang on,
and — when `KB_OIDC_OPERATOR_GROUPS` is set — what grants the operator role. `principal.py`
decides the role for a request (shared key, or the session's operator flag) without any request
or app state. Revocation before expiry exists: a per-reader session epoch.

## Entry points

`GET /api/auth/login?next=` → 302 to the IdP; `GET /api/auth/callback?code&state` → 302 to
`next` with the session cookie; `POST /api/auth/logout` → 204 (same-origin only);
`POST /api/auth/logout-everywhere` → 204 (`require_user`: signed-in and same-origin; bumps the
reader's epoch, clears this browser's cookie). `current_user` / `current_principal` /
`require_user` / `require_operator` / `same_origin` in `api/deps.py`; `Principal` and
`principal_for` in `auth/principal.py`; `/api/me` reports `user` (with `operator`),
`sso_configured`, `role` and `operator_via` (`key` | `group` | null).

## Trust boundaries

- The IdP is trusted **after** verification: discovery document's `issuer` must equal
  `KB_OIDC_ISSUER` and its `authorization_endpoint`/`token_endpoint`/`jwks_uri` must be https
  (http only to localhost); the ID token must be signed by a key from `jwks_uri`, with an allowed
  asymmetric algorithm (`RS*/ES*/PS256` — never `none`/HMAC; the key object is asymmetric so
  key-confusion is not constructible), `aud` = client id (several audiences need `azp` = client id),
  `iss` = issuer, `exp`/`iat`/`sub` present (30 s leeway), and carry the `nonce` this server generated.
- The browser is untrusted: `state` binds the callback to the login that started in the same
  browser (signed `kb_login` cookie, 10 min, `kind=login`), PKCE binds the token exchange to that
  login, and the session cookie is only accepted when its HMAC verifies with `KB_SESSION_SECRET`,
  its `kind` is `session` and it is unexpired. Any malformed cookie or `state` (bad base64,
  non-ASCII bytes, wrong kind) reads as anonymous, never as an error.
- Cookie-authenticated **mutations are CSRF-guarded**: `same_origin` rejects a request whose
  `Sec-Fetch-Site` is not `same-origin`/`none`, or whose `Origin` host differs from ours (403);
  it is part of `require_user` and of logout.
- Sign-in is **absent** (404) unless issuer, client id, redirect URI and session secret are all set.
  Settings refuse a non-https issuer/redirect URI and a session secret under 32 characters.
- **Operator role from groups**: at the callback, the claim named by `KB_OIDC_GROUPS_CLAIM`
  (default `groups`) is read from the *verified* ID-token claims; only a list of strings counts
  (absent, another type, or a list with a non-string → no groups); `operator` is true when it
  intersects `KB_OIDC_OPERATOR_GROUPS` (comma-separated; empty = identity never grants the role).
  The flag lives in the signed session, so it is re-evaluated at the next sign-in, not before.
  `KB_API_KEY` remains the break-glass path and is checked first (`via = "key"`); a signed-in
  operator is `via = "group"`. Audits record `requested_by` = `key` or `user:<16 hex>` — an HMAC of
  the issuer-qualified identity under `KB_SESSION_SECRET` (`auth/principal.py::pseudonym`), never the
  subject, name or e-mail, and not confirmable offline by a viewer who can guess subjects; the server
  log carries the subject next to the pseudonym at audit start.
- **Cookie-authenticated operator actions are CSRF-guarded too**: `require_operator` runs
  `same_origin` when the role came via the session; the bearer path is not a cookie and is not.
- **Revocation**: `current_user` accepts a session only while its `epoch` equals the reader's
  `session_epoch` in the profile store (one record read per authenticated request); the epoch
  is written into the cookie at sign-in and moved by "sign out everywhere". A cookie whose
  `operator` is not a JSON boolean, or whose `epoch` is not an integer, reads as viewer / epoch 0.

## Data handled

`sub`, issuer, display name and e-mail from the ID token, plus the `operator` flag and the
session `epoch`, stored in the session cookie (signed, not encrypted — none of it is secret; the
cookie is HttpOnly so scripts cannot read it). Name and e-mail are truncated to 200 characters
and `sub` over 255 is refused (a cookie a browser would drop). No token from the IdP is stored;
access/refresh tokens are discarded, and the group list itself is never stored — only the
resulting boolean. Per-user records are keyed by `sha256(issuer + sub)` (see `profile`); the
epoch lives there as `session_epoch`.

## Secrets

`KB_OIDC_CLIENT_SECRET` (optional; sent only to the token endpoint as RFC 6749 §2.3.1 basic auth,
form-urlencoded, and then `client_id` is not repeated in the body), `KB_SESSION_SECRET` (HMAC key,
≥ 32 chars; rotating it signs everyone out). Both `SecretStr`.

## External calls

HTTPS to the IdP: discovery (once, cached), JWKS (on first use and on an unknown `kid`, at most
once a minute), token endpoint (per sign-in). 10 s timeout. Every transport, status or JSON-shape
failure becomes `OidcError`: login answers 502, callback 401, with fixed messages (detail logged).

## Mutations

`logout-everywhere` writes the reader's own profile record (`bump_session_epoch`, atomic, under
the store lock). Cookies: `kb_login` (transaction) and `kb_session` (`KB_SESSION_TTL_HOURS`,
default 12), both `HttpOnly; SameSite=Lax; Path=/`, `Secure` whenever `KB_OIDC_REDIRECT_URI` is
https (`settings.cookies_secure`: decided from configuration, so a proxy that drops
`X-Forwarded-Proto` cannot downgrade it).

## Controls in place

- PKCE + `state` + `nonce`; `compare_digest` on `state` and on the MAC; JWKS keys cached per `kid`
  with a rate-limited refetch on miss; unknown key → reject, never "allow".
- Open-redirect guard on `next` (`safe_return_path`: absolute same-origin path, ≤ 2 KB, no `//`,
  `\`, or control characters).
- Fixed error strings: nothing from the IdP or the request is reflected into a response.
- Failure modes are explicit: 400 (foreign/expired login), 401 (declined/bad token), 502 (IdP down).
- Group claim read only from verified claims, shape-checked (`_is_operator`), decided once at
  sign-in; the session payload parser accepts `operator` as a JSON boolean only.
- Epoch check on every cookie-authenticated request; the bump is time-derived
  (`max(old + 1, int(time.time()))`, see `profile`) so a value written after a bump never recurs.

## Residual risks and reviewer attention points

- The operator flag is **cached in the session**: a person removed from the group at the IdP keeps
  the role until their cookie expires or is revoked ("sign out everywhere" by them, or rotating
  `KB_SESSION_SECRET`). Keep `KB_SESSION_TTL_HOURS` short where group membership changes matter.
- `DELETE /api/profile` keeps a tombstone with the epoch (`profile` module), so no revoked cookie
  comes back to life; a record that fails to parse is replaced on the spot by a tombstone with a fresh
  nanosecond epoch, so every earlier cookie is refused and the reader signs in again (fail closed);
  retention keeps a record holding an epoch until the session TTL has passed since its last activity.
- Two concurrent logins in one browser overwrite `kb_login`; the first tab's callback fails with 400.
- Discovery is fetched over https but not pinned; the issuer check, the https endpoint check and
  JWKS verification bound the impact of a DNS-level attacker to denial of service.

## Reviewer checklist

- [ ] `ALLOWED_ALGS` contains no symmetric or `none` algorithm.
- [ ] `sso_configured` requires the session secret; no route sets a cookie without it.
- [ ] `safe_return_path` unchanged; `next` never reaches `RedirectResponse` unfiltered.
- [ ] `same_origin` is a dependency of `require_user`, of both logouts, and of `require_operator` on the group path.
- [ ] The group claim is read after `verify_id_token`, never from the unverified token; only a list of strings grants.
- [ ] `requested_by` is `key` or `user:<16 hex>`, never the subject, name or e-mail; `/api/me` never lists the groups.
- [ ] `current_user` compares the cookie's epoch with the store on every request; the callback writes the current epoch.

## Sign-off

Submit with `kb-librarian security submit auth`; the reviewer records the decision with
`kb-librarian security sign auth …`, which appends a row here and to `security/signoffs/auth.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
