# Security review sheet: Console API client, hooks and types

| | |
| --- | --- |
| Module id | `web-api-client` |
| Kind | frontend |
| Code | `web/src/api/client.ts`, `hooks.ts`, `types.ts`, `chatTypes.ts`, `insightsTypes.ts` |
| Tests | `web/src/test/units.test.ts`, `web/src/test/harness.tsx` (fetch mock used by every page test) |
| Depends on | TanStack Query 5, `fetch` |

## Purpose

The one place the console talks to the API: `request()` adds `Accept`, the bearer token when
one is stored, and `Content-Type` for bodies; maps the error envelope to `ApiError(status,
message, requestId)`. Query/mutation hooks wrap each endpoint.

## Entry points

`api.*` functions, `readApiKey/storeApiKey`, `fileUrl`, `encodePath`, hooks such as `usePage`,
`useSearch`, `useStartAudit`, `useChat` (body: `message`, `history`, `lang?`, `mode?`, `context?`),
`useRecordQuiz`, `useProfile`/`useSetPersona`, `usePagesFor` (`GET /pages?audience=`, idle until a
persona is set), `useSignOut` (`POST /auth/logout`) and `useSignOutEverywhere`
(`POST /auth/logout-everywhere`; both invalidate the whole query cache when they settle),
`useInsights` (`GET /insights`, operator; a 404 resolves to `null` rather than an error, no retry)
and `useRefreshInsights` (`POST /insights/refresh`; the response replaces the cached insights).
Insight shapes live in `insightsTypes.ts` (paths, counts and rates; `null` below `k` readers).

## Trust boundaries

Same-origin `/api` by default (`VITE_API_BASE` overrides at build time). Responses are trusted
as data from our own API; rendering safety is handled by the components. `Me.role`,
`Me.operator_via` (`key` | `group` | null) and `SignedInUser.operator` are read for presentation
only; the server decides authorisation on every request.

## Data handled

The operator key in `localStorage` (`kb.apiKey`) when the operator saves it in Settings.
Page content, reports, chat answers in memory (query cache, `staleTime` 10 s). `Me` (role, how
the operator role was granted, the signed-in person's `sub`/name/e-mail/`operator`) in the cache.

## Secrets

The operator bearer key: stored in `localStorage` by explicit user action, sent only to
`API_BASE`, never logged. Cleared by the Settings "Clear" action.

## External calls

`fetch` to `API_BASE` only.

## Mutations

Mutations correspond one-to-one to API `POST`s (start/cancel/rollback audits, report a
problem, chat, record a quiz tally `{path, score, total}` for the signed-in reader, sign out,
sign out everywhere — which revokes every session of the reader server-side, refresh the insights
file server-side); nothing else.

## Controls in place

- `encodePath` percent-encodes each path segment, keeping `/`, so a page path cannot inject
  query or traversal characters into the URL.
- Query strings built with `URLSearchParams`.
- `localStorage` access wrapped in try/catch (private mode, blocked storage).
- Error bodies parsed defensively; `request_id` surfaced for support.

## Residual risks and reviewer attention points

- `localStorage` is readable by any script on the origin: acceptable because the CSP forbids
  foreign scripts and the console has no third-party script; an XSS in the console would
  expose the key — the Markdown renderer's no-HTML policy is the control.
- Storing a shared operator key in a browser is a stop-gap until SSO; the Settings page tells
  operators to clear it on shared machines.

## Reviewer checklist

- [ ] `Authorization` header set only for `API_BASE` requests.
- [ ] No endpoint path is built from unencoded user input.

## Sign-off

Submit with `kb-librarian security submit web-api-client`; the reviewer records the decision with
`kb-librarian security sign web-api-client …`, which appends a row here and to `security/signoffs/web-api-client.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
