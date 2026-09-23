"""Builds pages/interface.html: the playground's own page (static/) replaying a recorded session.

Run from the playground directory: python3 tools/pages/build.py. To record the session again first:
python3 tools/pages/record.py. tests/test_pages.py refuses a page that is out of date.
"""
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
PG = HERE.parent.parent
OUT = PG / "pages" / "interface.html"
HEAD = '<!doctype html>\n<html lang="en">\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'


def build():
    static = PG / "aiplayground" / "static"
    css = (static / "app.css").read_text()
    js = (static / "app.js").read_text()
    html = (static / "index.html").read_text()
    fx = json.loads((HERE / "fixtures.json").read_text())

    # three-state theme: tokens for dark under the media query (unless light is chosen) and under data-theme="dark"
    m = re.search(r"@media \(prefers-color-scheme: dark\) \{\s*:root \{(.*?)\}\s*\}", css, re.S)
    dark = m.group(1).strip()
    css = css.replace(m.group(0), "@media (prefers-color-scheme: dark) { :root:not([data-theme=\"light\"]) { " + dark + " color-scheme: dark; } }\n"
                      ":root[data-theme=\"dark\"] { " + dark + " color-scheme: dark; }")
    css = css.replace("@media (prefers-color-scheme: dark) { button.primary { color: #0b1220; } }",
                      "@media (prefers-color-scheme: dark) { :root:not([data-theme=\"light\"]) button.primary { color: #0b1220; } }\n:root[data-theme=\"dark\"] button.primary { color: #0b1220; }")
    assert ":root[data-theme=\"dark\"] { --bg: #0f1419" in css and ":root:not([data-theme=\"light\"]) { --bg: #0f1419" in css
    css = css.replace("header.top { position: sticky; top: 0;", "header.top { position: sticky; top: env(safe-area-inset-top, 0px);")

    body = html[html.index("<body>") + 6: html.index("<script")]
    chips = "".join(f'<button type="button" class="rq" data-q="{i}">{label}</button>' for i, label in enumerate(
        ["Sky colour", "Override instruction", "Money transfer", "Hidden instruction in a runbook", "Runbook question", "Secret in the instructions"]))
    tchips = "".join(f'<button type="button" class="rt" data-t="{i}">{label}</button>' for i, label in enumerate(
        ["Read a runbook", "Path traversal", "SQL with a quote", "Delete a ticket"]))
    banner = f'''<aside class="replay" aria-label="About this page">
      <div class="replay-in">
        <p><b>The AI Playground's own interface</b>, replaying a session recorded on a real playground: four sample solutions and four real reports. Set your name at the top right; runs and triage follow the real rules.</p>
        <div class="replay-row"><span>Try it, recorded questions:</span>{chips}</div>
        <div class="replay-row"><span>Recorded tool calls:</span>{tchips}</div>
      </div>
    </aside>'''
    extra_css = """
    .replay { background: var(--ink); color: var(--bg); padding-block: 10px; padding-inline: 16px; font-size: 13.5px; }
    .replay-in { max-width: 1120px; margin: 0 auto; display: grid; gap: 8px; }
    .replay p { margin: 0; }
    .replay-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
    .replay-row span { opacity: .75; margin-right: 4px; }
    .replay button { font: 500 12.5px var(--sans); padding: 4px 10px; border-radius: 999px; border: 1px solid color-mix(in srgb, var(--bg) 35%, transparent); background: transparent; color: var(--bg); cursor: pointer; }
    .replay button:hover, .replay button:focus-visible { background: color-mix(in srgb, var(--bg) 16%, transparent); outline: none; }
    """
    helper = """
    (function () {
      const FX = window.__PLAYGROUND_FIXTURES__;
      const wait = async (sel, ok) => { for (let i = 0; i < 60; i++) { const el = document.querySelector(sel); if (el && (!ok || ok(el))) return el; await new Promise((r) => setTimeout(r, 50)); } return null; };
      const set = (el, v) => { if (el) { el.value = v; el.dispatchEvent(new Event("input", { bubbles: true })); } };
      document.querySelectorAll(".replay .rq").forEach((b) => b.addEventListener("click", async () => {
        const q = FX.asks["demo-vulnerable"][+b.dataset.q];
        const pick = document.querySelector("main select");
        const target = state.view === "try" && pick && pick.value !== "ticket-tools" ? pick.value : "demo-vulnerable";
        go("try", target);
        const prompt = await wait("textarea[placeholder='Ask it something']", () => document.querySelector("main select") && document.querySelector("main select").value === target);
        set(document.querySelector("textarea[placeholder^='Optional: instructions']"), q.system);
        set(document.querySelector("textarea[placeholder^='Optional: a document']"), q.context);
        set(prompt, q.prompt);
        const send = [...document.querySelectorAll("main button")].find((x) => x.textContent === "Send");
        if (send) send.click();
      }));
      document.querySelectorAll(".replay .rt").forEach((b) => b.addEventListener("click", async () => {
        const c = FX.calls["ticket-tools"][+b.dataset.t];
        go("try", "ticket-tools");
        const sel = await wait("main .card select", (el) => el.options.length > 0);
        if (!sel) return;
        sel.value = c.name;
        const args = [...document.querySelectorAll("main textarea")].pop();
        set(args, JSON.stringify(c.arguments));
        const call = [...document.querySelectorAll("main button")].find((x) => x.textContent === "Call");
        if (call) call.click();
      }));
    })();
    function download() { toast("In the playground this saves the report file; this page cannot save files."); }
    """
    page = (HEAD + "<title>AI Playground Interface</title>\n<link rel=\"icon\" href=\"data:,\">\n<style>\n" + css + extra_css + "</style>\n" + banner + "\n" + body +
            "<script>window.__PLAYGROUND_FIXTURES__ = " + json.dumps(fx).replace("</", "<\\/") + ";</script>\n"
            "<script>\n" + (HERE / "replay.js").read_text() + "\n</script>\n<script>\n" + js + "\n</script>\n<script>\n" + helper + "\n</script>\n")
    return page


if __name__ == "__main__":
    OUT.write_text(build())
    print(OUT.relative_to(PG))
