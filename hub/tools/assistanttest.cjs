// Drive the assistant end to end: the recorded conversation, a streamed
// answer with tool call and citation, stop mid-stream, feedback, handoff,
// switching assistant, a new conversation, and role-based assistant choice.
const pw = require("playwright-core");
const BASE = process.env.HUB_BASE || "http://127.0.0.1:4173";
let fails = 0;
const check = (ok, note, extra = "") => { if (!ok) fails++; console.log(`${ok ? "PASS" : "FAIL"}  ${note}${extra ? "   " + extra : ""}`); };
async function session(browser, persona) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, ignoreHTTPSErrors: true });
  await page.addInitScript((id) => { try { window.sessionStorage.setItem("crai.hub.mockPersona", id); } catch {} }, persona);
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  return { page, errors };
}
const ready = (p) => p.waitForSelector(".hub:not([data-loading])", { timeout: 15000 });

(async () => {
  const browser = await pw.chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
  const { page, errors } = await session(browser, "gk");
  await page.goto(BASE + "/assistant", { waitUntil: "load" }); await ready(page);
  check(await page.locator(".turn").count() === 2, "recorded conversation shows two turns");
  check(await page.locator(".turn .claim").count() === 3, "three marked claims in the recorded answer");
  check(await page.locator(".turn .cite").count() === 3, "three citations rendered");
  check(await page.locator(".fb").count() === 1, "feedback row for the last answer");

  // Send a follow-up and watch it stream.
  await page.fill("textarea.in", "What is the cut-off for wires?");
  await page.keyboard.press("Enter");
  await page.waitForSelector(".stopbtn", { timeout: 5000 });
  check(true, "Stop button appears while streaming");
  await page.waitForSelector(".turn .tool:has-text('knowledge.search')", { timeout: 8000 });
  check(true, "tool call view rendered during the stream");
  await page.waitForSelector(".btn.ink:has-text('Send')", { timeout: 15000 });
  check(await page.locator(".turn").count() === 4, "two more turns after the answer");
  check(await page.locator(".turn").nth(3).locator(".cite").count() === 1, "streamed answer carries its citation");
  check(await page.locator(".turn").nth(3).locator(".budget").count() === 1, "budget view rendered");
  check((await page.locator(".card .conv").first().textContent() || "").includes("Late inbound file procedure"), "a follow-up keeps the conversation's title");

  // Feedback on the streamed answer, then handoff.
  await page.locator(".fb .btn", { hasText: "Yes" }).click();
  await page.waitForSelector(".fb:has-text('Thanks')", { timeout: 5000 });
  check(true, "feedback answered once");
  await page.getByRole("button", { name: "Talk to a person" }).click();
  await page.waitForSelector(".banner.accent:has-text('Handed to a person')", { timeout: 5000 });
  check(true, "handoff view rendered");

  // Stop mid-stream.
  await page.fill("textarea.in", "And for ACH?");
  await page.keyboard.press("Enter");
  await page.waitForSelector(".stopbtn", { timeout: 5000 });
  await page.locator(".stopbtn").click();
  await page.waitForSelector(".turn .banner.warn:has-text('Stopped')", { timeout: 5000 });
  check(true, "stopping records a stop view (human.interrupt)");
  await page.waitForSelector(".btn.ink:has-text('Send')", { timeout: 5000 });
  check(await page.locator(".fb").count() === 0, "a stopped answer asks for no feedback");

  // Switch assistant, start a new conversation.
  await page.locator("label.radio", { hasText: "Investigation triage" }).click();
  await page.waitForURL(/\/assistant\/investigation-triage/, { timeout: 5000 });
  await ready(page);
  check((await page.locator(".card .ch h3").nth(1).textContent()) === "Investigation triage", "assistant switches");
  await page.getByRole("button", { name: "New conversation" }).click();
  check(await page.locator(".turn").count() === 0, "new conversation is empty until the first send");
  await page.fill("textarea.in", "Why did R-1187 bounce?");
  await page.keyboard.press("Enter");
  await page.waitForSelector(".btn.ink:has-text('Send')", { timeout: 15000 });
  check(await page.locator(".turn").count() === 2, "first send creates the conversation and streams an answer");
  check((await page.locator(".card .conv").first().textContent() || "").includes("Why did R-1187 bounce?"), "new conversation is listed under its first message");

  // Query prefill from the palette route.
  await page.goto(BASE + "/assistant/employee-assistant?q=late%20inbound%20file%20procedure", { waitUntil: "load" }); await ready(page);
  check((await page.inputValue("textarea.in")) === "late inbound file procedure", "?q= prefills the composer");
  check(errors.length === 0, "no page errors (gk)", errors.join(" | "));
  await page.close();

  // employee: only the employee assistant is offered; an agent they lack is refused.
  const e = await session(browser, "employee");
  await e.page.goto(BASE + "/assistant", { waitUntil: "load" }); await ready(e.page);
  check(await e.page.locator("label.radio").count() === 1, "employee sees one assistant");
  await e.page.goto(BASE + "/assistant/investigation-triage", { waitUntil: "load" }); await ready(e.page);
  check(/not open to your role/.test(await e.page.locator("body").textContent() || ""), "employee opening an agent they lack is told why");
  check(e.errors.length === 0, "no page errors (employee)", e.errors.join(" | "));
  await e.page.close();
  await browser.close();
  console.log(fails ? `\n${fails} failure(s)` : "\nall assistant steps pass");
  process.exit(fails ? 1 : 0);
})();
