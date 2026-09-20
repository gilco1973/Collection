# Walkthrough: typed-api-client

## 1. Run the live example

```
cd components/typescript/typed-api-client && npm install && npx tsx example.ts
```

The real client against the in-process mock server: a `GET /me` with the bearer resolved to a principal, a `PATCH` with the right `If-Match`, a stale etag turned into a `ConflictError` with a support line, a 422 with field errors, and the same idempotency key returning the same response twice.

## 2. Copy `src/`

```
cp -r src /path/to/your-app/src/api
```

## 3. Construct one client

```ts
const api = new ApiClient("/api", fetchTransport, () => auth.getAccessToken(), { onUnauthorized: signOut, buildSha: import.meta.env.VITE_BUILD_SHA });
```

Nothing else in the app calls `fetch`. In tests and demos, pass `server.serve` from `createMockServer` instead of `fetchTransport`.

## 4. Type your endpoints

Write functions over the client, one per route, with the response type: `get: (signal) => api.get<Principal>("/me", { signal })`. That file is your half of the API contract; the server's OpenAPI is the other.

## 5. Send the right headers per call

Mutations a caller may repeat take `idempotencyKey`; writes to a versioned record take `ifMatch`. The client never retries a mutation; it retries an idempotent call once on a transient failure.

## 6. Handle errors by type

`UnauthorizedError` signs the person out through the hook; `ForbiddenError` carries a deny code to explain; `ConflictError` stops autosave until reload; `ValidationError.fieldErrors` lands next to the field. Show `error.supportLine` in the UI so support can find the request.

## 7. Prove it

```
npx tsc -p tsconfig.json && npx vitest run
```
