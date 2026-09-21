// The real sign-in path, end to end: the built hub served by hub-api with HUB_AUTH=oidc, against an OpenID
// Connect provider (scripts/fake_idp.py over TLS). Not the mock personas: Authorization Code + PKCE in the
// browser, an RS256 access token verified through the JWKS, the principal mapped from the token's groups by the
// identity map, and what that person may then do. Run by scripts/smoke-oidc.sh, which starts both processes.
//   HUB_BASE=http://127.0.0.1:18443 IDP_BASE=https://127.0.0.1:9443 node tools/oidctest.cjs
const pw = require("playwright-core");

const HUB = process.env.HUB_BASE || "http://127.0.0.1:18443";
const IDP = process.env.IDP_BASE || "https://127.0.0.1:9443";
let failures = 0;
const check = (ok, what) => { console.log((ok ? "PASS " : "FAIL ") + what); if (!ok) failures++; };

(async () => {
  const browser = await pw.chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, args: ["--no-sandbox"] });
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errors = [], csp = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  if (process.env.OIDC_TRACE) { page.on("framenavigated", (f) => console.log("  frame", f === page.mainFrame() ? "main" : "child", f.url().slice(0, 140))); page.on("console", (m) => console.log("  console", m.type(), m.text().slice(0, 200))); }
  page.on("console", (m) => { const t = m.text(); if (/Content Security Policy/i.test(t)) csp.push(t); else if (m.type() === "error") errors.push(t); });

  // 1. The sign-in page in production mode shows one button and no personas; it goes to the provider and back.
  await page.goto(HUB + "/discover");
  // First the hub asks the provider quietly (prompt=none) whether a session exists; the provider says no.
  await page.waitForURL((u) => u.pathname.startsWith("/signin"), { timeout: 20000 }).catch(() => {});
  check(page.url().startsWith(HUB + "/signin"), "a signed-out person is sent to /signin after the provider reports no session");
  await page.waitForSelector("#signin-sso", { timeout: 20000 }).catch(() => {});
  check((await page.locator("#signin-sso").count()) === 1 && (await page.locator("[id^=persona-]").count()) === 0, "production sign-in: one SSO button, no development personas");
  await page.click("#signin-sso");
  await page.waitForURL((u) => u.pathname.startsWith("/discover"), { timeout: 20000 });
  await page.waitForSelector(".hub:not([data-loading])", { timeout: 20000 });
  check(true, "authorization code + PKCE round trip lands back on Discover");

  // 2. The principal is the token's, through the identity map: a payments lead, ladder L2, entitled to the triage agent.
  const me = await page.evaluate(async () => {
    // The page's own client holds the token in memory; read the resolved principal from the query cache it filled.
    const el = document.querySelector('[aria-label^="Account: "]');
    return { account: el ? el.getAttribute("aria-label") : null, initials: el ? el.textContent.trim() : null };
  });
  check(me.account === "Account: Gil Klainert" && me.initials === "GK", `the account menu shows the token's person (${me.account}, ${me.initials})`);
  const triage = await page.locator('text=Investigation triage').first().count();
  check(triage > 0, "the catalog shows what the mapped group entitles (Investigation triage)");

  // 3. What a real lead may sign: the owner named on a component, by the token's email.
  await page.goto(HUB + "/build/shelf/sign-offs", { waitUntil: "networkidle" });
  await page.waitForSelector(".hub:not([data-loading])", { timeout: 20000 });
  const youCard = await page.locator("text=You may sign as").first().count();
  check(youCard > 0, "sign-offs: the lead whose email local part is the manifest's owner may sign as owner");

  // 4. A reload has no token in memory: the hub renews silently against the provider's session (a hidden frame).
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector(".hub:not([data-loading])", { timeout: 20000 });
  check(page.url().includes("/build/shelf/sign-offs"), "after a reload the session is renewed silently; the person stays on the page");

  // 5. The API refuses the token's bearer nowhere else: the hub's own calls carry it, an anonymous call is 401.
  // The browser context's own request carries every cookie the hub set and none of the hub's memory: a 401 proves
  // the token lives nowhere a cookie or a stored value could carry it.
  const anon = await ctx.request.get(HUB + "/api/me");
  check(anon.status() === 401, "a call with the browser's cookies but no bearer is 401 (the token never leaks into a cookie)");

  // 6. Sign out goes through the provider's end-session and back to the hub signed out.
  await page.click('[aria-label^="Account: "]');
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await page.waitForURL((u) => u.pathname === "/" || u.pathname.startsWith("/signin"), { timeout: 20000 });
  await page.goto(HUB + "/discover", { waitUntil: "networkidle" });
  check(page.url().startsWith(HUB + "/signin"), "after sign-out the hub asks to sign in again");
  await ctx.close();

  // 7. An AI security engineer, by group: may sign for AI security and nothing else.
  const ctx2 = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 900 } });
  const p2 = await ctx2.newPage();
  await p2.goto(HUB + "/signin", { waitUntil: "networkidle" });
  // The provider picks the person from a query on its authorize URL; the hub's redirect carries none, so set the
  // provider's session first, the way a person already signed in at the bank would be.
  await p2.goto(IDP + "/authorize?client_id=hub-web&response_type=code&code_challenge=x&code_challenge_method=S256&redirect_uri=" + encodeURIComponent(HUB + "/auth/callback") + "&persona=security&state=seed", { waitUntil: "commit" }).catch(() => {});
  await p2.goto(HUB + "/signin", { waitUntil: "networkidle" });
  await p2.click("#signin-sso");
  await p2.waitForURL((u) => u.pathname.startsWith("/discover"), { timeout: 20000 });
  await p2.goto(HUB + "/build/shelf/sign-offs", { waitUntil: "networkidle" });
  await p2.waitForSelector(".hub:not([data-loading])", { timeout: 20000 });
  const sec = await p2.locator("text=You may sign as").first().textContent().catch(() => "");
  check(/ai security/i.test(sec || ""), `an AI security engineer (by group) may sign for AI security (${(sec || "").trim()})`);
  await ctx2.close();

  // 8. A person whose directory left the groups out of the token is refused with the reason, not signed in as an employee.
  const ctx3 = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 900 } });
  const p3 = await ctx3.newPage();
  await p3.goto(IDP + "/authorize?client_id=hub-web&response_type=code&code_challenge=x&code_challenge_method=S256&redirect_uri=" + encodeURIComponent(HUB + "/auth/callback") + "&persona=overage&state=seed", { waitUntil: "commit" }).catch(() => {});
  await p3.goto(HUB + "/signin", { waitUntil: "networkidle" });
  await p3.click("#signin-sso");
  // The callback lands on Discover first; the platform's refusal of the principal (403 on /me) then sends the person to /403.
  await p3.waitForURL((u) => u.pathname === "/403", { timeout: 20000 }).catch(() => {});
  check(p3.url().endsWith("/403"), `a groups overage is refused (403), never downgraded to an employee (${new URL(p3.url()).pathname})`);
  const why = await p3.locator("text=Groups not in the token").count();
  check(why > 0, "the refusal names its reason (the identity team's fix), not a generic error");
  await ctx3.close();

  // 9. An employee the directory names only by upn, in no hub group: signed in with the default grants, signs nothing.
  const ctx4 = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 900 } });
  const p4 = await ctx4.newPage();
  await p4.goto(IDP + "/authorize?client_id=hub-web&response_type=code&code_challenge=x&code_challenge_method=S256&redirect_uri=" + encodeURIComponent(HUB + "/auth/callback") + "&persona=employee&state=seed", { waitUntil: "commit" }).catch(() => {});
  // Already signed in at the provider: the hub's quiet first ask succeeds and the person never sees a sign-in page.
  await p4.goto(HUB + "/build/shelf/sign-offs");
  await p4.waitForURL((u) => u.pathname.startsWith("/build/shelf/sign-offs"), { timeout: 20000 });
  await p4.waitForSelector(".hub:not([data-loading])", { timeout: 20000 });
  const emp = await p4.locator('[aria-label^="Account: "]').getAttribute("aria-label").catch(() => null);
  check(emp === "Account: Sam Okafor", `a person with a provider session is signed in without a click, an employee named only by upn as themselves (${emp})`);
  check((await p4.locator("text=You sign nothing yet").count()) > 0, "an employee in no hub group signs nothing");
  await ctx4.close();

  await browser.close();
  check(csp.length === 0, `no Content-Security-Policy violations in the browser${csp.length ? ": " + csp[0] : ""}`);
  check(errors.length === 0, `no page errors${errors.length ? ": " + errors[0] : ""}`);
  console.log(failures ? `\n${failures} check(s) failed` : "\nreal identity: every check passed");
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error("FAILED", e.message); process.exit(1); });
