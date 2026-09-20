# oidc-pkce-auth

Sign-in for a browser application against the company's identity provider: Authorization Code with PKCE through
`oidc-client-ts`, tokens held in memory only (never localStorage), silent renew, a callback route that returns the
person where they were. The `Principal` (roles, ladder, teams, entitlements, preferences) comes from `GET /me`, the
platform's authority, never from token claims read on the client. `permits()` is a closed set of actions the front
end uses to decide what to show and attempt; the platform decides what happens. A persona client stands in for the
IdP in development and tests.

## Five-minute start

```tsx
import { AuthProvider, RequireAuth, createMockClient, createOidcClient, useAuth } from "./src";
const client = import.meta.env.VITE_AUTH_MODE === "oidc" ? createOidcClient({ authority, clientId, redirectUri, scope: "openid profile email" }) : createMockClient();
<AuthProvider deps={{ client, fetchPrincipal: (signal) => api.me.get(signal), onUnauthorized: api.onUnauthorized }}>
  <Route path="/workspace" element={<RequireAuth action="hub.workspace"><Workspace /></RequireAuth>} />
</AuthProvider>
```

```
npm ci && npx tsc -p tsconfig.json && npx vitest run
```

## What is inside

| File | What it is |
| --- | --- |
| `src/provider.ts` | `AuthClient`: the contract every identity backend satisfies |
| `src/oidc.ts` | `createOidcClient` (PKCE, in-memory tokens, silent renew, callback) |
| `src/mock.ts` | `createMockClient` and `MOCK_PERSONAS` (`mock.<persona>` bearer tokens) |
| `src/types.ts` | `Principal`, `Preferences`, `AuthSnapshot`, `Ladder`, `Role`, `Channel` |
| `src/permits.ts` | The closed action set, `permits`, `primaryRole`, `isTeamLead` |
| `src/AuthProvider.tsx` | Token lifecycle plus the principal from `GET /me`; dependencies injected |
| `src/RequireAuth.tsx` | Route guard: signed-out to `/signin?returnTo=`, a 403 on `/me` to `/403`, an action the person lacks to `/403` |
| `src/*.test.ts(x)` | Permits by entitlement, ceiling and ownership; the provider and guard rendered with the persona client |

## How to reuse it

Copy `src/`. Rename the actions in `permits.ts` to yours (keep the set closed). Point `fetchPrincipal` at your
`GET /me` (`typed-api-client`). Replace `defaultStates` in `RequireAuth` with your page states.

## Rules it enforces

Tokens never touch storage; the principal is never derived from token claims; `permits` grants nothing to an
undefined principal; opening a consumer is by entitlement, not role.

## Where it came from

The AI Hub front end (`src/auth/`, snapshot 2026-09-19), with the provider's dependencies made explicit props.
