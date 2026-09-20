// Render each design artboard (reference) and the matching app route (candidate) under identical conditions in one
// browser session, so the only variable between the two PNGs is the app itself. Screens come from screens.json:
//   [{"name": "Home", "route": "/discover", "artboard": "Home.html", "height": 1660}, ...]
// Environment: APP_BASE (default http://127.0.0.1:4173), ARTBOARDS (dir), OUT (dir), HASH_ROUTER=1, CHROMIUM_PATH,
// FONTS (a dir with css.css and the woff2 files, so font availability never depends on the network),
// INIT_SCRIPT (a JS file evaluated before the app boots, e.g. to seed a mock sign-in).
const fs = require("fs");
const path = require("path");
const pw = require("playwright-core");

const ROOT = process.cwd();
const SCREENS = JSON.parse(fs.readFileSync(process.env.SCREENS || path.join(ROOT, "screens.json"), "utf8"));
const UX = process.env.ARTBOARDS || path.join(ROOT, "artboards");
const OUT = process.env.OUT || path.join(ROOT, "compare");
const BASE = process.env.APP_BASE || "http://127.0.0.1:4173";
const HASH = process.env.HASH_ROUTER === "1";
const FONTS = process.env.FONTS;
const INIT = process.env.INIT_SCRIPT ? fs.readFileSync(process.env.INIT_SCRIPT, "utf8") : null;

async function offlineFonts(page) {
  if (!FONTS) return;
  await page.route("**/fonts.googleapis.com/**", (route) => route.fulfill({ status: 200, contentType: "text/css; charset=utf-8", body: fs.readFileSync(path.join(FONTS, "css.css")) }));
  await page.route("**/fonts.gstatic.com/**", (route) => {
    const file = path.join(FONTS, path.basename(new URL(route.request().url()).pathname));
    return fs.existsSync(file) ? route.fulfill({ status: 200, contentType: "font/woff2", body: fs.readFileSync(file) }) : route.abort();
  });
}

async function settle(page) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(600);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await pw.chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
  let failures = 0;
  for (const s of SCREENS) {
    const viewport = { width: s.width || 1440, height: s.height };
    const ref = await browser.newPage({ viewport, deviceScaleFactor: 1, ignoreHTTPSErrors: true });
    await offlineFonts(ref);
    const errors = [];
    ref.on("pageerror", (e) => errors.push("ref: " + e));
    await ref.setContent(fs.readFileSync(path.join(UX, s.artboard), "utf8"), { waitUntil: "load" });
    await settle(ref);
    await ref.screenshot({ path: path.join(OUT, `${s.name}.ref.png`), fullPage: false });
    await ref.close();

    const app = await browser.newPage({ viewport, deviceScaleFactor: 1, ignoreHTTPSErrors: true });
    await offlineFonts(app);
    if (INIT) await app.addInitScript(INIT);
    app.on("pageerror", (e) => errors.push("app: " + e));
    app.on("console", (m) => { if (m.type() === "error") errors.push("app: " + m.text()); });
    await app.goto(BASE + (HASH ? "/#" : "") + s.route, { waitUntil: "load" });
    if (s.readySelector) await app.waitForSelector(s.readySelector, { timeout: 15000 });
    await settle(app);
    await app.screenshot({ path: path.join(OUT, `${s.name}.app.png`), fullPage: false });
    await app.close();
    if (errors.length) failures++;
    console.log(`${s.name.padEnd(14)} ${s.route.padEnd(40)}${errors.length ? "  ERRORS: " + errors.join(" | ") : "  ok"}`);
  }
  await browser.close();
  process.exit(failures ? 1 : 0);
})();
