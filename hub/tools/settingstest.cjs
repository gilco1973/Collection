// Settings: preferences apply at once, are saved through the API, and survive
// in-app navigation; dark theme, density and accessibility stamp the root.
const pw = require("playwright-core");
const BASE = process.env.HUB_BASE || "http://127.0.0.1:4173";
let fails = 0;
const check = (ok, note, extra = "") => { if (!ok) fails++; console.log(`${ok ? "PASS" : "FAIL"}  ${note}${extra ? "   " + extra : ""}`); };
const ready = (p) => p.waitForSelector(".hub:not([data-loading])", { timeout: 15000 });
(async () => {
  const browser = await pw.chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, ignoreHTTPSErrors: true });
  await page.addInitScript(() => { try { window.sessionStorage.setItem("crai.hub.mockPersona", "gk"); } catch {} });
  const errors = []; page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(BASE + "/settings", { waitUntil: "load" }); await ready(page);
  check((await page.locator("h1").textContent()) === "Settings", "settings page opens");
  check(await page.locator("html[data-theme]").count() === 0, "system theme: no stamp on the root");
  await page.getByRole("radio", { name: "Dark" }).click();
  await page.waitForFunction(() => document.documentElement.dataset.theme === "dark", null, { timeout: 3000 });
  check(true, "dark theme stamps data-theme=dark at once");
  await page.waitForFunction(() => document.querySelector(".row .chip[role=status]")?.textContent === "saved", null, { timeout: 5000 });
  check(true, "preferences saved through PUT /me/preferences");
  const bg = await page.evaluate(() => getComputedStyle(document.querySelector(".hub")).backgroundColor);
  check(bg === "rgb(16, 20, 24)", "dark background token applied", bg);
  await page.getByRole("radio", { name: "Dense" }).click();
  await page.waitForFunction(() => document.documentElement.dataset.density === "dense", null, { timeout: 3000 });
  check(true, "dense density stamps the root");
  await page.getByRole("switch", { name: /assistive technology/ }).check();
  await page.waitForFunction(() => document.documentElement.dataset.a11y === "true", null, { timeout: 3000 });
  check(true, "accessibility preference stamps the root");
  // Survives in-app navigation (the principal is cached; the mock keeps prefs for the page).
  await page.locator(".hnav .links a", { hasText: "Discover" }).click(); await ready(page);
  check(await page.evaluate(() => document.documentElement.dataset.theme === "dark" && document.documentElement.dataset.density === "dense"), "preferences persist across navigation");
  await page.screenshot({ path: "compare/_settings_dark_discover.png", fullPage: false });
  await page.goto(BASE + "/assistant", { waitUntil: "load" }); await ready(page);
  await page.screenshot({ path: "compare/_settings_dark_assistant.png", fullPage: false });
  check(errors.length === 0, "no page errors", errors.join(" | "));
  await browser.close();
  console.log(fails ? `\n${fails} failure(s)` : "\nall settings steps pass");
  process.exit(fails ? 1 : 0);
})();
