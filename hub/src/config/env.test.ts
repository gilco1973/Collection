import { describe, expect, it } from "vitest";

describe("runtime configuration", () => {
  it("lets /config.js override build-time values, ignoring anything that is not a VITE_ string", async () => {
    window.__HUB_CONFIG__ = { VITE_API_MODE: "http", VITE_KB_URL: "https://kb.example", NOT_VITE: "x", VITE_ROUTER: "" } as Record<string, string>;
    const { env } = await import("./env");
    expect(env.VITE_API_MODE).toBe("http");
    expect(env.VITE_KB_URL).toBe("https://kb.example");
    expect(env.VITE_ROUTER).toBe("browser");
    expect((env as Record<string, unknown>).NOT_VITE).toBeUndefined();
  });
});
