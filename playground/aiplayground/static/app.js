"use strict";
// The AI Playground's page. Everything a solution returns is untrusted text: it is only ever placed with
// textContent, never parsed as HTML.

const TOKEN_KEY = "aiplayground.token";
const state = { meta: null, probes: [], view: "home", report: null };

function token() {
  const m = location.hash.match(/token=([A-Za-z0-9_-]+)/);
  if (m) {
    try { sessionStorage.setItem(TOKEN_KEY, m[1]); } catch (e) { state.token = m[1]; }
    history.replaceState(null, "", location.pathname + "#home");
  }
  try { return sessionStorage.getItem(TOKEN_KEY) || state.token || ""; } catch (e) { return state.token || ""; }
}

function pref(key, value) {
  try {
    if (value === undefined) return localStorage.getItem("aiplayground." + key) || "";
    localStorage.setItem("aiplayground." + key, value);
  } catch (e) { /* storage blocked: the field just is not remembered */ }
  return value;
}

async function api(method, path, body) {
  const opts = { method, headers: { "X-Playground-Token": token() } };
  if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const r = await fetch("/api/" + path, opts);
  const text = await r.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (e) { data = { error: text }; }
  if (!r.ok) throw new Error((data && data.error) || ("HTTP " + r.status));
  return data;
}

async function download(path, name) {
  const r = await fetch("/api/" + path, { headers: { "X-Playground-Token": token() } });
  if (!r.ok) return toast("Download failed: HTTP " + r.status);
  const url = URL.createObjectURL(await r.blob());
  const a = h("a", { href: url, download: name });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

// h("div", {class: "card"}, "text", child, ...) : strings become text nodes, never HTML.
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (k === "value") el.value = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const chip = (text, cls) => h("span", { class: "chip " + (cls || "") }, text);
const main = () => document.getElementById("main");

function toast(text) {
  const t = document.getElementById("toast");
  t.textContent = text; t.classList.add("show");
  clearTimeout(toast.timer); toast.timer = setTimeout(() => t.classList.remove("show"), 3200);
}

function show(view, ...kids) {
  state.view = view;
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("on", a.dataset.view === view));
  main().replaceChildren(...kids.flat(Infinity).filter((k) => k !== null && k !== undefined && k !== false));
  main().focus({ preventScroll: true });
}

function errorBox(e) { return h("div", { class: "err card" }, String(e && e.message ? e.message : e)); }

// --- start -------------------------------------------------------------------------------------------------------
async function viewHome() {
  const role = pref("role") || "engineer";
  const runs = await api("GET", "runs").catch(() => []);
  const steps = role === "ai-security" ? [
    ["Read the report", "Open the latest run of the solution. The verdict says whether anything critical or high gave way."],
    ["Run everything", "Run checks with every probe, including the tool-server hardening set, against the same target."],
    ["Triage by name", "For each finding: accept the risk (with a reason that goes into Known limits), call it a false positive, or send it back."],
    ["Sign, outside the playground", "The report is evidence, not a sign-off. Sign with tools/shelf.py --sign and cite the report id in the note."],
  ] : [
    ["Describe the solution", "Add it under Solutions: an API, an MCP server, a Python function or a command. Credentials are names, never values."],
    ["Try it by hand", "Ask it questions or call its tools and look at the raw answer before running anything automated."],
    ["Run the checks", "The collection's contract on the component's directory, the probe library, and your own cases."],
    ["Fix, run again, compare", "Fix what failed, run again, and compare the two reports. Then ask the owner and an AI security engineer to sign."],
  ];
  show("home",
    h("h1", {}, "Test an AI solution before it joins the collection"),
    h("p", { class: "lede" }, "Point the playground at the solution you want to onboard. It checks the candidate against the collection's contract, puts it through prompt injection, leakage, excessive agency and robustness probes, runs your own cases, and writes a report with a verdict that the two signers read before they sign."),
    h("div", { class: "steps" }, steps.map(([t, d]) => h("div", { class: "card" }, h("h3", {}, t), h("div", { class: "muted small" }, d)))),
    h("h2", {}, "Recent reports"),
    runsTable(runs.slice(0, 6)),
    h("div", { class: "row" },
      h("button", { class: "primary", onclick: () => go("targets") }, "Add a solution"),
      h("button", { onclick: () => go("run") }, "Run checks")));
}

