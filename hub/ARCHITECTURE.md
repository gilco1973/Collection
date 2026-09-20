# Architecture

The Employee AI Hub is a single-page React application that is a *client of the
platform*, not a system of its own: every fact it shows comes from the Hub API,
every decision about what a person may do is the platform's, and the front end
only avoids advertising what the API would refuse (specification §8.6, PLT-UI-17).

```
src/
  config/env.ts          runtime configuration, validated with zod at boot
  api/
    client.ts            ApiClient: bearer, X-Request-Id, traceparent, Idempotency-Key, If-Match,
                         RFC 9457 problems -> typed errors, one retry on transient idempotent calls
    errors.ts            ApiError hierarchy (Unauthorized, Forbidden, NotFound, Conflict, Validation, Server, Network)
    endpoints.ts         every call the Hub makes, typed; SSE turn stream as an async generator
    schemas.ts           the intake brief as a zod schema (client-side validation = server's rules)
    types.ts             the contract's types (see api/openapi.yaml)
    mock/                in-browser implementation of the same contract, from artboard fixtures
  auth/
    provider.ts          AuthClient interface (initialize, signIn, completeSignIn, signOut, getAccessToken)
    oidc.ts              Authorization Code + PKCE via oidc-client-ts; tokens in memory; silent renew
    mock.ts              dev personas (gk, investigator, employee, platform) -> `mock.<id>` tokens
    AuthProvider.tsx     token lifecycle + the principal from GET /me (the authority on roles, ladder, entitlements)
    permits.ts           closed action set; front-end courtesy checks only
    RequireAuth.tsx      route guard (signed-out -> /signin?returnTo, 403 on /me -> /403)
  ui/                    chrome (HubNav, HubFoot), form controls, icons, toasts, palette, theme, error boundary
  features/
    discover/            Discover and listing pages (GET /catalog, GET /consumers/:slug)
    workspace/           My workspace (GET /me/workspace, POST /me/playground/rotate)
    intake/              the brief: state hook (autosave with etags), six step forms, road/estimate, file
    assistant/           conversations: view-descriptor renderer, SSE streaming, stop, feedback, handoff
    requests/            entitlement / role / ladder requests (POST /me/requests)
    settings/            preferences (PUT /me/preferences), account, data
    shelf/               the collection's sign-off form and queue, the onboarding tracker (GET /shelf, POST /shelf/:name/signoffs)
  screens/               Learn, SignIn, status pages
  styles/
    ui-core.css          the design system, verbatim from the artboards
    ui-core.controls.css semantic controls (<button>, <a>, <input>) painted like the artboard spans
    ui-core.themes.css   dark theme, density, accessibility (behind preference selectors only)
```

## Requests

`ApiClient` is the only place HTTP happens. It takes a `Transport` (the browser's
`fetch`, or the mock server in-process), a token provider (the auth layer), and
hooks. Every request carries:

| Header | Why |
| --- | --- |
| `Authorization: Bearer …` | the identity provider's access token; never persisted |
| `X-Request-Id` | a client id echoed by the server; shown in error support lines |
| `traceparent` | W3C trace context, so a front-end report joins the platform's traces |
| `X-Client-Build` | the build SHA, so support can pin a report to a build |
| `Idempotency-Key` | on mutations a client may safely repeat (create, file, request, rotate, send) |
| `If-Match` | on writes to a versioned record (brief autosave, file) |

Failures are `application/problem+json`, mapped to typed errors: a 401 signs the
person out (the auth layer decides whether to renew), a 403 carries a deny code
the UI explains in plain language, a 409 stops autosave until the person
reloads, a 422 carries field errors keyed by dotted path so the form can show
them next to the field. Only idempotent requests are retried, once, on a
transient failure.

## Authentication and authorization

`AuthClient` is an interface with two implementations. **OIDC**: Authorization
Code with PKCE against the bank's identity provider, tokens held in memory
(`InMemoryWebStorage`), silent renew before expiry, and the callback route
finishes sign-in and returns the person to where they were. **Mock**: a persona
picker whose token the mock API resolves to a principal; the persona is kept in
`sessionStorage` for the tab only.

The `Principal` is what `GET /me` returns: roles, ladder, channel, teams,
entitlements, preferences. It is the authority; token claims are never read on
the client. `permits(principal, action, resource)` is a closed set of eleven
actions used to decide what to *show* and what to *attempt*; the platform's
policy engine decides what *happens*.

## State

Server state lives in TanStack Query with conservative defaults (30 s stale,
no refetch on focus, retry only transient failures on reads, never mutations).
Feature hooks own their mutations and invalidate what they change. Form state
is local and validated with zod per step, using the same schema the server
applies on file, so a 422 the person could have seen never happens.

The intake brief autosaves 1.2 s after the last edit with `If-Match`; a 409
means another tab saved and the form stops until reloaded. Conversations stream:
`POST /conversations/:id/turns` returns `text/event-stream` and each `view`
event is appended as it arrives; aborting the request is the stop button.

## Rendering the assistant

The assistant never sends markup. Each answer is a stream of descriptors from
the closed set of specification §8.2 (`text`, `citation`, `tool_call`, `form`,
`stop`, `budget`, `feedback`, `handoff`, `interrupt`). `features/assistant/Views.tsx`
renders each; text leaves are escaped by React and their claims are marked from
the spans the harness computed, so a claim without a source looks different from
one with.

## The guide

`features/guide/GuideProvider.tsx` sits under the router and the auth provider and owns the guide's state: the
persona the person chose, the routes they visited, the steps they ticked, the nudges they dismissed and the tours
they finished, stored under `hub.guide.<principal id>`. Facts come from the same queries the pages use (`briefs`,
`shelf`, `requests`), so the panel never disagrees with the page beside it. `model.ts` is pure: journeys per
persona, page notes, the one nudge for a page and its facts, the tours. `Tour.tsx` navigates, waits for the
`data-guide` target to render, and draws a spotlight and a callout over it; nothing on the page changes.
Questions go to `POST /guide/ask`; the mock answers from `api/mock/guide.ts`, generated by the shelf tool, with the
same ranking the service uses.

## Pixel fidelity

The five artboards of the design canvas are the reference. Generated screens
were replaced by live components one by one; each live screen renders the
artboard's markup from data, and semantic controls are styled so a `<button
class="btn">` paints the same pixels as the artboard's `<span class="btn">`.
`tools/shoot.cjs` + `tools/diff.py` prove it on every build; the two button
states where the artboards disagree among themselves are listed, with reasons,
in `compare/expected.json`.

## Configuration

See `.env.example`. `VITE_API_MODE=mock` swaps only the transport: the same
client, endpoints and error handling run against the in-browser server, which
implements the contract in `api/openapi.yaml` including 401/403/404/409/422,
etags, idempotency replay and the SSE stream. That is what the end-to-end
scripts and the unit tests run against.
