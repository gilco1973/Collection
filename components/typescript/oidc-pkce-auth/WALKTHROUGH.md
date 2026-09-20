# Walkthrough: oidc-pkce-auth

## 1. Run the live example

```
cd components/typescript/oidc-pkce-auth && npm install && npx tsx example.ts
```

The persona client signs in and out with a `mock.<persona>` bearer, the principal that `GET /me` would return for it, and the permits set answering five questions: the workspace, two consumers (one entitled, one not), filing a brief, admin.

## 2. Copy `src/`

```
cp -r src /path/to/your-app/src/auth
```

## 3. Pick the client by environment

`createOidcClient({ authority, clientId, redirectUri, scope })` in production (Authorization Code with PKCE, tokens in memory, silent renew); `createMockClient()` in development and tests. Both satisfy `AuthClient`.

## 4. Mount the provider with your dependencies

```tsx
<AuthProvider deps={{ client, fetchPrincipal: (signal) => api.me.get(signal), onUnauthorized: api.onUnauthorized, track }}>
```

The provider owns the token lifecycle and fetches the principal from `GET /me`; the principal, never the token's claims, is the authority on roles, ladder and entitlements.

## 5. Guard routes

`<RequireAuth action="hub.workspace"><Workspace /></RequireAuth>`: signed-out goes to `/signin?returnTo=`, a 403 from `/me` or a missing action goes to `/403`. Replace `defaultStates` with your page states.

## 6. Rename the actions

`permits.ts` is a closed set; rename to your actions and keep it closed. It decides what to show and attempt; the platform decides what happens.

## 7. Prove it

```
npx tsc -p tsconfig.json && npx vitest run
```