// --- solutions (targets) -----------------------------------------------------------------------------------------
const TEMPLATES = {
  "Demo: safe assistant": { name: "demo-safe", kind: "demo", demo: "safe", environment: "sandbox", description: "The bundled demo that holds every probe", capabilities: ["cites-sources", "masks-pii"] },
  "Demo: vulnerable assistant": { name: "demo-vulnerable", kind: "demo", demo: "vulnerable", environment: "sandbox", description: "The bundled demo that gives way", capabilities: ["cites-sources"] },
  "Chat API (OpenAI-style)": { name: "my-assistant", kind: "http", preset: "openai-chat", environment: "sandbox", url: "http://127.0.0.1:8099/v1/chat/completions",
    model: "workhorse", headers: { Authorization: "Bearer ${env:MODEL_GATEWAY_TOKEN}" }, allow_hosts: [], capabilities: [], owner: "", component: "" },
  "Messages API (Anthropic-style)": { name: "my-agent", kind: "http", preset: "anthropic-messages", environment: "sandbox", url: "https://model-gateway.example.internal/v1/messages",
    model: "workhorse", headers: { "x-api-key": "${env:MODEL_GATEWAY_KEY}" }, allow_hosts: ["model-gateway.example.internal"], capabilities: [] },
  "Simple JSON API": { name: "my-service", kind: "http", preset: "simple-json", environment: "dev", url: "http://127.0.0.1:8099/chat", capabilities: ["cites-sources"] },
  "MCP tool server (HTTP)": { name: "my-tools", kind: "mcp-http", environment: "sandbox", url: "http://127.0.0.1:8099/mcp", headers: { Authorization: "Bearer ${env:MCP_TOKEN}" } },
  "MCP tool server (stdio command)": { name: "my-stdio-tools", kind: "mcp-stdio", environment: "sandbox", command: ["python3", "server.py"], env: [] },
  "Python function": { name: "my-function", kind: "python", environment: "sandbox", path: "/path/to/component", callable: "module:answer", env: [] },
  "Command": { name: "my-command", kind: "command", environment: "sandbox", command: ["python3", "answer.py"], env: [] },
};

async function viewTargets() {
  let list = [];
  try { list = await api("GET", "targets"); } catch (e) { return show("targets", errorBox(e)); }
  const editor = h("textarea", { class: "tall", spellcheck: "false", "aria-label": "Target file (JSON)" });
  const status = h("div", { class: "err" });
  const fill = (obj) => { editor.value = JSON.stringify(obj, null, 2); status.textContent = ""; };
  fill(TEMPLATES["Demo: safe assistant"]);
  const save = async () => {
    status.textContent = "";
    let raw;
    try { raw = JSON.parse(editor.value); } catch (e) { status.textContent = "Not JSON: " + e.message; return; }
    try { const t = await api("POST", "targets", raw); toast("Saved " + t.name); viewTargets(); } catch (e) { status.textContent = e.message; }
  };
  const rows = list.map((it) => it.target ? h("tr", {},
    h("td", {}, h("b", {}, it.target.name), h("div", { class: "muted small" }, it.target.description || "")),
    h("td", {}, chip(it.target.kind), " ", chip(it.target.environment)),
    h("td", { class: "small" }, it.target.url || (it.target.command || []).join(" ") || it.target.callable || it.target.demo || ""),
    h("td", {}, h("div", { class: "row" },
      h("button", { onclick: () => go("try", it.target.name) }, "Try"),
      h("button", { onclick: () => go("run", it.target.name) }, "Run"),
      h("button", { onclick: async () => fill(await api("GET", "targets/" + it.target.name)) }, "Edit"),
      h("button", { class: "danger", onclick: async () => { if (confirm("Delete the target file " + it.target.name + "? Its reports stay.")) { await api("DELETE", "targets/" + it.target.name); viewTargets(); } } }, "Delete"))))
    : h("tr", {}, h("td", { colspan: 4, class: "err" }, it.file + ": " + it.error)));
  show("targets",
    h("h1", {}, "Solutions"),
    h("p", { class: "lede" }, "Each solution is one target file: how to reach it and nothing secret. A credential is written ${env:NAME} and read from the environment the playground runs in. Only non-production environments are accepted, and a host outside loopback must be listed in allow_hosts."),
    list.length ? h("div", { class: "card" }, h("table", {}, h("tr", {}, h("th", {}, "Solution"), h("th", {}, "Kind"), h("th", {}, "Where"), h("th", {}, "")), rows))
      : h("div", { class: "card empty" }, "No solutions yet. Start from a template below; the demo ones work straight away."),
    h("h2", {}, "Add or edit"),
    h("div", { class: "row" }, Object.keys(TEMPLATES).map((k) => h("button", { onclick: () => fill(TEMPLATES[k]) }, k))),
    h("div", { class: "card stack" }, editor, status, h("div", { class: "row" }, h("button", { class: "primary", onclick: save }, "Save"),
      h("span", { class: "muted small" }, "Fields: name, kind, environment, url or command or callable, preset, headers, body, response, model, system, env, allow_hosts, timeout_s, concurrency, capabilities (masks-pii, cites-sources), owner, component."))));
}

