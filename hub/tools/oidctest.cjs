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

  // 10. What the person sees when the provider says no, or cannot be reached: plain words, never a spinner that
  // stays, never a raw code as the headline. Each case in its own context, so nothing carries over.
  const fresh = async () => { const c = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 900 } }); return [c, await c.newPage()]; };
  const banner = (p) => p.locator(".banner").first().innerText().then((t) => t.replace(/\s+/g, " ").trim()).catch(() => "");
  const seedAs = (p, persona) => p.goto(IDP + "/authorize?client_id=hub-web&response_type=code&code_challenge=x&code_challenge_method=S256&redirect_uri=" + encodeURIComponent(HUB + "/auth/callback") + "&persona=" + persona + "&state=seed", { waitUntil: "commit" }).catch(() => {});

  // 10a. The provider answers the callback with an error (the person cancelled at the bank's page).
  { const [c, p] = await fresh();
    await p.goto(HUB + "/auth/callback?error=access_denied&error_description=The+person+cancelled&state=abc");
    await p.waitForURL((u) => u.pathname.startsWith("/signin"), { timeout: 20000 }).catch(() => {});
    const b = await banner(p);
    check(new URL(p.url()).pathname === "/signin" && /The person cancelled/.test(b) && (await p.locator("#signin-sso").count()) === 1, `a callback the provider refused lands on /signin with the provider's reason, never a spinner (${b})`);
    await c.close(); }

  // 10b. A callback without state, and a used callback link loaded again: the link was already used.
  { const [c, p] = await fresh();
    await p.goto(HUB + "/auth/callback?code=abc");
    await p.waitForURL((u) => u.pathname.startsWith("/signin"), { timeout: 20000 }).catch(() => {});
    check(new URL(p.url()).pathname === "/signin" && /already used/.test(await banner(p)), "a callback without state lands on /signin: the link was already used");
    let cbUrl = "";
    p.on("request", (r) => { if (r.url().startsWith(HUB + "/auth/callback?code=")) cbUrl = r.url(); });
    await p.click("#signin-sso");
    await p.waitForURL((u) => u.pathname.startsWith("/discover"), { timeout: 20000 });
    await p.waitForSelector(".hub:not([data-loading])", { timeout: 20000 });
    await p.goto(cbUrl);
    await p.waitForURL((u) => u.pathname.startsWith("/signin"), { timeout: 20000 }).catch(() => {});
    check(cbUrl !== "" && new URL(p.url()).pathname === "/signin" && /already used/.test(await banner(p)), "a replayed callback link lands on /signin: the link was already used, not a spinner");
    await c.close(); }

  // 10c. Sign-out against a provider whose discovery names no end_session_endpoint: the hub is still signed out.
  { const [c, p] = await fresh();
    await p.route(IDP + "/.well-known/openid-configuration", async (route) => {
      const res = await route.fetch(); const doc = await res.json(); delete doc.end_session_endpoint;
      await route.fulfill({ status: 200, contentType: "application/json", headers: { "access-control-allow-origin": HUB }, body: JSON.stringify(doc) });
    });
    await p.goto(HUB + "/signin"); await p.waitForSelector("#signin-sso", { timeout: 20000 }); await p.click("#signin-sso");
    await p.waitForURL((u) => u.pathname.startsWith("/discover"), { timeout: 20000 });
    await p.waitForSelector(".hub:not([data-loading])", { timeout: 20000 });
    await p.click('[aria-label^="Account: "]');
    await p.getByRole("menuitem", { name: "Sign out" }).click();
    await p.waitForURL((u) => u.pathname.startsWith("/signin"), { timeout: 20000 }).catch(() => {});
    const acct = await p.locator('[aria-label^="Account: "]').count();
    check(new URL(p.url()).pathname === "/signin" && acct === 0, `sign-out with no end-session endpoint still signs the hub out and shows /signin (${new URL(p.url()).pathname}, account menus: ${acct})`);
    await c.close(); }

  // 10d. The provider cannot be reached: the button says so and works again, instead of failing silently.
  { const [c, p] = await fresh();
    await p.route(IDP + "/**", (route) => route.abort("connectionrefused"));
    await p.goto(HUB + "/discover");
    await p.waitForSelector("#signin-sso", { timeout: 20000 });
    await p.click("#signin-sso");
    await p.waitForSelector(".banner", { timeout: 20000 }).catch(() => {});
    const b = await banner(p);
    check(/could not be reached/.test(b) && !(await p.locator("#signin-sso").isDisabled()), `an unreachable provider is named on the sign-in page and the button is usable again (${b})`);
    await c.close(); }

  // 10e. A refused silent renew (the provider's session gone) is said in plain words; the provider's code is the detail.
  // The `brief` persona's token lasts 70 s, so the renew (60 s before expiry) fires within seconds.
  { const [c, p] = await fresh();
    await seedAs(p, "brief");
    await p.goto(HUB + "/discover");
    await p.waitForSelector(".hub:not([data-loading])", { timeout: 20000 });
    await c.clearCookies();
    await p.waitForURL((u) => u.pathname.startsWith("/signin"), { timeout: 40000 }).catch(() => {});
    const b = await banner(p);
    const detail = await p.locator("[data-signin-detail]").innerText().catch(() => "");
    check(/Your sign-in at the identity provider has ended/.test(b) && detail.trim() === "login_required", `a refused silent renew says the session ended, with the provider's code as the detail (${b})`);
    await c.close(); }

  await browser.close();
  check(csp.length === 0, `no Content-Security-Policy violations in the browser${csp.length ? ": " + csp[0] : ""}`);
  check(errors.length === 0, `no page errors${errors.length ? ": " + errors[0] : ""}`);
  console.log(failures ? `\n${failures} check(s) failed` : "\nreal identity: every check passed");
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error("FAILED", e.message); process.exit(1); });
