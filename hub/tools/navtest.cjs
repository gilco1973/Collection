// Exercise the delegated navigation in HubShell end to end: primary nav links,
// in-page buttons, and browser back. Fails non-zero on the first miss.
const pw = require("playwright-core");
const { mockConfig } = require("./mockconfig.cjs");
const BASE = process.env.HUB_BASE || "http://127.0.0.1:4173";
const steps = [
  { do: async (p) => p.goto(BASE + "/"),                                            expect: "/discover",                              note: "root redirects to Discover" },
  { do: async (p) => p.locator(".hnav .links > *", { hasText: "My workspace" }).click(), expect: "/workspace",                         note: "nav: My workspace" },
  { do: async (p) => p.locator(".btn", { hasText: "Start a brief" }).first().click(),     expect: "/build/intake",                      note: "workspace: Start a brief -> intake" },
  { do: async (p) => p.locator(".hnav .links .on").click(),                                expect: "/build/intake",                      note: "intake: active nav is Build (live chrome)" },
  { do: async (p) => p.locator(".hnav .links a", { hasText: "Discover" }).click(),        expect: "/discover",                          note: "intake: nav Discover (live chrome link)" },
  { do: async (p) => p.locator(".lc", { hasText: "Investigation triage" }).locator(".btn").click(), expect: "/discover/agents/investigation-triage", note: "discover: Open (Investigation triage) -> listing" },
  { do: async (p) => p.locator(".btn", { hasText: "Try in playground" }).click(),         expect: "/assistant/investigation-triage",    note: "listing: Try in playground -> assistant" },
  { do: async (p) => p.goBack(),                                                          expect: "/discover/agents/investigation-triage", note: "browser back -> listing" },
  { do: async (p) => p.locator(".hnav .links > *", { hasText: "Learn" }).click(),       expect: "/learn",                             note: "nav: Learn" },
  { do: async (p) => p.locator(".hnav .links > *", { hasText: "Build" }).click(),       expect: "/build/intake",                      note: "nav: Build -> intake" },
  { do: async (p) => p.locator(".hnav .links > *", { hasText: "Discover" }).click(),    expect: "/discover",                          note: "nav: Discover" },
];
(async () => {
  const browser = await pw.chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, ignoreHTTPSErrors: true });
  await mockConfig(page);
  // Sign in as the artboard persona before the app boots (mock auth mode).
  await page.addInitScript(() => { try { window.sessionStorage.setItem("crai.hub.mockPersona", "gk"); } catch {} });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  let fails = 0;
  for (const s of steps) {
    await s.do(page);
    await page.waitForSelector(".hub:not([data-loading])", { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(150);
    const got = new URL(page.url()).pathname;
    const on = await page.locator(".hnav .links .on").first().textContent().catch(() => "?");
    const ok = got === s.expect;
    if (!ok) fails++;
    console.log(`${ok ? "PASS" : "FAIL"}  ${s.note.padEnd(46)} -> ${got}${ok ? "" : "   (expected " + s.expect + ")"}   active nav: ${on?.trim()}`);
  }
  await browser.close();
  if (errors.length) { console.log("PAGE ERRORS:", errors.join(" | ")); fails++; }
  console.log(fails ? `\n${fails} failure(s)` : "\nall navigation steps pass, no page errors");
  process.exit(fails ? 1 : 0);
})();