// --- try it --------------------------------------------------------------------------------------------------------
async function viewTry(name) {
  let list = [];
  try { list = (await api("GET", "targets")).filter((x) => x.target); } catch (e) { return show("try", errorBox(e)); }
  if (!list.length) return show("try", h("h1", {}, "Try it"), h("div", { class: "card empty" }, "Add a solution first."), h("button", { class: "primary", onclick: () => go("targets") }, "Add a solution"));
  const pick = h("select", {}, list.map((x) => h("option", { value: x.target.name, selected: x.target.name === name }, x.target.name + " (" + x.target.kind + ")")));
  const area = h("div", {});
  const render = () => {
    const t = list.find((x) => x.target.name === pick.value).target;
    area.replaceChildren(t.kind.startsWith("mcp") ? toolPane(t) : chatPane(t));
  };
  pick.addEventListener("change", render);
  show("try", h("h1", {}, "Try it by hand"),
    h("p", { class: "lede" }, "Look at what the solution really returns before you automate anything. Nothing here is recorded in a report."),
    h("div", { class: "row" }, h("label", {}, "Solution", pick)), area);
  render();
}

function replyView(r) {
  return h("div", { class: "stack" },
    h("div", { class: "row" }, r.error ? chip("error", "error") : chip("answered", "pass"), chip(r.latency_ms + " ms"), r.status !== null && r.status !== undefined ? chip("status " + r.status) : null),
    r.error ? h("div", { class: "err" }, r.error) : null,
    h("h3", {}, "Answer"), h("pre", {}, r.text || "(empty)"),
    r.tool_calls && r.tool_calls.length ? [h("h3", {}, "Tool calls"), h("pre", {}, JSON.stringify(r.tool_calls, null, 2))] : null,
    r.citations && r.citations.length ? [h("h3", {}, "Citations"), h("pre", {}, JSON.stringify(r.citations, null, 2))] : null,
    h("details", {}, h("summary", {}, "Raw response"), h("pre", {}, r.raw || "")));
}

function chatPane(t) {
  const system = h("textarea", { placeholder: "Optional: instructions added to the solution's own" });
  const context = h("textarea", { placeholder: "Optional: a document or record the solution should read (retrieved context)" });
  const prompt = h("textarea", { placeholder: "Ask it something" });
  const out = h("div", {});
  const send = h("button", { class: "primary", onclick: async () => {
    send.disabled = true; out.replaceChildren(h("div", { class: "muted" }, "Asking…"));
    try { out.replaceChildren(replyView(await api("POST", "targets/" + t.name + "/ask", { prompt: prompt.value, system: system.value, context: context.value }))); }
    catch (e) { out.replaceChildren(errorBox(e)); }
    send.disabled = false;
  } }, "Send");
  return h("div", { class: "two" },
    h("div", { class: "card stack" }, h("label", {}, "System", system), h("label", {}, "Context", context), h("label", {}, "Question", prompt), h("div", {}, send)),
    h("div", { class: "card" }, out));
}

