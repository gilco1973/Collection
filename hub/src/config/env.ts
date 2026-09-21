import { z } from "zod";

/**
 * Runtime configuration, validated once at boot.
 *
 * Every knob the deployment can turn is declared here with its type and its
 * default, so a misconfigured build fails at startup with a readable message
 * instead of failing at the first API call. Values come from Vite's
 * `import.meta.env` (a `.env.<mode>` file or the host's environment) and, on
 * top of those, from `/config.js` (`window.__HUB_CONFIG__`), which hub-api
 * renders from its own settings so one built dist runs in every environment.
 *
 * Nothing here runs at import time: `loadEnv()` parses on first use, so a bad
 * configuration is thrown to `main.tsx`, which renders it, never to the module
 * loader, which would leave a blank page.
 */
const schema = z
  .object({
    /** Base URL of the Hub API. Relative (`/api`) when served behind the same origin. */
    VITE_API_BASE: z.string().default("/api"),
    /** `http` talks to a real server; `mock` serves fixtures in-process (dev, demos, tests). */
    VITE_API_MODE: z.enum(["http", "mock"]),
    /** `oidc` runs Authorization Code + PKCE against the bank IdP; `mock` offers dev personas. */
    VITE_AUTH_MODE: z.enum(["oidc", "mock"]),
    VITE_OIDC_AUTHORITY: z.string().url().optional(),
    VITE_OIDC_CLIENT_ID: z.string().min(1).optional(),
    VITE_OIDC_REDIRECT_URI: z.string().url().optional(),
    VITE_OIDC_POST_LOGOUT_URI: z.string().url().optional(),
    VITE_OIDC_SCOPE: z.string().default("openid profile email"),
    /** `browser` for a host with rewrites; `hash` for a static host. */
    VITE_ROUTER: z.enum(["browser", "hash"]).default("browser"),
    /** The knowledge base's console, linked from Learn; relative when served behind the same origin. */
    VITE_KB_URL: z.string().default("/kb"),
    /** Where telemetry events go until the OpenTelemetry web SDK is wired. */
    VITE_TELEMETRY: z.enum(["none", "console"]).default("none"),
    /** Shown in the footer and sent as a header, so support can pin a report to a build. */
    VITE_BUILD_SHA: z.string().default("dev"),
  })
  .superRefine((v, ctx) => {
    if (v.VITE_AUTH_MODE === "oidc") {
      for (const key of ["VITE_OIDC_AUTHORITY", "VITE_OIDC_CLIENT_ID", "VITE_OIDC_REDIRECT_URI"] as const) {
        if (!v[key]) ctx.addIssue({ code: z.ZodIssueCode.custom, path: [key], message: `${key} is required when VITE_AUTH_MODE=oidc` });
      }
    }
  });

export type Env = z.infer<typeof schema>;

/**
 * Runtime configuration: hub-api serves `/config.js`, which sets `window.__HUB_CONFIG__`
 * from its own settings, so one built dist runs in every environment (sandbox, staging,
 * production) with the identity provider and API mode decided at deploy time, not at
 * build time. Build-time values remain the defaults for `vite dev` and static hosting.
 */
declare global {
  interface Window {
    __HUB_CONFIG__?: Record<string, unknown>;
  }
}

/** The name of the runtime flag hub-api sets in `/config.js` when it serves mock identity (sandbox only). */
export const RUNTIME_ALLOW_MOCK = "HUB_ALLOW_MOCK";
/** The build-time flag that makes a production build a demo build: the mock is allowed and is the default. */
export const BUILD_ALLOW_MOCK = "VITE_ALLOW_MOCK";

const MOCK_MODES = ["VITE_API_MODE", "VITE_AUTH_MODE"] as const;

/** What `loadEnv()` reads; exposed so the rules can be tested without a window or a build. */
export interface EnvSources {
  /** `import.meta.env`: the values baked in at build time. */
  build: Record<string, unknown>;
  /** `window.__HUB_CONFIG__`: undefined when `/config.js` did not load or did not set it. */
  runtime: unknown;
  /** `import.meta.env.PROD`: a production build fails closed. */
  prod: boolean;
}

