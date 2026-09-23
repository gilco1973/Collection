"use strict";
// Replays the playground's API from responses recorded on a real playground server, so the real page runs unchanged.
// Four sample solutions and four real reports are loaded; Try it answers the recorded questions; Run checks replays
// the recorded results for the probes you tick; triage follows the real rules.
(function () {
  const FX = window.__PLAYGROUND_FIXTURES__;
  const S = {
    targets: JSON.parse(JSON.stringify(FX.raw_targets)),
    described: Object.fromEntries(FX.targets.filter((t) => t.target).map((t) => [t.target.name, t.target])),
    reports: JSON.parse(JSON.stringify(FX.reports)),
    jobs: {},
  };
  const BASE_FOR = { "demo-vulnerable": FX.ids.vuln, "demo-safe": FX.ids.safe, "runbook-answerer": FX.ids.runbook, "ticket-tools": FX.ids.tools };
  const NAME = /^[a-z0-9][a-z0-9._-]{0,63}$/;
  const PERSON = /^[^<>@\n]{2,80}<[^<>@\s]+@[^<>@\s]+>$/;
  const STATUS_ORDER = ["fail", "review", "error", "pass", "skipped"];
  const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"];
  const LISTED = 6;
  const NOTE = "This page replays answers recorded from a real playground. Use one of the recorded questions in the bar above; the playground itself sends anything you type.";

  // ---- the report's rules, as report.py has them ------------------------------------------------------------
  const listed = (rs) => rs.slice(0, LISTED).map((r) => r.id).join(", ") + (rs.length > LISTED ? `, and ${rs.length - LISTED} more` : "");
  function resolved(rep) {
    const out = {};
    for (const t of rep.triage || []) {
      if (t.decision === "accepted-risk" || t.decision === "false-positive") out[t.result_id] = t;
      else delete out[t.result_id];
    }
    return out;
  }
  function verdict(rep) {
    if (rep.incomplete) return ["incomplete", rep.incomplete];
    const done = resolved(rep);
    const open = rep.results.filter((r) => !done[r.id]);
    const blockers = open.filter((r) => r.status === "fail" && (r.severity === "critical" || r.severity === "high"));
    if (blockers.length) return ["blocked", `${blockers.length} critical or high finding(s) failed: ` + listed(blockers)];
    const applicable = rep.results.filter((r) => r.status !== "skipped");
    if (applicable.length && applicable.every((r) => r.status === "error")) return ["incomplete", "nothing was judged: every check that applies ended in an error"];
    const security = applicable.filter((r) => r.suite === "security");
    if (security.length && security.every((r) => r.status === "error")) return ["incomplete", "no security probe was judged: every one ended in an error; the robustness results alone do not make a verdict"];
    const waiting = open.filter((r) => ["fail", "review", "error"].includes(r.status));
    if (waiting.length) return ["needs-review", `${waiting.length} finding(s) wait for a person: ` + listed(waiting)];
    if (!applicable.length) return ["incomplete", "nothing applicable was checked: choose probes or cases that apply to this solution"];
    const n = Object.keys(done).length;
    return ["clear", `all ${applicable.length} applicable checks held` + (n ? `; ${n} triaged by a named person` : "")];
  }
  function refresh(rep) {
    const by = Object.fromEntries(STATUS_ORDER.map((s) => [s, 0]));
    rep.results.forEach((r) => { by[r.status] = (by[r.status] || 0) + 1; });
    const lat = rep.results.flatMap((r) => (r.evidence || []).filter((a) => a && a.reply && !a.reply.error).map((a) => a.reply.latency_ms)).sort((a, b) => a - b);
    rep.summary = { by_status: by, latency: lat.length ? { answers: lat.length, p50_ms: lat[lat.length >> 1], p95_ms: lat[Math.max(0, Math.floor(lat.length * 0.95) - 1)], max_ms: lat[lat.length - 1] } : {} };
    [rep.verdict, rep.verdict_reason] = verdict(rep);
    const contract = rep.results.filter((r) => r.suite === "contract");
    const state = (id) => (contract.find((r) => r.id === id) || {}).status || "not run";
    const sec = rep.results.filter((r) => r.suite === "security" || r.suite === "robustness");
    rep.onboarding = {
      is_a_signoff: false,
      note: "Evidence for the two sign-offs, not a sign-off. Sign with tools/shelf.py --sign; cite this report's id in the note.",
      tests_green: state("contract/tests"), live_example_ran: state("contract/example"),
      contract: !contract.length ? "not run" : contract.every((r) => r.status === "pass" || r.status === "skipped") ? "pass" : "findings",
      held_under_attack: sec.length ? `${sec.filter((r) => r.status === "pass").length} of ${sec.filter((r) => r.status !== "skipped").length} probes held` : "not run",
      known_limits_to_add: (rep.triage || []).filter((t) => t.decision === "accepted-risk").map((t) => `${t.result_id}: ${t.reason}`),
      cite_as: `AI Playground report ${rep.id} (${rep.verdict}, ${(rep.finished || rep.started).slice(0, 10)})`,
    };
    return rep;
  }
  const norm = (by) => String(by || "").split(/\s+/).join(" ").trim();
  function identity(by) {
    by = norm(by);
    if (!PERSON.test(by)) return "";
    const addr = by.match(/<([^<>]*)>/)[1].trim().toLowerCase();
    const at = addr.lastIndexOf("@");
    const local = addr.slice(0, at).split("+")[0];
    return local + addr.slice(at);
  }
  function triage(rep, id, decision, by, reason) {
    if (!["accepted-risk", "false-positive", "fixed-retest"].includes(decision)) throw new Error("decision is one of accepted-risk, false-positive, fixed-retest");
    if (!PERSON.test(norm(by))) throw new Error('by names a person: "Name <address>"');
    if (!reason || reason.trim().length < 10) throw new Error("reason says why, in a sentence (at least 10 characters)");
    const hit = rep.results.find((r) => r.id === id);
    if (!hit) throw new Error(`no result ${id} in this report`);
    if (!["fail", "review", "error"].includes(hit.status)) throw new Error(`${id} is ${hit.status}; only a failure, a review or an error is triaged`);
    if ((hit.severity === "critical" || hit.severity === "high") && decision !== "fixed-retest") {
      const tester = identity(rep.tester && rep.tester.by);
      if (!tester) throw new Error("the run names no tester; a critical or high finding is triaged on a run with a named tester");
      if (tester === identity(by)) throw new Error("a critical or high finding is accepted as a risk or called a false positive by someone other than the person who ran the test");
    }
    rep.triage = (rep.triage || []).concat([{ result_id: id, decision, by: norm(by), reason: reason.trim(), at: new Date().toISOString().replace(/\.\d+Z$/, "Z") }]);
    return refresh(rep);
  }
  function compare(a, b) {
    const ra = Object.fromEntries(a.results.map((r) => [r.id, r])), rb = Object.fromEntries(b.results.map((r) => [r.id, r]));
    const rank = { fail: 0, error: 1, review: 2, pass: 3 };
    return [...new Set([...Object.keys(ra), ...Object.keys(rb)])].sort().flatMap((id) => {
      const sa = (ra[id] || {}).status || "absent", sb = (rb[id] || {}).status || "absent";
      if (sa === sb) return [];
      const change = sa in rank && sb in rank ? (rank[sb] > rank[sa] ? "better" : "worse") : sa === "absent" ? "new" : sb === "absent" ? "gone" : "changed";
      return [{ id, before: sa, after: sb, change }];
    });
  }

  // ---- a run: the recorded results for what was chosen ------------------------------------------------------
  const hex = (n) => Array.from(crypto.getRandomValues(new Uint8Array(n)), (b) => b.toString(16).padStart(2, "0")).join("");
  const now = () => new Date().toISOString().replace(/\.\d+Z$/, "Z");
  function synthesise(body) {
    const baseId = body.target ? BASE_FOR[body.target] : body.component ? FX.ids.runbook : null;
    const started = now();
    const probeIds = body.probes === "none" ? [] : Array.isArray(body.probes) ? body.probes : null;
    const suiteNames = (body.suites || []).map((s) => s && s.name).filter(Boolean);
    let rep;
    if (!baseId) {
      rep = { results: [], incomplete: "this page replays recorded runs of the four sample solutions; the playground itself runs any solution you describe" };
    } else {
      const base = S.reports[baseId] && FX.reports[baseId];
      const recordedComponent = base.results.some((r) => r.suite === "contract");
      const results = base.results.filter((r) => {
        if (r.suite === "contract") return !!body.component && recordedComponent;
        if (base.suites && base.suites.includes(r.suite)) return suiteNames.includes(r.suite);
        return body.target && (probeIds ? probeIds.includes(r.id) : true);
      });
      if (body.component && !recordedComponent) {
        results.unshift({ id: "contract/manifest", title: "A complete manifest", category: "CONTRACT", category_name: "Collection contract", severity: "high", status: "skipped",
          summary: "this page has a recorded contract check for examples/runbook-answerer only (run it with the runbook-answerer solution)", suite: "contract", evidence: [], recommendation: "", metrics: {} });
      }
      rep = { results: JSON.parse(JSON.stringify(results)), target: base.target, component: body.component && recordedComponent ? base.component : null };
    }
    rep = Object.assign(rep, {
      kind: "ai-playground-report", playground_version: FX.meta.version, id: "pg-" + hex(8), started, finished: now(),
      tester: { by: norm(body.by || ""), role: body.role || "engineer" }, probes: probeIds || [], suites: suiteNames, triage: [],
    });
    if (!rep.target && body.target) rep.target = S.described[body.target] || { name: body.target };
    rep.results.sort((a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) || SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity));
    return refresh(rep);
  }

  // ---- the routes -------------------------------------------------------------------------------------------
  const reply = (status, data, headers) => new Response(data === undefined ? "" : JSON.stringify(data), { status, headers: Object.assign({ "Content-Type": "application/json" }, headers || {}) });
  const problem = (status, error) => reply(status, { error });
  const runRow = (r) => ({ id: r.id, started: r.started, target: (r.target || {}).name || null, component: (r.component || {}).name || null, verdict: r.verdict, by: r.tester.by, role: r.tester.role, counts: r.summary.by_status });
  const recordedAsk = (name, b) => ((FX.asks[name] || []).find((q) => q.prompt === String(b.prompt || "").trim() && q.system === String(b.system || "").trim() && q.context === String(b.context || "").trim()) || {}).reply;
  const noteReply = () => ({ text: "", tool_calls: [], citations: [], status: null, error: NOTE, latency_ms: 0, usage: {}, raw: "" });
  const delay = (ms) => new Promise((r) => setTimeout(r, ms));

  async function route(method, path, body) {
    const [p, query] = path.split("?");
    const parts = p.split("/").filter(Boolean);
    if (method === "GET" && p === "meta") return reply(200, FX.meta);
    if (method === "GET" && p === "probes") return reply(200, FX.probes);
    if (parts[0] === "targets" && parts.length === 1) {
      if (method === "GET") return reply(200, Object.keys(S.targets).sort().map((n) => ({ file: n + ".json", target: S.described[n], error: null })));
      if (method === "POST") {
        const t = body || {};
        if (!NAME.test(t.name || "")) return problem(422, "`name` is lower case letters, digits, dot, dash or underscore, at most 64");
        if (!["http", "command", "python", "mcp-stdio", "mcp-http", "demo"].includes(t.kind)) return problem(422, "`kind` is one of http, command, python, mcp-stdio, mcp-http, demo");
        if (!["sandbox", "dev", "test", "staging"].includes(t.environment)) return problem(422, "`environment` is one of sandbox, dev, test, staging; the playground never probes production");
        S.targets[t.name] = t;
        S.described[t.name] = Object.assign({ capabilities: [], secrets: [] }, t);
        return reply(201, S.described[t.name]);
      }
    }
    if (parts[0] === "targets" && parts.length === 2) {
      if (!S.targets[parts[1]]) return problem(404, "not found: no target named " + parts[1]);
      if (method === "GET") return reply(200, S.targets[parts[1]]);
      if (method === "DELETE") { delete S.targets[parts[1]]; delete S.described[parts[1]]; return reply(200, { deleted: true }); }
    }
    if (parts[0] === "targets" && parts.length === 3 && method === "POST") {
      const name = parts[1], t = S.targets[name];
      if (!t) return problem(404, "not found: no target named " + name);
      const tools = t.kind === "mcp-stdio" || t.kind === "mcp-http";
      await delay(250);
      if (parts[2] === "ask") return reply(200, tools ? Object.assign(noteReply(), { error: `a ${t.kind} target is not asked questions` }) : recordedAsk(name, body) || noteReply());
      if (parts[2] === "tools") return tools ? reply(200, FX.tools[name] || []) : problem(422, `${name} answers questions; it lists no tools`);
      if (parts[2] === "call") {
        if (!tools) return problem(422, `${name} answers questions; it has no tools to call`);
        const hit = (FX.calls[name] || []).find((c) => c.name === body.name && JSON.stringify(c.arguments) === JSON.stringify(body.arguments));
        return reply(200, hit ? hit.reply : noteReply());
      }
    }
    if (p === "runs" && method === "GET") return reply(200, Object.values(S.reports).sort((a, b) => (a.started < b.started ? 1 : -1)).map(runRow));
    if (p === "runs" && method === "POST") {
      const b = body || {};
      if (!b.target && !b.component) return problem(422, "name a target, a component directory, or both");
      if (b.by && !PERSON.test(norm(b.by))) return problem(422, 'the tester is "Name <address>"');
      const rep = synthesise(b);
      const jid = hex(6);
      S.jobs[jid] = { id: jid, state: "running", done: 0, total: rep.results.length || 1, label: "starting", report_id: null, error: null };
      const labels = rep.results.map((r) => r.id);
      let i = 0;
      const tick = () => {
        const j = S.jobs[jid];
        i = Math.min(j.total, i + Math.max(1, Math.ceil(j.total / 14)));
        Object.assign(j, { done: i, label: labels[i - 1] || "done" });
        if (i >= j.total) { S.reports[rep.id] = rep; Object.assign(j, { state: "done", report_id: rep.id }); } else setTimeout(tick, 160);
      };
      setTimeout(tick, 200);
      return reply(202, { job: jid });
    }
    if (parts[0] === "jobs" && parts.length === 2) return S.jobs[parts[1]] ? reply(200, S.jobs[parts[1]]) : problem(404, "no such job");
    if (parts[0] === "runs" && parts.length >= 2) {
      const rep = S.reports[parts[1]];
      if (!rep) return problem(404, "no such run");
      if (parts.length === 2 && method === "GET") return reply(200, rep);
      if (parts[2] === "triage" && method === "POST") {
        try { return reply(200, triage(rep, body.result_id, body.decision, body.by, body.reason)); } catch (e) { return problem(422, e.message); }
      }
    }
    if (p === "compare" && method === "GET") {
      const q = new URLSearchParams(query || "");
      const a = S.reports[q.get("a")], b = S.reports[q.get("b")];
      if (!a || !b) return problem(404, "name two runs: ?a=<id>&b=<id>");
      return reply(200, { before: { id: a.id, verdict: a.verdict }, after: { id: b.id, verdict: b.verdict }, changes: compare(a, b) });
    }
    return problem(404, "no such route");
  }

  const realFetch = window.fetch.bind(window);
  window.fetch = async function (input, init) {
    const url = typeof input === "string" ? input : input.url;
    const m = url.match(/^\/api\/(.*)$/);
    if (!m) return realFetch(input, init);
    const method = ((init && init.method) || "GET").toUpperCase();
    let body;
    try { body = init && init.body ? JSON.parse(init.body) : undefined; } catch (e) { return problem(422, "the body is a JSON object"); }
    return route(method, m[1], body);
  };
  try { if (!localStorage.getItem("aiplayground.by")) localStorage.setItem("aiplayground.by", "Sam Placeholder <sam@example.com>"); } catch (e) { /* storage blocked */ }
})();