function toolPane(t) {
  const out = h("div", {});
  const tools = h("div", { class: "stack" }, h("div", { class: "muted" }, "Listing tools…"));
  const name = h("select", {});
  const args = h("textarea", {}, "{}");
  api("POST", "targets/" + t.name + "/tools", {}).then((list) => {
    tools.replaceChildren(...list.map((x) => h("div", {}, h("b", {}, x.name), h("div", { class: "muted small" }, x.description || "(no description)"))));
    name.replaceChildren(...list.map((x) => h("option", { value: x.name }, x.name)));
  }).catch((e) => tools.replaceChildren(errorBox(e)));
  const call = h("button", { class: "primary", onclick: async () => {
    let a; try { a = JSON.parse(args.value || "{}"); } catch (e) { return out.replaceChildren(errorBox("Arguments are not JSON: " + e.message)); }
    call.disabled = true;
    try { out.replaceChildren(replyView(await api("POST", "targets/" + t.name + "/call", { name: name.value, arguments: a }))); } catch (e) { out.replaceChildren(errorBox(e)); }
    call.disabled = false;
  } }, "Call");
  return h("div", { class: "two" }, h("div", { class: "card stack" }, h("h3", {}, "Tools"), tools, h("label", {}, "Tool", name), h("label", {}, "Arguments (JSON)", args), h("div", {}, call)), h("div", { class: "card" }, out));
}

// --- run -----------------------------------------------------------------------------------------------------------
async function viewRun(name) {
  let list = [];
  try { list = (await api("GET", "targets")).filter((x) => x.target); } catch (e) { return show("run", errorBox(e)); }
  const role = pref("role") || "engineer";
  const defaults = (state.meta.defaults[role] || "").split(",");
  const pick = h("select", {}, h("option", { value: "" }, "(none: only the component's contract)"), list.map((x) => h("option", { value: x.target.name, selected: x.target.name === name }, x.target.name + " (" + x.target.kind + ")")));
  const comp = h("input", { placeholder: "/path/to/the/candidate/component (optional)", value: pref("component") });
  const runTests = h("input", { type: "checkbox", checked: true });
  const suite = h("textarea", { placeholder: '{"name": "my-cases", "cases": [{"id": "hello", "prompt": "Say hello", "expect": {"contains": ["hello"]}}]}' });
  const boxes = {};
  const groups = ["security", "robustness", "quality"].map((g) => h("div", { class: "card" },
    h("h3", {}, g === "quality" ? "Quality (for solutions that claim to cite)" : g[0].toUpperCase() + g.slice(1)),
    h("div", { class: "probe-group" }, state.probes.filter((p) => p.suite === g).map((p) => {
      boxes[p.id] = h("input", { type: "checkbox", checked: defaults.includes(g) || defaults.includes("all") });
      return h("label", { title: p.why }, boxes[p.id], h("span", {}, p.title, " ", chip(p.severity, p.severity), " ", h("span", { class: "muted small" }, p.applies === "tool" ? "tool servers" : "")));
    }))));
  const status = h("div", {});
  const start = h("button", { class: "primary", onclick: async () => {
    const body = { target: pick.value || null, component: comp.value.trim() || null, run_component: runTests.checked, role: pref("role") || "engineer", by: pref("by") || "",
      probes: Object.keys(boxes).filter((k) => boxes[k].checked), suites: [] };
    if (!body.probes.length) body.probes = "none";
    if (suite.value.trim()) { try { body.suites = [JSON.parse(suite.value)]; } catch (e) { return status.replaceChildren(errorBox("The suite is not JSON: " + e.message)); } }
    pref("component", comp.value.trim());
    start.disabled = true;
    try { const { job } = await api("POST", "runs", body); track(job, status, start); } catch (e) { status.replaceChildren(errorBox(e)); start.disabled = false; }
  } }, "Run the checks");
  show("run", h("h1", {}, "Run checks"),
    h("p", { class: "lede" }, "Choose the solution, the candidate component's directory (its contract is checked and its own tests run in a throwaway copy), the probes, and any cases of your own. The run is recorded with your name and role."),
    h("div", { class: "card stack" }, h("div", { class: "two" }, h("label", {}, "Solution", pick), h("label", {}, "Component directory", comp)),
      h("label", { class: "row" }, runTests, "Run the component's tests and live example")),
    groups,
    h("div", { class: "card stack" }, h("label", {}, "Your own cases (a suite, JSON; optional)", suite)),
    h("div", { class: "row" }, start, h("span", { class: "muted small" }, "Tester: " + (pref("by") || "set your name at the top right"))),
    status);
}

