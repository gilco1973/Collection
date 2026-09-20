// Screenshots for the walkthrough from the real products: the hub (pnpm preview on 4173, mock persona), the
// knowledge-base console (deploy/serve.py on 8765), and terminal outputs rendered from build/term-*.txt.
//   NODE_PATH=../hub/node_modules node capture_shots.cjs
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright-core");

const HUB = process.env.HUB_BASE || "http://localhost:4173";
const KB = process.env.KB_BASE || "http://localhost:8765";
const OUT = path.join(__dirname, "shots");
const VIEW = { width: 1400, height: 1040 };
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const TERM_CSS = [
  "html,body{margin:0;background:#0f1419;color:#d7dde5;font-family:'DejaVu Sans Mono',Menlo,monospace;font-size:22px;line-height:1.5}",
  ".bar{height:52px;background:#1b222b;display:flex;align-items:center;padding:0 18px;color:#8a97a6;font-size:18px}",
  ".dot{width:14px;height:14px;border-radius:50%;display:inline-block;margin-right:10px}",
  "pre{margin:0;padding:28px 32px;white-space:pre-wrap;word-break:break-word;font-family:inherit}",
  ".p{color:#7fd1a0}.c{color:#f4f6f8;font-weight:600}.ok{color:#7fd1a0}",
].join("\n");

function terminalHtml(title, cmd, text) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>${TERM_CSS}</style></head>
  <body><div class="bar"><span class="dot" style="background:#ff5f57"></span><span class="dot" style="background:#febc2e"></span><span class="dot" style="background:#28c840"></span>${esc(title)}</div>
  <pre><span class="p">$</span> <span class="c">${esc(cmd)}</span>\n${esc(text).replace(/\b(OK|ok:.*|PASS|passed.*)$/gm, '<span class="ok">$1</span>')}</pre></body></html>`;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, args: ["--no-sandbox"] });
  const ctx = await browser.newContext({ viewport: VIEW, deviceScaleFactor: 1 });
  await ctx.addInitScript(() => { try { window.sessionStorage.setItem("crai.hub.mockPersona", "gk"); } catch {} });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  const shot = async (name) => { await page.waitForTimeout(500); await page.screenshot({ path: path.join(OUT, name) }); console.log("shot", name); };
  const ready = () => page.waitForSelector(".hub:not([data-loading])", { timeout: 20000 });

  // The hub
  await page.goto(HUB + "/discover", { waitUntil: "networkidle" }); await ready();
  await page.getByRole("tab", { name: "Tools and APIs" }).click(); await page.waitForTimeout(300);
  await page.evaluate(() => document.querySelector('[role="tablist"]')?.scrollIntoView({ block: "start" }));
  await shot("01-discover-tools.png");
  await page.goto(HUB + "/discover/tools/governed-action-loop", { waitUntil: "networkidle" }); await ready(); await shot("02-listing.png");
  await page.goto(HUB + "/discover", { waitUntil: "networkidle" }); await ready();
  await page.keyboard.press("Control+k"); await page.waitForSelector('[role="dialog"]'); await page.keyboard.type("guard"); await page.waitForTimeout(600); await shot("03-search.png");
  await page.goto(HUB + "/learn", { waitUntil: "networkidle" }); await ready();
  await page.evaluate(() => document.getElementById("collection")?.scrollIntoView({ block: "start" })); await shot("04-learn.png");
  await page.goto(HUB + "/build/intake", { waitUntil: "networkidle" }); await ready(); await shot("05-intake.png");

  // The knowledge-base console
  const kbShot = async (route, name) => { await page.goto(KB + route, { waitUntil: "networkidle" }); await page.waitForSelector("article h1, main h1", { timeout: 20000 }); await shot(name); };
  await kbShot("/kb/page/components/README.md", "06-kb-components.png");
  await kbShot("/kb/page/best-practices/action-tiers-and-confirmation.md", "07-kb-practice.png");
  await kbShot("/kb/page/onboarding/ai-champions.md", "08-kb-champions.png");
  await kbShot("/kb/page/skills/README.md", "09-kb-skills.png");

  // Terminal renders
  const term = [["10-term-example.png", "components/python/governed-action-loop", "python3 example.py", "term-example.txt"],
                ["11-term-tests.png", "Collection", "python3 tools/catalog.py --test --only python", "term-tests.txt"],
                ["12-term-list.png", "Collection", "python3 tools/catalog.py --list", "term-list.txt"],
                ["13-term-check.png", "Collection", "python3 tools/catalog.py --write && python3 tools/catalog.py --check", "term-check.txt"]];
  // A fresh page: the console's Content-Security-Policy would otherwise block the inline stylesheet.
  const tpage = await browser.newPage({ viewport: VIEW, deviceScaleFactor: 1 });
  for (const [name, dir, cmd, file] of term) {
    await tpage.setContent(terminalHtml(dir, cmd, fs.readFileSync(path.join(__dirname, "build", file), "utf8")), { waitUntil: "load" });
    await tpage.waitForTimeout(300);
    await tpage.screenshot({ path: path.join(OUT, name) }); console.log("shot", name);
  }
  await browser.close();
  if (errors.length) { console.error("PAGE ERRORS:", errors.join(" | ")); process.exit(1); }
})().catch((e) => { console.error(e); process.exit(1); });
