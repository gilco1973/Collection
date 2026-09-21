# CrossRiver AI Hub — frontend

The Employee AI Hub from the CrossRiver AI Platform experience design: a React +
TypeScript + Tailwind application that is **integration-ready against the Hub
API**, **pixel-identical to the published design-canvas artboards** at its
default state, and runs end to end today against an in-browser implementation
of the same API contract.

| Route | Screen | Source of truth |
| --- | --- | --- |
| `/discover` | Discover | `GET /catalog` for the signed-in person |
| `/discover/:kind/:slug` | A listing (e.g. `/discover/agents/investigation-triage`) | `GET /consumers/:slug` |
| `/assistant`, `/assistant/:consumerId` | Employee assistant and agents | `GET /conversations`, SSE `POST /conversations/:id/turns` |
| `/workspace` | My workspace | `GET /me/workspace` |
| `/build/intake`, `/build/intake/:briefId` | Intake brief (six sections, autosave, file) | `GET/PATCH /briefs/:id`, `POST …/estimate`, `…/road`, `…/file` |
| `/settings` | Preferences and account | `GET /me`, `PUT /me/preferences` |
| `/build/shelf/sign-offs` | Component sign-offs: the queue, the form, the export the shelf tool applies | `GET /shelf`, `POST /shelf/:name/signoffs`, `GET /shelf/signoffs/export` |
| `/build/shelf/onboarding` | Onboarding: every component's stage on its way to the shelf; how champions, owners and AI security engineers join | `GET /shelf` |
| `/learn` | Learn (roads, example, office hours) | static |
| `/signin`, `/auth/callback`, `/403` | Sign-in (OIDC or personas), callback, refused | — |

## What "enterprise ready" means here

- **Configuration is validated at boot** (`src/config/env.ts`, zod). A missing OIDC
  setting fails the start with a readable message, not the first API call. See `.env.example`.
- **Authentication** is an `AuthClient` interface with two implementations:
  Authorization Code + PKCE against the bank's IdP (`oidc-client-ts`, tokens in memory,
  silent renew, callback route, return-to), or dev personas in mock mode.
- **Authorization** comes from the platform. `GET /me` returns the principal (roles,
  ladder, channel, teams, entitlements, preferences) and is the only authority; the
  front end's `permits()` is a closed set of eleven actions used to *show* and
  *attempt*, never to decide. Access on every listing is resolved server-side per
  person (`open` / `request` / `view` / `contract`) and rendered as such.
- **One HTTP client** (`src/api/client.ts`): bearer token, `X-Request-Id`, W3C
  `traceparent`, `X-Client-Build`, `Idempotency-Key` on repeatable mutations,
  `If-Match` on versioned writes, RFC 9457 `problem+json` mapped to typed errors
  (401 → sign out, 403 with deny code, 404, 409 conflict, 422 field errors, 5xx),
  one retry on transient failures for idempotent requests only.
- **The API contract is written down** in `api/openapi.yaml`, typed in
  `src/api/endpoints.ts` and `src/api/types.ts`, and implemented in the browser by
  `src/api/mock/server.ts` for development, demos and tests. `VITE_API_MODE=http`
  swaps the transport and nothing else.
- **Forms validate with the server's rules.** The intake brief is a zod schema
  (`src/api/schemas.ts`) applied per step in the browser and in full on file, so a
  422 the person could have seen never happens; server 422s still land next to the field.
- **Optimistic concurrency.** Drafts autosave with the etag last seen; a 409 stops
  saving until the person reloads, with the message the server sent.
- **Streaming.** Answers arrive as `text/event-stream` view events from the closed
  descriptor set of the specification (§8.2) and render as they come; Stop aborts the
  request (recorded as `human.interrupt`). Model text is never treated as markup.
- **Preferences travel with the account**: theme (system/light/dark), density,
  accessibility (PLT-UI-15), "prefer a person" (PLT-CH-18), locale, notifications;
  applied at once, saved with `PUT /me/preferences`.
- **Accessibility**: real `<button>`, `<a>`, `<input>`, `<label>` under the
  artboards' classes; skip link; focus moves to the page on navigation; live regions
  for toasts and streaming; `:focus-visible` rings; `prefers-reduced-motion`;
  `jsx-a11y` in lint.
- **Observability seam**: `src/telemetry.ts` records product events
  (`brief.filed`, `assistant.stopped`, …) to a sink (`none` | `console`) until the
  OpenTelemetry web SDK is wired; request ids join the platform's traces.
- **Error boundary, toasts, page states** with support lines (`HTTP 409 · request abc…`).

See `ARCHITECTURE.md` for the module map and the request/state design.

## The composer

Section 3 of the intake brief, "Data and tools", opens a composer from "Browse the catalog"
(`src/features/intake/Composer.tsx`): on the left everything that exists (the registry's systems and their tools
with tiers, the collection's components, the bank's services), on the right the brief's own section as a drop
zone. Drag or Add writes straight into the brief; a tool brings its system with it; the panel shows the
consequences live (the ceiling the tools need, the data classes they read, the session limit, whether a lead
files) with one button per fix. A system without a recorded contract is shown but cannot be dropped; a money
tool is refused for a first consumer. What is reused is kept in the brief's optional `reuses` list and shown on
the review page. The default render of the step is unchanged, so the pixel guard still passes at 0 px.