function track(job, status, button) {
  const bar = h("div", {});
  const label = h("div", { class: "muted small" }, "Starting…");
  status.replaceChildren(h("div", { class: "card stack" }, h("div", { class: "progress" }, bar), label));
  const tick = async () => {
    let j;
    try { j = await api("GET", "jobs/" + job); } catch (e) { status.replaceChildren(errorBox(e)); button.disabled = false; return; }
    bar.style.width = j.total ? Math.round((100 * j.done) / j.total) + "%" : "5%";
    label.textContent = j.done + " of " + (j.total || "?") + " · " + (j.label || "");
    if (j.state === "running") return setTimeout(tick, 600);
    button.disabled = false;
    if (j.state === "failed") return status.replaceChildren(errorBox("The run failed: " + j.error));
    go("report", j.report_id);
  };
  tick();
}

// --- reports -------------------------------------------------------------------------------------------------------
function runsTable(runs, selectable) {
  if (!runs.length) return h("div", { class: "card empty" }, "No reports yet.");
  const picked = new Set();
  // the older run is "before", whichever was ticked first; the table is newest first, so a tie keeps its order
  const when = new Map(runs.map((r, i) => [r.id, [r.started, -i]]));
  const inOrder = () => [...picked].sort((a, b) => {
    const [sa, ia] = when.get(a), [sb, ib] = when.get(b);
    return sa < sb ? -1 : sa > sb ? 1 : ia - ib;
  });
  const compare = h("button", { disabled: true, onclick: () => viewCompare(inOrder()) }, "Compare the two selected");
  const rows = runs.map((r) => h("tr", { class: "click", onclick: (ev) => { if (ev.target.tagName !== "INPUT") go("report", r.id); } },
    selectable ? h("td", {}, h("input", { type: "checkbox", "aria-label": "Select " + r.id, onchange: (ev) => {
      ev.target.checked ? picked.add(r.id) : picked.delete(r.id);
      compare.disabled = picked.size !== 2;
    } })) : null,
    h("td", {}, chip(r.verdict, r.verdict)),
    h("td", {}, h("b", {}, r.target || "—"), r.component ? h("div", { class: "muted small" }, "component " + r.component) : null),
    h("td", { class: "small" }, ["fail", "review", "error", "pass"].filter((k) => r.counts[k]).map((k) => [chip(k + " " + r.counts[k], k), " "])),
    h("td", { class: "small muted" }, (r.by || "unnamed") + " · " + r.role),
    h("td", { class: "small muted" }, r.started.replace("T", " ").replace("Z", ""))));
  return h("div", { class: "card" }, h("table", {}, h("tr", {}, selectable ? h("th", {}, "") : null, h("th", {}, "Verdict"), h("th", {}, "Solution"), h("th", {}, "Results"), h("th", {}, "By"), h("th", {}, "When")), rows),
    selectable ? h("div", { class: "row" }, compare) : null);
}

async function viewRuns() {
  try { show("runs", h("h1", {}, "Reports"), h("p", { class: "lede" }, "Every run, newest first. Select two runs of the same solution to see what changed."), runsTable(await api("GET", "runs"), true)); }
  catch (e) { show("runs", errorBox(e)); }
}

// ids: [before, after], the older run first
async function viewCompare(ids) {
  try {
    const c = await api("GET", "compare?a=" + encodeURIComponent(ids[0]) + "&b=" + encodeURIComponent(ids[1]));
    show("runs", h("h1", {}, "What changed"),
      h("p", { class: "lede" }, c.before.id + " (" + c.before.verdict + ") → " + c.after.id + " (" + c.after.verdict + ")"),
      c.changes.length ? h("div", { class: "card" }, h("table", {}, h("tr", {}, h("th", {}, "Check"), h("th", {}, "Before"), h("th", {}, "After"), h("th", {}, "")),
        c.changes.map((x) => h("tr", {}, h("td", {}, h("code", {}, x.id)), h("td", {}, chip(x.before, x.before)), h("td", {}, chip(x.after, x.after)), h("td", {}, x.change)))))
        : h("div", { class: "card empty" }, "No result changed."),
      h("button", { onclick: () => go("runs") }, "Back to reports"));
  } catch (e) { show("runs", errorBox(e)); }
}

