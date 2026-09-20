# typed-api-client

The one HTTP client a front end uses. Every request carries the bearer token, an `X-Request-Id`, a W3C
`traceparent` and the build SHA; mutations a caller may repeat carry an `Idempotency-Key`, versioned writes an
`If-Match`; RFC 9457 `problem+json` failures become typed errors (401 signs out through a hook, 403 with a deny
code, 404, 409 conflict, 422 field errors, 5xx); only idempotent requests are retried, once, on a transient failure.
`createMockServer` is an in-process API behind the same `Transport`, so the real client runs in development, demos
and tests without a server.

## Five-minute start

```ts
import { ApiClient, createMockServer, json, fetchTransport } from "./src";
const server = createMockServer((token) => (token === "mock.gk" ? { id: "gk" } : undefined));
server.route("GET", "/me", ({ principal }) => json(principal));
const api = new ApiClient("/api", server.serve, async () => "mock.gk", { buildSha: "dev" });
await api.get("/me");                       // { id: "gk" }
// production: new ApiClient("/api", fetchTransport, () => auth.getAccessToken(), { onUnauthorized: signOut, buildSha })
```

```
npm ci && npx tsc -p tsconfig.json && npx vitest run
```

## What is inside

| File | What it is |
| --- | --- |
| `src/client.ts` | `ApiClient` (`get/post/put/patch/delete/raw`), `Transport`, `TokenProvider`, `ClientHooks`, `fetchTransport`, `newId` |
| `src/errors.ts` | `ApiError` and the typed subclasses, `errorFromResponse`, `isTransient`, `Problem` |
| `src/mockServer.ts` | `createMockServer(resolve, base)`: `route`, `serve`, `reset`; `json`, `problem` |
| `src/*.test.ts` | Headers, idempotency and If-Match, problem mapping, 401 hook, retry policy, 204, the mock server |

## How to reuse it

Copy `src/`. Build your typed endpoints as functions over `ApiClient` (the hub's `endpoints.ts` is the shape). Give the
client your auth layer's `getAccessToken` and sign out in `onUnauthorized`. Swap `fetchTransport` for the mock server's
`serve` with one environment variable and nothing else changes.

## Rules it enforces

Never retries a mutation; never persists a token; never treats a failure body as markup; the request id in an error's
`supportLine` is the server's when it echoed one.

## Where it came from

The AI Hub front end (`src/api/client.ts`, `errors.ts` and the route helper of `mock/server.ts`, snapshot
2026-09-19), with the build SHA made a constructor option.

## Known limits

Streaming responses use `raw()` and are parsed by the caller (the hub's SSE turn stream is the example).

**Replacement test** (the platform specification's §14.3 rule for an interim): The Hub API client generated from the contract registry carries the same headers and error mapping; the mock server becomes the recorded contract's fixtures.
