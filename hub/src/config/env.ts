import { z } from "zod";

/**
 * Runtime configuration, validated once at boot.
 *
 * Every knob the deployment can turn is declared here with its type and its
 * default, so a misconfigured build fails at startup with a readable message
 * instead of failing at the first API call. Values come from Vite's
 * `import.meta.env` (a `.env.<mode>` file or the host's environment).
 */
const schema = z
  .object({
    /** Base URL of the Hub API. Relative (`/api`) when served behind the same origin. */
    VITE_API_BASE: z.string().default("/api"),
    /** `http` talks to a real server; `mock` serves fixtures in-process (dev, demos, tests). */
    VITE_API_MODE: z.enum(["http", "mock"]).default("mock"),
    /** `oidc` runs Authorization Code + PKCE against the bank IdP; `mock` offers dev personas. */
    VITE_AUTH_MODE: z.enum(["oidc", "mock"]).default("mock"),
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

function load(): Env {
  const parsed = schema.safeParse(import.meta.env);
  if (!parsed.success) {
    const lines = parsed.error.issues.map((i) => `  ${i.path.join(".")}: ${i.message}`).join("\n");
    throw new Error(`Invalid configuration:\n${lines}`);
  }
  return parsed.data;
}

export const env: Env = load();
