import { env } from "../config/env";
import { errorFromResponse, isTransient, NetworkError, type Problem } from "./errors";

/**
 * The one HTTP client every feature uses.
 *
 * - Attaches the bearer token from the auth layer on every call.
 * - Sends `X-Request-Id` and a W3C `traceparent`, so a front-end report joins
 *   the server's logs and the platform's traces in one step.
 * - Parses `application/problem+json` into typed errors (see `errors.ts`).
 * - Retries idempotent requests once on a transient failure; never retries a
 *   mutation, which instead carries an `Idempotency-Key` the server can honour.
 * - Takes a `Transport` so the mock server plugs in without touching `fetch`.
 */
export type Transport = (input: Request) => Promise<Response>;

export interface RequestOptions {
  body?: unknown;
  signal?: AbortSignal;
  /** Client-generated key for a mutation the caller may safely repeat. */
  idempotencyKey?: string;
  /** Optimistic concurrency: the version the caller last saw. */
  ifMatch?: string;
  headers?: Record<string, string>;
}

export type TokenProvider = () => Promise<string | undefined>;

export interface ClientHooks {
  /** Called on a 401 after the request; the auth layer decides whether to refresh or sign in. */
  onUnauthorized?: () => void;
}

const IDEMPOTENT = new Set(["GET", "HEAD", "OPTIONS", "PUT", "DELETE"]);

/** Absolute URL for the request: relative bases resolve against the page (or localhost under Node). */
function absolute(base: string, path: string): string {
  const joined = path.startsWith("http") ? path : `${base.replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
  if (/^https?:/.test(joined)) return joined;
  const origin = typeof location !== "undefined" && location.origin && location.origin !== "null" ? location.origin : "http://localhost";
  return new URL(joined, origin).toString();
}

export function newId(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

function traceparent(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(24));
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `00-${hex.slice(0, 32)}-${hex.slice(32, 48)}-01`;
}

export class ApiClient {
  constructor(
    private readonly base: string,
    private readonly transport: Transport,
    private readonly getToken: TokenProvider,
    private readonly hooks: ClientHooks = {},
  ) {}

  get<T>(path: string, opts: RequestOptions = {}) {
    return this.request<T>("GET", path, opts);
  }
  post<T>(path: string, body?: unknown, opts: RequestOptions = {}) {
    return this.request<T>("POST", path, { ...opts, body });
  }
  put<T>(path: string, body?: unknown, opts: RequestOptions = {}) {
    return this.request<T>("PUT", path, { ...opts, body });
  }
  patch<T>(path: string, body?: unknown, opts: RequestOptions = {}) {
    return this.request<T>("PATCH", path, { ...opts, body });
  }
  delete<T>(path: string, opts: RequestOptions = {}) {
    return this.request<T>("DELETE", path, opts);
  }

  /** A response left unparsed, for streaming bodies (SSE turn events). */
  async raw(path: string, opts: RequestOptions & { method: string; accept?: string }): Promise<Response> {
    const url = absolute(this.base, path);
    const requestId = newId();
    const headers: Record<string, string> = {
      Accept: opts.accept ?? "application/json",
      "X-Request-Id": requestId,
      traceparent: traceparent(),
      "X-Client-Build": env.VITE_BUILD_SHA,
      ...opts.headers,
    };
    if (opts.body !== undefined) headers["Content-Type"] = "application/json";
    if (opts.idempotencyKey) headers["Idempotency-Key"] = opts.idempotencyKey;
    const token = await this.getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    let res: Response;
    try {
      res = await this.transport(
        new Request(url, {
          method: opts.method,
          headers,
          body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
          signal: opts.signal,
          credentials: "same-origin",
        }),
      );
    } catch (e) {
      if (opts.signal?.aborted) throw e;
      throw new NetworkError(e);
    }
    if (!res.ok) {
      const ct = res.headers.get("content-type") ?? "";
      const problem = ct.includes("json") ? ((await res.json().catch(() => undefined)) as Problem | undefined) : undefined;
      if (res.status === 401) this.hooks.onUnauthorized?.();
      throw errorFromResponse(res.status, problem, res.headers.get("x-request-id") ?? requestId);
    }
    return res;
  }

  async request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
    const url = absolute(this.base, path);
    const requestId = newId();
    const headers: Record<string, string> = {
      Accept: "application/json",
      "X-Request-Id": requestId,
      traceparent: traceparent(),
      "X-Client-Build": env.VITE_BUILD_SHA,
      ...opts.headers,
    };
    if (opts.body !== undefined) headers["Content-Type"] = "application/json";
    if (opts.idempotencyKey) headers["Idempotency-Key"] = opts.idempotencyKey;
    if (opts.ifMatch) headers["If-Match"] = opts.ifMatch;
    const token = await this.getToken();
    if (token) headers.Authorization = `Bearer ${token}`;

    const attempt = async (): Promise<T> => {
      const req = new Request(url, {
        method,
        headers,
        body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
        signal: opts.signal,
        credentials: "same-origin",
      });
      let res: Response;
      try {
        res = await this.transport(req);
      } catch (e) {
        if (opts.signal?.aborted) throw e;
        throw new NetworkError(e);
      }
      if (res.ok) {
        if (res.status === 204) return undefined as T;
        return (await res.json()) as T;
      }
      let problem: Problem | undefined;
      const ct = res.headers.get("content-type") ?? "";
      if (ct.includes("json")) problem = (await res.json().catch(() => undefined)) as Problem | undefined;
      const err = errorFromResponse(res.status, problem, res.headers.get("x-request-id") ?? requestId);
      if (res.status === 401) this.hooks.onUnauthorized?.();
      throw err;
    };

    try {
      return await attempt();
    } catch (e) {
      if (IDEMPOTENT.has(method) && isTransient(e) && !opts.signal?.aborted) {
        await new Promise((r) => setTimeout(r, 300));
        return attempt();
      }
      throw e;
    }
  }
}

/** The browser's own fetch, as a Transport. */
export const fetchTransport: Transport = (req) => fetch(req);
