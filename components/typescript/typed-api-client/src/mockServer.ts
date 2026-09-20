/**
 * An in-process API as a `Transport`, so the real `ApiClient` runs against it unchanged in development, demos and
 * tests: bearer tokens resolve to principals, failures are RFC 9457 problem+json, idempotency keys replay the
 * first response. Register routes with `route()`, then pass `serve` as the client's transport.
 */
import type { Transport } from "./client";
import type { Problem } from "./errors";

export type Handler<P> = (ctx: { params: Record<string, string>; url: URL; body: unknown; principal: P; req: Request }) => Response | Promise<Response>;

export interface MockServer<P> {
  route(method: string, path: string, handler: Handler<P>, opts?: { anonymous?: boolean }): void;
  serve: Transport;
  reset(): void;
}

export const json = (body: unknown, init: ResponseInit = {}) =>
  new Response(JSON.stringify(body), { status: 200, ...init, headers: { "Content-Type": "application/json", ...(init.headers ?? {}) } });

export const problem = (status: number, p: Problem) =>
  new Response(JSON.stringify({ status, ...p }), { status, headers: { "Content-Type": "application/problem+json" } });

/** `resolve` maps a bearer token to a principal (e.g. `mock.<persona>` -> a fixture), or undefined for 401. */
export function createMockServer<P>(resolve: (token: string | undefined) => P | undefined, base = "/api"): MockServer<P> {
  const routes: Array<{ method: string; pattern: RegExp; keys: string[]; handler: Handler<P>; anonymous?: boolean }> = [];
  const idempotency = new Map<string, Response>();
  const strip = (pathname: string) => (pathname.startsWith(base) ? pathname.slice(base.length) : pathname) || "/";
  return {
    route(method, path, handler, opts = {}) {
      const keys: string[] = [];
      const pattern = new RegExp("^" + path.replace(/:(\w+)/g, (_, k) => (keys.push(k), "([^/]+)")) + "$");
      routes.push({ method, pattern, keys, handler, ...opts });
    },
    reset() {
      idempotency.clear();
    },
    serve: async (req) => {
      const url = new URL(req.url);
      const path = strip(url.pathname);
      const match = routes.find((r) => r.method === req.method && r.pattern.test(path));
      if (!match) return problem(404, { title: "Not found", detail: `No route for ${req.method} ${path}.` });
      const token = /^Bearer (.+)$/.exec(req.headers.get("authorization") ?? "")?.[1];
      const principal = resolve(token);
      if (!principal && !match.anonymous) return problem(401, { title: "Unauthenticated" });
      const key = req.headers.get("idempotency-key");
      if (key && idempotency.has(key)) return idempotency.get(key)!.clone();
      const m = match.pattern.exec(path)!;
      const params = Object.fromEntries(match.keys.map((k, i) => [k, decodeURIComponent(m[i + 1])]));
      const body = req.method === "GET" || req.method === "HEAD" ? undefined : await req.text().then((t) => (t ? JSON.parse(t) : undefined));
      const res = await match.handler({ params, url, body, principal: principal as P, req });
      const out = res.headers.has("X-Request-Id") ? res : new Response(res.body, { status: res.status, headers: { ...Object.fromEntries(res.headers), "X-Request-Id": req.headers.get("x-request-id") ?? "" } });
      if (key) idempotency.set(key, out.clone());
      return out;
    },
  };
}