async function viewReport(id) {
  let rep;
  try { rep = await api("GET", "runs/" + id); } catch (e) { return show("runs", errorBox(e)); }
  state.report = rep;
  const s = rep.summary;
  const tri = {};
  (rep.triage || []).forEach((t) => { if (t.decision === "fixed-retest") delete tri[t.result_id]; else tri[t.result_id] = t; });
  const findings = rep.results.filter((r) => ["fail", "review", "error"].includes(r.status));
  const held = rep.results.filter((r) => r.status === "pass");
  const skipped = rep.results.filter((r) => r.status === "skipped");
  const ob = rep.onboarding;
  show("runs",
    h("div", { class: "row" }, h("button", { class: "link", onclick: () => go("runs") }, "← Reports")),
    h("h1", {}, "Report ", h("code", {}, rep.id)),
    h("div", { class: "muted small" }, (rep.target ? "Solution " + rep.target.name + " (" + rep.target.kind + ", " + rep.target.environment + ")" : "") +
      (rep.component ? (rep.target ? " · " : "") + "component " + rep.component.name + " " + (rep.component.version || "") : "") + " · " + (rep.tester.by || "unnamed") + " as " + rep.tester.role + " · " + rep.started),
    h("div", { class: "card verdict" }, chip(rep.verdict, rep.verdict), h("span", {}, rep.verdict_reason)),
    h("div", { class: "stats" }, Object.entries(s.by_status).map(([k, v]) => h("div", {}, h("b", {}, v), h("span", { class: "muted small" }, k))),
      s.latency && s.latency.answers ? h("div", {}, h("b", {}, s.latency.p95_ms + " ms"), h("span", { class: "muted small" }, "p95 latency")) : null),
    h("h2", {}, "For the sign-off"),
    h("div", { class: "card" }, h("p", { class: "muted small" }, ob.note), h("table", {},
      [["Tests green", ob.tests_green], ["Live example ran", ob.live_example_ran], ["Collection contract", ob.contract], ["Held under attack", ob.held_under_attack], ["Cite as", ob.cite_as]]
        .map(([k, v]) => h("tr", {}, h("td", {}, k), h("td", {}, v))),
      ob.known_limits_to_add.map((k) => h("tr", {}, h("td", {}, "Known limit to add"), h("td", {}, k))))),
    h("div", { class: "row" },
      h("button", { onclick: () => download("runs/" + rep.id + "/report.html", rep.id + ".html") }, "Download HTML"),
      h("button", { onclick: () => download("runs/" + rep.id + "/report.md", rep.id + ".md") }, "Download Markdown"),
      h("button", { onclick: () => download("runs/" + rep.id + "/report.json", rep.id + ".json") }, "Download JSON")),
    h("h2", {}, "Findings (" + findings.length + ")"),
    findings.length ? findings.map((r) => findingCard(r, tri[r.id], rep)) : h("div", { class: "card empty" }, "Nothing needs a person."),
    h("h2", {}, "Held (" + held.length + ")"), held.map((r) => findingCard(r, null, rep)),
    skipped.length ? [h("h2", {}, "Not applicable (" + skipped.length + ")"), h("div", { class: "card small" }, skipped.map((r) => h("div", {}, h("code", {}, r.id), " ", h("span", { class: "muted" }, r.summary))))] : null,
    (rep.triage || []).length ? [h("h2", {}, "Triage log"), h("div", { class: "card" }, h("table", {}, h("tr", {}, h("th", {}, "Finding"), h("th", {}, "Decision"), h("th", {}, "By"), h("th", {}, "Reason"), h("th", {}, "When")),
      rep.triage.map((t) => h("tr", {}, h("td", {}, h("code", {}, t.result_id)), h("td", {}, t.decision), h("td", {}, t.by), h("td", {}, t.reason), h("td", { class: "small muted" }, t.at)))))] : null);
}

function evidenceView(ev) {
  if (ev && ev.reply) {
    const r = ev.reply;
    return h("pre", {}, "asked: " + ev.prompt + (ev.context ? "\ncontext: " + ev.context : "") + (ev.system ? "\nsystem: " + ev.system : "") +
      "\nanswer: " + (r.text || "") + (r.error ? "\nerror: " + r.error : "") + (r.tool_calls && r.tool_calls.length ? "\ntool calls: " + JSON.stringify(r.tool_calls) : "") + "\n" + r.latency_ms + " ms");
  }
  return h("pre", {}, JSON.stringify(ev, null, 2));
}

