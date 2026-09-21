import { describe, expect, it } from "vitest";
import { parseEnv } from "./env";

const OIDC = { VITE_API_MODE: "http", VITE_AUTH_MODE: "oidc", VITE_OIDC_AUTHORITY: "https://idp.example/tenant", VITE_OIDC_CLIENT_ID: "hub-web", VITE_OIDC_REDIRECT_URI: "https://hub.example/auth/callback" };

describe("runtime configuration", () => {
  it("lets /config.js override build-time values, ignoring anything that is not a VITE_ string", async () => {
    window.__HUB_CONFIG__ = { VITE_API_MODE: "http", VITE_KB_URL: "https://kb.example", NOT_VITE: "x", VITE_ROUTER: "" };
    const { env } = await import("./env");
    expect(env.VITE_API_MODE).toBe("http");
    expect(env.VITE_KB_URL).toBe("https://kb.example");
    expect(env.VITE_ROUTER).toBe("browser");
    expect((env as Record<string, unknown>).NOT_VITE).toBeUndefined();
    delete window.__HUB_CONFIG__;
  });

  it("a development build defaults to the mock, with or without /config.js", () => {
    expect(parseEnv({ build: {}, runtime: undefined, prod: false })).toMatchObject({ VITE_API_MODE: "mock", VITE_AUTH_MODE: "mock" });
    expect(parseEnv({ build: {}, runtime: {}, prod: false })).toMatchObject({ VITE_API_MODE: "mock", VITE_AUTH_MODE: "mock" });
  });

  it("a production build refuses to start when /config.js did not load, rather than fall back to the mock", () => {
    expect(() => parseEnv({ build: {}, runtime: undefined, prod: true })).toThrow(/config\.js must set window\.__HUB_CONFIG__/);
    expect(() => parseEnv({ build: { VITE_API_MODE: "mock", VITE_AUTH_MODE: "mock" }, runtime: undefined, prod: true })).toThrow(/did not load/);
  });

  it("a production build requires /config.js (or the build) to name both modes; there is no default", () => {
    expect(() => parseEnv({ build: {}, runtime: {}, prod: true })).toThrow(/VITE_API_MODE is not set[\s\S]*VITE_AUTH_MODE is not set/);
    expect(() => parseEnv({ build: {}, runtime: { VITE_API_MODE: "http" }, prod: true })).toThrow(/VITE_AUTH_MODE is not set/);
    expect(() => parseEnv({ build: {}, runtime: { VITE_API_MODE: "http" }, prod: true })).not.toThrow(/VITE_API_MODE is not set/);
  });

  it("a production build refuses mock unless the configuration that names it carries the flag", () => {
    const mock = { VITE_API_MODE: "http", VITE_AUTH_MODE: "mock" };
    expect(() => parseEnv({ build: {}, runtime: mock, prod: true })).toThrow(/VITE_AUTH_MODE=mock is refused in a production build/);
    // hub-api in the sandbox with HUB_AUTH=mock: the flag travels with the configuration.
    expect(parseEnv({ build: {}, runtime: { ...mock, HUB_ALLOW_MOCK: true }, prod: true })).toMatchObject(mock);
    expect(parseEnv({ build: {}, runtime: { ...mock, HUB_ALLOW_MOCK: "true" }, prod: true })).toMatchObject(mock);
    expect(() => parseEnv({ build: {}, runtime: { ...mock, HUB_ALLOW_MOCK: false }, prod: true })).toThrow(/refused/);
    expect(() => parseEnv({ build: {}, runtime: { ...mock, HUB_ALLOW_MOCK: "yes" }, prod: true })).toThrow(/refused/);
    // The mock API in production needs the same flag.
    expect(() => parseEnv({ build: {}, runtime: { ...OIDC, VITE_API_MODE: "mock" }, prod: true })).toThrow(/VITE_API_MODE=mock is refused/);
  });

  it("a demo build (VITE_ALLOW_MOCK=1) keeps the development defaults and accepts the mock, so the pixel guard and e2e run on a build", () => {
    expect(parseEnv({ build: { VITE_ALLOW_MOCK: "1" }, runtime: {}, prod: true })).toMatchObject({ VITE_API_MODE: "mock", VITE_AUTH_MODE: "mock" });
    expect(parseEnv({ build: { VITE_ALLOW_MOCK: "1", VITE_API_MODE: "mock", VITE_AUTH_MODE: "mock" }, runtime: undefined, prod: true })).toMatchObject({ VITE_API_MODE: "mock" });
    // hub-api's runtime configuration still wins over the demo build's defaults.
    expect(parseEnv({ build: { VITE_ALLOW_MOCK: "1" }, runtime: OIDC, prod: true })).toMatchObject({ VITE_API_MODE: "http", VITE_AUTH_MODE: "oidc" });
  });

  it("a static host bakes the modes in at build time and the empty /config.js leaves them alone", () => {
    expect(parseEnv({ build: OIDC, runtime: {}, prod: true })).toMatchObject({ VITE_AUTH_MODE: "oidc", VITE_OIDC_CLIENT_ID: "hub-web" });
  });

  it("an incomplete oidc configuration is a readable error naming each missing value", () => {
    expect(() => parseEnv({ build: {}, runtime: { VITE_API_MODE: "http", VITE_AUTH_MODE: "oidc", VITE_OIDC_CLIENT_ID: "hub-web" }, prod: true })).toThrow(
      /Invalid configuration:\n {2}VITE_OIDC_AUTHORITY: VITE_OIDC_AUTHORITY is required when VITE_AUTH_MODE=oidc\n {2}VITE_OIDC_REDIRECT_URI: VITE_OIDC_REDIRECT_URI is required/,
    );
    expect(() => parseEnv({ build: {}, runtime: { ...OIDC, VITE_OIDC_AUTHORITY: "not a url" }, prod: true })).toThrow(/VITE_OIDC_AUTHORITY: Invalid url/);
  });
});