## The guide

A companion drawn over every signed-in screen (`src/features/guide/`): the button at the bottom right, Alt+G, or
the "Next step" peek it shows when something is waiting. On first open it asks what the person is here for
(build, understand and decide, or use), suggesting from their role, and keeps to that: a one-line note on the
page they are on, one suggested next step, a path of steps ticked from the hub's own records (briefs, the shelf,
requests, pages visited) or by hand, a spotlight tour of the parts that matter for them, and a place to ask.
Answers come from `POST /guide/ask`, which quotes the repository's pages and names them; a question that reads as
an instruction is refused, and a question the pages do not answer is admitted. A leader is told what an agent
cannot do on the pages where it matters; a builder is pointed at the reference agent, the brief and the queue.
The guide never acts on the person's behalf and has no tools. Its state is theirs alone, in the browser under
their principal id. Tour targets are `data-guide` attributes on the live screens; the pixel guard hides the
launcher before it shoots, because the guide is drawn over the artboards, never inside them.

## Fidelity guarantee, and how it is kept

The five artboards of the design canvas are committed under `artboards/`. The
live screens render the artboards' markup from data, with the design system
(`src/styles/ui-core.css`) verbatim and Tailwind's preflight deliberately not
loaded. Semantic controls are styled by `src/styles/ui-core.controls.css` so a
`<button class="btn">` paints the same pixels as the artboard's `<span class="btn">`.

`tools/shoot.cjs` renders each artboard and the matching route in one Chromium
session (same viewport, same cached fonts) and `tools/diff.py` counts differing
pixels. At the artboard persona's default state every screen diffs at **0 px**,
with one documented exception: the Home and Listing artboards draw "Request
access" and "Request ladder L2" while the Workspace artboard already lists both
requests as pending; the live app shows them as requested. Those two button
regions are listed with reasons in `compare/expected.json`; anything else fails
the guard.

| Screen | Pixels compared | Differing | Inside documented regions |
| --- | ---: | ---: | ---: |
| HubHome | 2,390,400 | 0 | 1,196 |
| HubListing | 2,016,000 | 0 | 1,038 |
| HubIntake | 1,699,200 | 0 | 0 |
| HubWorkspace | 1,612,800 | 0 | 0 |
| HubAssistant | 1,296,000 | 0 | 0 |

`tools/html2jsx.py` remains for reference: it is the lossless converter that
produced the first, static screens from the artboards.

## Running it

```
pnpm install
pnpm dev                 # http://127.0.0.1:5173, mock API and mock sign-in
pnpm verify              # typecheck, lint, unit tests, build
pnpm build && pnpm preview
pnpm verify:shoot && pnpm verify:diff    # pixel guard (needs Chromium; CHROMIUM_PATH=… if not registered)
pnpm verify:e2e          # nav, intake, discover/listing/workspace, assistant, settings flows
pnpm build:artifact      # static-host bundle (HashRouter, relative assets) in dist-artifact/
```

Node ≥ 22, pnpm 10. In mock mode, sign in as one of five personas: **Gil Klainert**
(ops.lead, the artboard user), **Ana Petrov** (investigator, ladder L1), **Sam Okafor**
(employee, no team, prefers assistive technology), **Dana Ruiz** (platform lead), **Maya Chen**
(AI security engineer, the `ai.security` role that signs components off).
`?mockPersona=gk` on any URL signs in without the picker (tests use this).

Behind hub-api (`services/hub-api`), nothing is set at build time: the page loads `/config.js`, which hub-api
renders from its `HUB_WEB_*` settings, so one `dist/` runs in every environment.

On a static host without hub-api: set `VITE_API_MODE=http`, `VITE_API_BASE`, `VITE_AUTH_MODE=oidc`
and the `VITE_OIDC_*` values; the server must implement `api/openapi.yaml`.

## Tests

- **Unit** (`vitest`, jsdom): the intake schema and its refinements, permits,
  the HTTP client (headers, error mapping, retry policy), the mock server against
  the contract (401/403/404/409/422, etags, idempotency replay, the SSE stream and
  stop), the view-descriptor renderer.
- **End to end** (`tools/*test.cjs`, Playwright on the preview build): navigation,
  the whole brief (autosave, validation, the tier-ceiling rule, the lead rule, filing),
  entitlement and ladder requests reflected across screens, catalog tabs and views,
  key rotation, the ⌘K palette, streaming with stop, feedback, handoff, assistant
  switching, preferences and the dark theme, and role-based visibility for the
  employee persona.
- **Pixel guard** as above. CI (`.github/workflows/crossriver-ai-hub.yml`) runs all of it.

## Known limits, stated plainly

- **Fixed 1440 px width and artboard heights** are kept for fidelity; the Hub is
  a desktop surface through Phase 4 (PD-UX-5).
- **The mock API is in-memory per page load.** A reload resets it to the fixtures;
  in-app navigation keeps state. That is what makes it deterministic for tests.
- **Dark theme, density and accessibility** are the platform's own derivation of
  the light design system; the design canvas has no dark artboards yet.
- **Learn** is the one page not drawn from an artboard.
- **Not yet wired**: the `form` view (on-screen confirmation for W1 tools) renders a
  placeholder; the OpenTelemetry sink; locale-specific number formats.
