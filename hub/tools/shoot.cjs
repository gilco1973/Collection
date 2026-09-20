// Render each artboard (reference) and the matching app route (candidate)
// under identical conditions in one browser session, so the only variable
// between the two PNGs is the app itself.
const fs = require("fs");
const path = require("path");
const pw = require("playwright-core");

const ROOT = path.resolve(__dirname, "..");
const UX = process.env.HUB_ARTBOARDS || path.join(ROOT, "artboards");
const OUT = path.join(ROOT, "compare");
const BASE = process.env.HUB_BASE || "http://127.0.0.1:4173";
const HASH = process.env.HUB_HASH === "1"; // hash-routed build: /#/discover
// The app is guarded by sign-in. In mock auth mode the persona is read from
// sessionStorage, so seed it before any script runs; `gk` is the artboard user.
const PERSONA = process.env.HUB_PERSONA || "gk";
async function signIn(page) {
  await page.addInitScript((id) => { try { window.sessionStorage.setItem("crai.hub.mockPersona", id); } catch {} }, PERSONA);
}

const SCREENS = [
  { name: "HubHome", route: "/discover" },
  { name: "HubListing", route: "/discover/agents/investigation-triage" },
  { name: "HubIntake", route: "/build/intake" },
  { name: "HubWorkspace", route: "/workspace" },
  { name: "HubAssistant", route: "/assistant" },
];

// Serve the Google Fonts CSS and woff2 files from a local cache (tools/fonts/,
// fetched once by tools/fetch-fonts) on BOTH pages, so font availability is
// identical for reference and candidate and never depends on the network.
const FONTS = path.join(__dirname, "fonts");
async function offlineFonts(page) {
  await page.route("**/fonts.googleapis.com/**", (route) =>
    route.fulfill({ status: 200, contentType: "text/css; charset=utf-8", body: fs.readFileSync(path.join(FONTS, "css.css")) }));
  await page.route("**/fonts.gstatic.com/**", (route) => {
    const file = path.join(FONTS, path.basename(new URL(route.request().url()).pathname));
    if (fs.existsSync(file)) return route.fulfill({ status: 200, contentType: "font/woff2", body: fs.readFileSync(file) });
    return route.abort();
  });
}

async function settle(page) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(600);
  return page.evaluate(() => {
    const want = ['Instrument Sans', 'Geist Mono'];
    const loaded = new Set();
    document.fonts.forEach((f) => { if (f.status === 'loaded') loaded.add(f.family.replace(/"/g, '')); });
    return want.map((w) => `${w}:${loaded.has(w) ? 'loaded' : 'MISSING'}`).join(' ');
  });
}

(async () => {
  const meta = JSON.parse(fs.readFileSync(path.join(ROOT, "extract", "meta.json"), "utf8"));
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await pw.chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
  for (const s of SCREENS) {
    const h = meta[s.name].height;
    const viewport = { width: 1440, height: h };

    // Reference: the artboard file itself.
    const ref = await browser.newPage({ viewport, deviceScaleFactor: 1, ignoreHTTPSErrors: true });
    await offlineFonts(ref);
    const html = fs
      .readFileSync(path.join(UX, `${s.name}.dc.html`), "utf8")
      .replace('<script src="./support.js"></script>', "");
    const refErrors = [];
    ref.on("pageerror", (e) => refErrors.push(String(e)));
    ref.on("console", (m) => { if (m.type() === "error") refErrors.push(m.text()); });
    await ref.setContent(html, { waitUntil: "load" });
    const refFonts = await settle(ref);
    await ref.screenshot({ path: path.join(OUT, `${s.name}.ref.png`), fullPage: false });
    await ref.close();

    // Candidate: the React app route.
    const app = await browser.newPage({ viewport, deviceScaleFactor: 1, ignoreHTTPSErrors: true });
    await offlineFonts(app);
    await signIn(app);
    const errors = [];
    app.on("pageerror", (e) => errors.push(String(e)));
    app.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    await app.goto(BASE + (HASH ? "/#" : "") + s.route, { waitUntil: "load" });
    // Live screens carry data-loading while their queries resolve.
    await app.waitForSelector(".hub:not([data-loading])", { timeout: 15000 });
    // The guide is drawn over every screen, never inside the artboard markup; hide it so the compare is page to page.
    await app.addStyleTag({ content: ".guide-launcher, #hub-guide { display: none !important; }" });
    const appFonts = await settle(app);
    await app.screenshot({ path: path.join(OUT, `${s.name}.app.png`), fullPage: false });
    const box = await app.evaluate(() => {
      const el = document.querySelector(".hub");
      const r = el.getBoundingClientRect();
      return { x: r.x, y: r.y, w: r.width, h: r.height };
    });
    await app.close();
    console.log(`${s.name.padEnd(13)} ${s.route.padEnd(40)} .hub ${box.w}x${box.h}  ref[${refFonts}] app[${appFonts}]${refErrors.length ? "  REF-ERRORS: " + refErrors.join(" | ") : ""}${errors.length ? "  APP-ERRORS: " + errors.join(" | ") : ""}`);
  }
  await browser.close();
})();
