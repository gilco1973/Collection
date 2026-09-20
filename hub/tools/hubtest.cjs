// Drive Discover, a listing, the workspace and the ⌘K palette end to end
// against the preview build and the mock API: entitlement and ladder
// requests, catalog tabs and views, key rotation, and role-based visibility.
const pw = require("playwright-core");
const BASE = process.env.HUB_BASE || "http://127.0.0.1:4173";
let fails = 0;
const check = (ok, note, extra = "") => { if (!ok) fails++; console.log(`${ok ? "PASS" : "FAIL"}  ${note}${extra ? "   " + extra : ""}`); };

async function session(browser, persona) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1200 }, ignoreHTTPSErrors: true });
  await page.addInitScript((id) => { try { window.sessionStorage.setItem("crai.hub.mockPersona", id); } catch {} }, persona);
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  return { page, errors };
}
const ready = (p) => p.waitForSelector(".hub:not([data-loading])", { timeout: 15000 });

(async () => {
  const browser = await pw.chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });

  // --- gk ---
  const { page, errors } = await session(browser, "gk");
  await page.goto(BASE + "/discover", { waitUntil: "load" }); await ready(page);
  check((await page.locator(".hero .chip.line").textContent()) === "Gil Klainert · ops.lead · team-payments-ops", "hero chip is built from the principal");
  check(await page.locator(".hsec").first().locator(".lc").count() === 4, "four listings available to gk");
  check(await page.locator(".lc", { hasText: "Compliance narration" }).locator(".btn:has-text('Requested')").count() === 1, "pending role request shows as Requested (disabled)");

  // Tabs and list view.
  await page.getByRole("tab", { name: "Agents" }).click();
  check(await page.locator(".hsec").nth(1).locator(".lc").count() === 3, "Agents tab shows three agents");
  await page.getByRole("tab", { name: "Roads and templates" }).click();
  check(await page.locator(".hsec").nth(1).locator(".lc").count() === 2, "Roads tab shows two templates");
  await page.getByRole("radio", { name: "List" }).click();
  check(await page.locator(".hsec").nth(1).locator("table.t tbody tr").count() === 2, "list view of the same tab");
  await page.getByRole("tab", { name: /^All/ }).click();
  check(await page.locator(".hsec").nth(1).locator("table.t tbody tr").count() === 9, "list view of All shows all nine listings");
  await page.getByRole("radio", { name: "Cards" }).click();

  // Request access on a card (payments exception agent · approver role).
  await page.locator(".lc", { hasText: "Payments exception agent" }).locator(".btn", { hasText: "Request access" }).click();
  await page.waitForSelector(".toasts .banner:has-text('Request sent')", { timeout: 5000 });
  check(true, "request access sends and toasts");
  check(await page.locator(".lc", { hasText: "Payments exception agent" }).locator(".btn:has-text('Requested')").count() === 1, "card flips to Requested");

  // Listing: open, ladder request state, evidence links, changelog.
  await page.locator(".lc", { hasText: "Investigation triage" }).locator(".btn", { hasText: "Open" }).click();
  await ready(page);
  check(/\/discover\/agents\/investigation-triage$/.test(page.url()), "Open on an agent card goes to its listing", page.url());
  check((await page.title()).startsWith("Investigation triage"), "document title is the listing name", await page.title());
  check(await page.locator(".btn", { hasText: "Ladder L2 requested" }).count() === 1, "pending ladder request is reflected on the listing");
  check(await page.locator("table.t tbody tr").count() === 5, "five catalog operations");
  check(await page.locator("a[href^='https://catalog.crai.internal']").count() === 1, "changelog links to the catalog record");

  // Workspace: new request present (in-app navigation keeps the mock state), rotate key.
  await page.locator(".hnav .links a", { hasText: "My workspace" }).click(); await ready(page);
  check(await page.locator(".card", { hasText: "Your requests" }).locator(".row", { hasText: "Payments exception agent" }).count() === 1, "workspace lists the new request");
  const before = await page.locator(".card", { hasText: "Playground" }).locator(".mono").nth(1).textContent();
  await page.getByRole("button", { name: "rotate" }).click();
  await page.waitForSelector(".toasts .banner:has-text('rotated')", { timeout: 5000 });
  const after = await page.locator(".card", { hasText: "Playground" }).locator(".mono").nth(1).textContent();
  check(before !== after && /^crai_pg_…/.test(after || ""), "playground key rotates in place", `${before} -> ${after}`);
  check(await page.locator(".card", { hasText: "team’s consumers" }).locator("a[href='/build/intake/brf_7c1e']").count() === 1, "draft consumer links to its brief");

  // Palette: ⌘K, search, keyboard open.
  await page.keyboard.press("Control+K");
  await page.waitForSelector(".palette", { timeout: 3000 });
  await page.keyboard.type("sanction");
  await page.waitForSelector(".palette .opt:has-text('Sanctions screening')", { timeout: 5000 });
  await page.keyboard.press("Enter");
  await ready(page);
  check(/\/discover\/tools\/sanctions-screening$/.test(page.url()), "palette opens a listing from a search", page.url());
  check(await page.locator(".palette").count() === 0, "palette closes after running");
  await page.keyboard.press("Control+K");
  await page.keyboard.type("late inbound file procedure");
  await page.locator(".palette .opt", { hasText: "Ask the employee assistant" }).click();
  check(/\/assistant\/employee-assistant\?q=late/.test(page.url()), "a free-text query is offered to the assistant", page.url());

  // Account menu (on a live page): sign out returns to /signin.
  await page.locator(".hnav .links > *", { hasText: "My workspace" }).click(); await ready(page);
  await page.getByRole("button", { name: /^Account:/ }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await page.waitForURL(/\/signin/, { timeout: 5000 });
  check(true, "sign out from the account menu");
  check(errors.length === 0, "no page errors (gk)", errors.join(" | "));
  await page.close();

  // --- employee (L0, no team, no lead role) ---
  const e = await session(browser, "employee");
  await e.page.goto(BASE + "/discover", { waitUntil: "load" }); await ready(e.page);
  check((await e.page.locator(".hero .chip.line").textContent()) === "Sam Okafor · employee · no team", "employee hero chip");
  await e.page.goto(BASE + "/discover/agents/investigation-triage", { waitUntil: "load" }); await ready(e.page);
  check(await e.page.locator(".btn", { hasText: "Request ladder" }).count() === 0, "employee is not offered a ladder request (no grant)");
  check(await e.page.locator(".btn", { hasText: "Open in the portal" }).count() === 0, "employee is not offered Open on a consumer they lack");
  check(await e.page.locator(".btn", { hasText: "Request access" }).count() === 1, "employee may request access");
  await e.page.goto(BASE + "/discover/agents/no-such-listing", { waitUntil: "load" });
  await ready(e.page);
  check(/does not exist|nothing here/i.test(await e.page.locator("body").textContent() || ""), "unknown listing renders the not-found page");
  check(e.errors.length === 0, "no page errors (employee)", e.errors.join(" | "));
  await e.page.close();

  await browser.close();
  console.log(fails ? `\n${fails} failure(s)` : "\nall hub steps pass");
  process.exit(fails ? 1 : 0);
})();