function findingCard(r, t, rep) {
  const card = h("div", { class: "card finding " + r.status },
    h("div", { class: "row" }, chip(r.status, r.status), chip(r.severity, r.severity), chip(r.category + " " + r.category_name), h("b", {}, r.title), h("code", { class: "muted small" }, r.id)),
    h("p", {}, r.summary),
    r.status !== "pass" && r.recommendation ? h("p", { class: "muted small" }, "What to do: " + r.recommendation) : null,
    t ? h("div", { class: "tri" }, "Triaged ", h("b", {}, t.decision), " by " + t.by + ": " + t.reason) : null,
    r.evidence && r.evidence.length ? h("details", {}, h("summary", {}, "Evidence"), r.evidence.slice(0, 3).map(evidenceView)) : null,
    r.metrics && Object.keys(r.metrics).length ? h("div", { class: "muted small" }, Object.entries(r.metrics).map(([k, v]) => k + " " + v).join(" · ")) : null);
  if (["fail", "review", "error"].includes(r.status)) {
    const decision = h("select", {}, state.meta.decisions.map((d) => h("option", { value: d }, d)));
    const reason = h("input", { placeholder: "Why, in a sentence (goes into the report; an accepted risk also into the README's Known limits)" });
    const err = h("div", { class: "err" });
    card.append(h("details", {}, h("summary", {}, "Triage this finding"), h("div", { class: "stack" },
      h("div", { class: "two" }, h("label", {}, "Decision", decision), h("label", {}, "Reason", reason)), err,
      h("div", {}, h("button", { onclick: async () => {
        err.textContent = "";
        try { await api("POST", "runs/" + rep.id + "/triage", { result_id: r.id, decision: decision.value, by: pref("by"), reason: reason.value }); toast("Recorded"); viewReport(rep.id); }
        catch (e) { err.textContent = e.message; }
      } }, "Record, as " + (pref("by") || "(set your name at the top right)"))))));
  }
  return card;
}

// --- probe library -------------------------------------------------------------------------------------------------
function viewProbes() {
  show("probes", h("h1", {}, "Probe library"),
    h("p", { class: "lede" }, "What the playground tries. Each probe plants something unique (a marker, a canary, a fake card number) and judges the answer by looking for it; where only a person can judge, the result is review. Categories follow the OWASP Top 10 for LLM applications."),
    h("div", { class: "card" }, h("table", {}, h("tr", {}, h("th", {}, "Probe"), h("th", {}, "Category"), h("th", {}, "Severity"), h("th", {}, "Why it matters"), h("th", {}, "What to do if it fails")),
      state.probes.map((p) => h("tr", {}, h("td", {}, h("b", {}, p.title), h("div", {}, h("code", { class: "muted small" }, p.id)), h("div", { class: "muted small" }, p.applies === "tool" ? "tool servers" : "question answering" + (p.needs ? ", when " + p.needs + " is claimed" : ""))),
        h("td", { class: "small" }, p.category + " " + p.category_name), h("td", {}, chip(p.severity, p.severity)), h("td", { class: "small" }, p.why), h("td", { class: "small muted" }, p.recommendation))))));
}

// --- routing -------------------------------------------------------------------------------------------------------
function go(view, arg) {
  const hash = "#" + view + (arg ? "/" + encodeURIComponent(arg) : "");
  if (location.hash !== hash) history.pushState(null, "", hash);
  route();
}

function route() {
  const [view, arg] = (location.hash.replace(/^#/, "") || "home").split("/");
  const a = arg ? decodeURIComponent(arg) : undefined;
  const views = { home: viewHome, targets: viewTargets, try: () => viewTry(a), run: () => viewRun(a), runs: viewRuns, report: () => viewReport(a), probes: viewProbes };
  Promise.resolve((views[view] || viewHome)()).catch((e) => show(view, errorBox(e)));
}

async function boot() {
  token();
  const role = document.getElementById("role");
  const by = document.getElementById("by");
  role.value = pref("role") || "engineer";
  by.value = pref("by");
  role.addEventListener("change", () => { pref("role", role.value); route(); });
  by.addEventListener("change", () => pref("by", by.value.trim()));
  window.addEventListener("popstate", route);
  document.querySelectorAll("#nav a").forEach((a) => a.addEventListener("click", (ev) => { ev.preventDefault(); go(a.dataset.view); }));
  try {
    state.meta = await api("GET", "meta");
    state.probes = await api("GET", "probes");
  } catch (e) {
    main().replaceChildren(h("h1", {}, "AI Playground"), errorBox(e.message + " — open the link the playground printed in the terminal; it carries the access token."));
    return;
  }
  document.getElementById("ver").textContent = state.meta.version;
  route();
}

boot();
