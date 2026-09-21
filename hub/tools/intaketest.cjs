// Drive the intake brief end to end against the preview build and mock API:
// autosave, step validation, the tier-ceiling rule, filing, and the lead rule.
const pw = require("playwright-core");
const { mockConfig } = require("./mockconfig.cjs");
const BASE = process.env.HUB_BASE || "http://127.0.0.1:4173";
let fails = 0;
const check = (ok, note, extra = "") => { if (!ok) fails++; console.log(`${ok ? "PASS" : "FAIL"}  ${note}${extra ? "   " + extra : ""}`); };

async function session(browser, persona) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1200 }, ignoreHTTPSErrors: true });
  await mockConfig(page);
  await page.addInitScript((id) => { try { window.sessionStorage.setItem("crai.hub.mockPersona", id); } catch {} }, persona);
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  return { page, errors };
}

(async () => {
  const browser = await pw.chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });

  // --- gk: the artboard draft at step 3 ---
  const { page, errors } = await session(browser, "gk");
  await page.goto(BASE + "/build/intake", { waitUntil: "load" });
  await page.waitForSelector(".hub:not([data-loading])");
  check((await page.locator("h1").textContent()) === "Payments returns triage for the collections desk", "draft opens with the artboard title");
  check((await page.locator(".steps button.step.on .t").textContent())?.startsWith("Data and tools"), "resumes at step 3");
  check((await page.locator(".card .ch .chip").first().textContent()) === "draft saved", "save chip: draft saved");

  // Edit: add a system -> chip flips to unsaved, then autosaves.
  await page.getByRole("button", { name: "+ add a system" }).click();
  await page.getByRole("option", { name: /General ledger/ }).click();
  check((await page.locator(".card .ch .chip").first().textContent()) === "unsaved changes", "edit marks the draft unsaved");
  await page.waitForFunction(() => document.querySelector(".card .ch .chip")?.textContent === "draft saved", null, { timeout: 5000 });
  check(true, "autosave lands (chip back to draft saved)");
  check(await page.locator(".chip.accent", { hasText: "General ledger" }).count() === 1, "system chip rendered");

  // Continue with ceiling R and a W1 tool -> validation error on the ceiling.
  await page.getByRole("button", { name: "Continue to Model" }).click();
  await page.waitForTimeout(200);
  const err = await page.locator(".field.invalid .err").first().textContent().catch(() => "");
  check(/tier ceiling must cover every tool/i.test(err || ""), "Continue is blocked by the tier-ceiling rule", err?.slice(0, 70));
  check((await page.locator(".steps button.step.on .t").textContent())?.startsWith("Data and tools"), "still on step 3 after the error");

  // Raise the ceiling to W1 and continue: step 4, road becomes a write profile.
  await page.locator("label.radio", { hasText: "Write with confirmation" }).click();
  await page.getByRole("button", { name: "Continue to Model" }).click();
  await page.waitForFunction(() => document.querySelector(".steps button.step.on .t")?.textContent?.startsWith("Model"), null, { timeout: 5000 });
  check(true, "Continue moves to step 4 · Model");
  await page.waitForFunction(() => /Write profile \(W1\)/.test(document.body.textContent || ""), null, { timeout: 5000 });
  check(true, "road card re-derives for the write profile");
  check(await page.locator(".steps button.step.done").count() === 3, "three steps marked done");

  // Step 5 and review.
  await page.getByRole("button", { name: "Continue to Outcome" }).click();
  await page.waitForFunction(() => document.querySelector(".steps button.step.on .t")?.textContent?.startsWith("Outcome"), null, { timeout: 5000 });
  await page.getByRole("button", { name: "Continue to Review and file" }).click();
  await page.waitForFunction(() => document.querySelector(".steps button.step.on .t")?.textContent?.startsWith("Review"), null, { timeout: 5000 });
  check(true, "reaches 6 · Review and file");
  check(await page.locator(".banner.accent", { hasText: "Lead confirmation" }).count() === 1, "lead (gk) sees the lead-confirmation banner");

  // File without acknowledging -> blocked; acknowledge -> filed.
  await page.getByRole("button", { name: "File the brief" }).click();
  await page.waitForTimeout(200);
  check(/Confirm you have read/.test(await page.locator(".field.invalid .err").first().textContent().catch(() => "") || ""), "filing requires the acknowledgement");
  await page.getByRole("checkbox", { name: /I have read/ }).check();
  await page.getByRole("button", { name: "File the brief" }).click();
  await page.waitForSelector(".banner.ok:has-text('Filed')", { timeout: 8000 });
  check(true, "brief files; filed banner shown");
  check((await page.locator(".card .ch .chip").first().textContent()) === "filed", "status chip: filed");
  check(await page.locator("fieldset:disabled").count() === 1, "form is read-only after filing");

  // Leave and come back in-app (a reload would reset the in-browser mock state).
  await page.locator(".hnav .links a", { hasText: "My workspace" }).click();
  await page.waitForSelector(".hub");
  await page.locator(".hnav .links > *", { hasText: "Build" }).click();
  await page.waitForSelector(".hub");
  check(/Start an intake brief/.test(await page.locator("h1").textContent() || ""), "with no open draft the Build area offers to start one");
  await page.getByRole("button", { name: "Start a brief" }).click();
  await page.waitForURL(/\/build\/intake\/brf_/, { timeout: 8000 }).catch(() => {});
  await page.waitForSelector(".hub:not([data-loading])");
  check(/\/build\/intake\/brf_/.test(page.url()), "Start a brief creates a draft and opens it", page.url());
  check((await page.locator(".steps button.step.on .t").textContent())?.startsWith("Use case"), "new draft starts at step 1");
  await page.getByRole("button", { name: "Continue to People" }).click();
  await page.waitForTimeout(200);
  check(await page.locator(".field.invalid").count() >= 2, "empty step 1 shows field errors");
  check(errors.length === 0, "no page errors (gk)", errors.join(" | "));
  await page.close();

  // --- employee (not a lead): a write profile cannot be filed by them ---
  const e = await session(browser, "employee");
  await e.page.goto(BASE + "/build/intake", { waitUntil: "load" });
  await e.page.waitForSelector(".hub");
  // A brief names the team that owns it: a person in no team is told so instead of being handed a draft that can never be filed.
  check((await e.page.getByRole("button", { name: "Start a brief" }).count()) === 0, "a person in no team is not offered a brief to start");
  check(/no team yet/.test(await e.page.locator("[data-testid=no-team]").textContent().catch(() => "") || ""), "the intake page says why and who to ask");
  check(e.errors.length === 0, "no page errors (employee)", e.errors.join(" | "));
  await e.page.close();

  await browser.close();
  console.log(fails ? `\n${fails} failure(s)` : "\nall intake steps pass");
  process.exit(fails ? 1 : 0);
})();