function truthy(v: unknown): boolean {
  return v === true || v === "true" || v === "1" || v === 1;
}

function viteStrings(src: unknown): Record<string, string> {
  return src && typeof src === "object"
    ? Object.fromEntries(Object.entries(src as Record<string, unknown>).filter(([k, v]) => k.startsWith("VITE_") && typeof v === "string" && v !== "")) as Record<string, string>
    : {};
}

function invalid(lines: string[]): Error {
  return new Error(`Invalid configuration:\n${lines.map((l) => `  ${l}`).join("\n")}`);
}

/**
 * The rules, as a pure function of the two sources.
 *
 * - A development build (`vite dev`, vitest) and a demo build (`VITE_ALLOW_MOCK=1`) default to the mock: the
 *   in-browser API and the dev personas.
 * - A production build fails closed. `/config.js` must have loaded and must name `VITE_API_MODE` and
 *   `VITE_AUTH_MODE` (hub-api always does; a static host bakes them in at build time). `mock` is refused
 *   unless the configuration that names it also carries the flag: `HUB_ALLOW_MOCK: true` in `/config.js`
 *   (hub-api sets it in the sandbox with `HUB_AUTH=mock`) or `VITE_ALLOW_MOCK=1` at build time. A missing
 *   or broken `/config.js` is therefore a readable error, never the five development personas on
 *   fabricated data.
 */
export function parseEnv({ build, runtime, prod }: EnvSources): Env {
  const demoBuild = truthy(build[BUILD_ALLOW_MOCK]);
  const strict = prod && !demoBuild;
  const runtimeObject = runtime && typeof runtime === "object" ? (runtime as Record<string, unknown>) : undefined;
  if (strict && runtimeObject === undefined) {
    throw invalid([
      "the runtime configuration did not load: /config.js must set window.__HUB_CONFIG__ (hub-api serves it from its HUB_WEB_* settings).",
      "The hub refuses to start without it rather than fall back to the development mock.",
    ]);
  }
  const fromRuntime = viteStrings(runtimeObject);
  const merged: Record<string, string> = { ...viteStrings(build), ...fromRuntime };
  const allowMock = demoBuild || truthy(runtimeObject?.[RUNTIME_ALLOW_MOCK]);
  const problems: string[] = [];
  for (const key of MOCK_MODES) {
    if (!merged[key]) {
      if (strict) problems.push(`${key} is not set: /config.js (or the build) must name it; a production build has no default.`);
      else merged[key] = "mock";
    } else if (merged[key] === "mock" && prod && !allowMock) {
      problems.push(`${key}=mock is refused in a production build unless ${RUNTIME_ALLOW_MOCK} is set in /config.js (hub-api sets it in the sandbox with HUB_AUTH=mock) or the build was made with ${BUILD_ALLOW_MOCK}=1.`);
    }
  }
  if (problems.length) throw invalid(problems);
  const parsed = schema.safeParse(merged);
  if (!parsed.success) throw invalid(parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`));
  return parsed.data;
}

function readRuntime(): unknown {
  try {
    return typeof window !== "undefined" ? window.__HUB_CONFIG__ : undefined;
  } catch {
    return undefined;
  }
}

let current: Env | undefined;

/** Parse the configuration once (throws a readable `Error` on a bad one) and return it. */
export function loadEnv(): Env {
  if (!current) current = parseEnv({ build: import.meta.env as unknown as Record<string, unknown>, runtime: readRuntime(), prod: import.meta.env.PROD });
  return current;
}

/**
 * The configuration, loaded on first access. Modules may read `env.X` at their top level: the read
 * happens when the module is evaluated, which `main.tsx` does only after `loadEnv()` succeeded.
 */
export const env: Env = new Proxy({} as Env, {
  get: (_t, key) => loadEnv()[key as keyof Env],
  has: (_t, key) => key in loadEnv(),
  ownKeys: () => Reflect.ownKeys(loadEnv()),
  getOwnPropertyDescriptor: (_t, key) => {
    const d = Object.getOwnPropertyDescriptor(loadEnv(), key);
    return d ? { ...d, configurable: true } : undefined;
  },
});
