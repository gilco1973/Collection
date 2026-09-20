// Deck HTML → one PNG per slide at 2560×1440 (Playwright, headless Chromium).
const { chromium } = require('playwright-core');
const fs = require('fs');
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
  const p = await b.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 2 });
  await p.goto('file://' + process.cwd() + '/deck.html', { waitUntil: 'networkidle' });
  await p.evaluate(() => document.fonts.ready);
  const n = await p.$$eval('section.slide', s => s.length);
  fs.mkdirSync('frames', { recursive: true });
  for (let i = 1; i <= n; i++) {
    const el = await p.$(`#s${String(i).padStart(2, '0')}`);
    await el.screenshot({ path: `frames/slide-${String(i).padStart(2, '0')}.png` });
  }
  await b.close(); console.log('frames', n);
})().catch(e => { console.error(e); process.exit(1); });
