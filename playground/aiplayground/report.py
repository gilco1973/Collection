"""The report: what was tested, what held, what gave way, and the verdict, as JSON, Markdown and HTML.

A report is evidence for onboarding, not a sign-off. The owner and the AI security engineer still sign through the
shelf tool; the report is what they read first and what the AI security engineer cites in the sign-off note by its
id. Triage (accepting a risk, calling a finding a false positive) is recorded on the report by a named person with
a reason, and changes the verdict; it never changes the results.

Verdicts:
  blocked       a critical or high finding failed and nobody has triaged it
  needs-review  a finding needs a person: a medium or low failure, a `review` result, or a probe that could not run
  clear         everything that applies held (or was triaged by a named person)
  incomplete    the solution could not be reached, so nothing was judged
"""
from __future__ import annotations

import datetime
import hashlib
import html
import json
import os
import re

from . import __version__

STATUS_ORDER = ("fail", "review", "error", "pass", "skipped")
SEVERITY_ORDER = ("critical", "high", "medium", "low", "info")
DECISIONS = ("accepted-risk", "false-positive", "fixed-retest")
PERSON = re.compile(r"^[^<>@\n]{2,80}<[^<>@\s]+@[^<>@\s]+>$")
MAX_TEXT = 2000


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def scrub(value, secrets: list):
    """Cut long text and replace any credential value with its placeholder, everywhere in the evidence."""
    if isinstance(value, str):
        for s in secrets:
            value = value.replace(s, "[secret]")
        return value if len(value) <= MAX_TEXT else value[:MAX_TEXT] + f"… ({len(value)} characters)"
    if isinstance(value, list):
        return [scrub(v, secrets) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v, secrets) for k, v in value.items()}
    return value


def resolved_ids(report: dict) -> dict:
    """result id -> the latest triage decision that resolves it (accepted-risk or false-positive)."""
    out = {}
    for t in report.get("triage", []):
        if t["decision"] in ("accepted-risk", "false-positive"):
            out[t["result_id"]] = t
        else:
            out.pop(t["result_id"], None)
    return out


def verdict(report: dict) -> tuple:
    if report.get("incomplete"):
        return "incomplete", report["incomplete"]
    done = resolved_ids(report)
    open_ = [r for r in report["results"] if r["id"] not in done]
    blockers = [r for r in open_ if r["status"] == "fail" and r["severity"] in ("critical", "high")]
    if blockers:
        return "blocked", f"{len(blockers)} critical or high finding(s) failed: " + ", ".join(r["id"] for r in blockers[:6])
    waiting = [r for r in open_ if r["status"] in ("fail", "review", "error")]
    if waiting:
        return "needs-review", f"{len(waiting)} finding(s) wait for a person: " + ", ".join(r["id"] for r in waiting[:6])
    judged = sum(1 for r in report["results"] if r["status"] != "skipped")
    return "clear", f"all {judged} applicable checks held" + (f"; {len(done)} triaged by a named person" if done else "")


def summarise(report: dict) -> dict:
    by_status = {s: 0 for s in STATUS_ORDER}
    by_sev = {s: 0 for s in SEVERITY_ORDER}
    for r in report["results"]:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        if r["status"] == "fail":
            by_sev[r["severity"]] = by_sev.get(r["severity"], 0) + 1
    lat = sorted(a["reply"]["latency_ms"] for r in report["results"] for a in r["evidence"] if isinstance(a, dict) and "reply" in a and not a["reply"].get("error"))
    latency = {"answers": len(lat), "p50_ms": lat[len(lat) // 2], "p95_ms": lat[max(0, int(len(lat) * 0.95) - 1)], "max_ms": lat[-1]} if lat else {}
    return {"by_status": by_status, "failed_by_severity": by_sev, "latency": latency}


def report_id(report: dict) -> str:
    core = {k: report[k] for k in ("started", "target", "component", "results")}
    return "pg-" + hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()[:16]


def build(results: list, *, target: dict | None, component: dict | None, tester: dict, started: str, suites: list,
          probes: list, secrets: list = (), incomplete: str | None = None) -> dict:
    rep = {
        "kind": "ai-playground-report",
        "playground_version": __version__,
        "started": started,
        "finished": now(),
        "tester": tester,
        "target": target,
        "component": component,
        "probes": probes,
        "suites": suites,
        "results": scrub(sorted((r.to_json() for r in results), key=lambda r: (STATUS_ORDER.index(r["status"]), SEVERITY_ORDER.index(r["severity"]))), list(secrets)),
        "triage": [],
    }
    if incomplete:
        rep["incomplete"] = incomplete
    rep["id"] = report_id(rep)
    refresh(rep)
    return rep


def refresh(rep: dict) -> dict:
    rep["summary"] = summarise(rep)
    rep["verdict"], rep["verdict_reason"] = verdict(rep)
    rep["onboarding"] = onboarding(rep)
    return rep


def triage(rep: dict, result_id: str, decision: str, by: str, reason: str) -> dict:
    """Record one person's decision on one finding; the verdict is recomputed, the results are untouched."""
    if decision not in DECISIONS:
        raise ValueError(f"decision is one of {', '.join(DECISIONS)}")
    if not PERSON.match(by or ""):
        raise ValueError('by names a person: "Name <address>"')
    if not reason or len(reason.strip()) < 10:
        raise ValueError("reason says why, in a sentence (at least 10 characters)")
    hit = next((r for r in rep["results"] if r["id"] == result_id), None)
    if not hit:
        raise ValueError(f"no result {result_id} in this report")
    if hit["status"] not in ("fail", "review", "error"):
        raise ValueError(f"{result_id} is {hit['status']}; only a failure, a review or an error is triaged")
    tester = (rep.get("tester") or {}).get("by", "")
    if decision == "accepted-risk" and hit["severity"] in ("critical", "high") and tester and tester == by:
        raise ValueError("a critical or high risk is accepted by someone other than the person who ran the test")
    rep["triage"].append({"result_id": result_id, "decision": decision, "by": by, "reason": reason.strip(), "at": now()})
    return refresh(rep)


def onboarding(rep: dict) -> dict:
    """What this report is evidence for, in the words of the sign-off form."""
    ids = {r["id"]: r for r in rep["results"]}
    def state(i):
        return ids[i]["status"] if i in ids else "not run"
    security = [r for r in rep["results"] if r["suite"] in ("security", "robustness")]
    accepted = [t for t in rep.get("triage", []) if t["decision"] == "accepted-risk"]
    return {
        "is_a_signoff": False,
        "note": "Evidence for the two sign-offs, not a sign-off. Sign with tools/shelf.py --sign; cite this report's id in the note.",
        "tests_green": state("contract/tests"),
        "live_example_ran": state("contract/example"),
        "contract": "pass" if all(r["status"] in ("pass", "skipped") for r in rep["results"] if r["suite"] == "contract") and any(r["suite"] == "contract" for r in rep["results"]) else ("not run" if not any(r["suite"] == "contract" for r in rep["results"]) else "findings"),
        "held_under_attack": f"{sum(1 for r in security if r['status'] == 'pass')} of {sum(1 for r in security if r['status'] != 'skipped')} probes held" if security else "not run",
        "known_limits_to_add": [f"{t['result_id']}: {t['reason']}" for t in accepted],
        "cite_as": f"AI Playground report {rep['id']} ({rep['verdict']}, {rep['finished'][:10]})",
    }


# --- renderings --------------------------------------------------------------------------------------------------

def excerpt(text: str, n: int = 400) -> str:
    text = text or ""
    return text if len(text) <= n else text[:n] + "…"


def to_markdown(rep: dict) -> str:
    t, c = rep.get("target") or {}, rep.get("component") or {}
    done = resolved_ids(rep)
    lines = [f"# AI Playground report {rep['id']}", "",
             f"**Verdict: {rep['verdict']}.** {rep['verdict_reason']}.", ""]
    subject = []
    if t:
        subject.append(f"target `{t.get('name')}` ({t.get('kind')}, {t.get('environment')})")
    if c:
        subject.append(f"component `{c.get('name')}` {c.get('version') or ''}")
    lines += [f"Tested: {' and '.join(subject) or 'nothing'}. By {rep['tester'].get('by') or 'an unnamed tester'} as {rep['tester'].get('role', 'engineer')}, "
              f"{rep['started']} to {rep['finished']}, playground {rep['playground_version']}.", ""]
    s = rep["summary"]
    lines += ["| Status | Count |", "| --- | --- |"] + [f"| {k} | {v} |" for k, v in s["by_status"].items() if v] + [""]
    if s.get("latency"):
        L = s["latency"]
        lines += [f"Latency over {L['answers']} answers: p50 {L['p50_ms']} ms, p95 {L['p95_ms']} ms, max {L['max_ms']} ms.", ""]
    ob = rep["onboarding"]
    lines += ["## For the sign-off", "", ob["note"], "",
              f"- Tests green: {ob['tests_green']}", f"- Live example ran: {ob['live_example_ran']}", f"- Collection contract: {ob['contract']}",
              f"- Held under attack: {ob['held_under_attack']}", f"- Cite as: {ob['cite_as']}"]
    if ob["known_limits_to_add"]:
        lines += ["- Accepted risks to add to the README's Known limits:"] + [f"  - {k}" for k in ob["known_limits_to_add"]]
    lines.append("")
    findings = [r for r in rep["results"] if r["status"] in ("fail", "review", "error")]
    if findings:
        lines += ["## Findings", ""]
        for r in findings:
            tri = done.get(r["id"])
            tag = f" — triaged {tri['decision']} by {tri['by']}: {tri['reason']}" if tri else ""
            lines += [f"### {r['status'].upper()} · {r['severity']} · {r['title']} (`{r['id']}`){tag}", "",
                      f"{r['category']} {r['category_name']}. {r['summary']}.", ""]
            if r.get("recommendation"):
                lines += [f"What to do: {r['recommendation']}", ""]
            for e in r["evidence"][:2]:
                if isinstance(e, dict) and "reply" in e:
                    rp = e["reply"]
                    lines += ["```text", f"asked: {excerpt(e['prompt'], 300)}"]
                    if e.get("context"):
                        lines.append(f"context: {excerpt(e['context'], 300)}")
                    lines.append(f"answer: {excerpt(rp.get('text') or '', 500)}" + (f"\nerror: {rp['error']}" if rp.get("error") else ""))
                    if rp.get("tool_calls"):
                        lines.append("tool calls: " + json.dumps(rp["tool_calls"])[:400])
                    lines += ["```", ""]
                elif isinstance(e, dict):
                    lines += ["```json", json.dumps(e, indent=1)[:800], "```", ""]
    held = [r for r in rep["results"] if r["status"] == "pass"]
    if held:
        lines += ["## Held", ""] + [f"- `{r['id']}` {r['title']}: {r['summary']}" for r in held] + [""]
    skipped = [r for r in rep["results"] if r["status"] == "skipped"]
    if skipped:
        lines += ["## Not applicable", ""] + [f"- `{r['id']}`: {r['summary']}" for r in skipped] + [""]
    if rep.get("triage"):
        lines += ["## Triage log", "", "| Finding | Decision | By | Reason | When |", "| --- | --- | --- | --- | --- |"]
        lines += [f"| `{t['result_id']}` | {t['decision']} | {t['by']} | {t['reason']} | {t['at']} |" for t in rep["triage"]] + [""]
    return "\n".join(lines)


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#101828;--ink2:#475467;--rule:#e4e7ec;--ok:#067647;--okb:#ecfdf3;--warn:#b54708;--warnb:#fffaeb;--bad:#b42318;--badb:#fef3f2;--acc:#2757a8;--accb:#eef4ff;--mono:ui-monospace,Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root{--bg:#0f1419;--card:#171c22;--ink:#e7ecf2;--ink2:#a3adba;--rule:#2a333e;--ok:#63c58c;--okb:#14301f;--warn:#e4a44a;--warnb:#3a2a12;--bad:#f0776c;--badb:#3d1d1a;--acc:#8fb0ee;--accb:#1d2b44}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1000px;margin:0 auto;padding:28px 16px 80px}h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:28px 0 10px}
.muted{color:var(--ink2)}.card{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:14px 16px;margin:10px 0}
.v{display:inline-block;padding:3px 12px;border-radius:999px;font-weight:600}.v.clear,.s-pass{background:var(--okb);color:var(--ok)}.v.blocked,.s-fail{background:var(--badb);color:var(--bad)}
.v.needs-review,.v.incomplete,.s-review,.s-error{background:var(--warnb);color:var(--warn)}.s-skipped{background:var(--rule);color:var(--ink2)}
.chip{display:inline-block;font:600 11.5px var(--mono);padding:1px 8px;border-radius:999px;margin-right:6px}
.sev{border:1px solid var(--rule);color:var(--ink2)}.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px}
.stats div{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:10px}.stats b{display:block;font-size:22px}
pre{white-space:pre-wrap;word-break:break-word;background:var(--bg);border:1px solid var(--rule);border-radius:8px;padding:8px 10px;font:12.5px/1.45 var(--mono);margin:6px 0}
details summary{cursor:pointer;color:var(--acc)}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:6px 8px;border-bottom:1px solid var(--rule);vertical-align:top;font-size:14px}
.tri{background:var(--accb);border-radius:8px;padding:6px 10px;margin-top:6px;font-size:14px}code{font-family:var(--mono);font-size:13px}
"""


def to_html(rep: dict) -> str:
    e = html.escape
    t, c = rep.get("target") or {}, rep.get("component") or {}
    done = resolved_ids(rep)
    s = rep["summary"]
    parts = [f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>",
             f"<title>Playground report {e(rep['id'])}</title><style>{CSS}</style></head><body><main>",
             f"<h1>AI Playground report</h1><div class=muted><code>{e(rep['id'])}</code> · {e(rep['started'])} → {e(rep['finished'])} · "
             f"{e(rep['tester'].get('by') or 'unnamed tester')} ({e(rep['tester'].get('role', 'engineer'))})</div>",
             f"<p><span class='v {e(rep['verdict'])}'>{e(rep['verdict'])}</span> {e(rep['verdict_reason'])}</p>"]
    subject = []
    if t:
        subject.append(f"Target <b>{e(t.get('name', ''))}</b> ({e(t.get('kind', ''))}, {e(t.get('environment', ''))}){' — ' + e(t['description']) if t.get('description') else ''}")
    if c:
        subject.append(f"Component <b>{e(c.get('name') or '')}</b> {e(c.get('version') or '')} ({e(c.get('category') or '')})")
    parts.append("<div class=card>" + "<br>".join(subject) + "</div>")
    parts.append("<div class=stats>" + "".join(f"<div><b>{v}</b><span class=muted>{e(k)}</span></div>" for k, v in s["by_status"].items()) +
                 (f"<div><b>{s['latency']['p95_ms']} ms</b><span class=muted>p95 latency</span></div>" if s.get("latency") else "") + "</div>")
    ob = rep["onboarding"]
    parts.append("<h2>For the sign-off</h2><div class=card><p class=muted>" + e(ob["note"]) + "</p><table>"
                 + "".join(f"<tr><td>{e(k)}</td><td>{e(str(v))}</td></tr>" for k, v in (("Tests green", ob["tests_green"]), ("Live example ran", ob["live_example_ran"]),
                                                                                        ("Collection contract", ob["contract"]), ("Held under attack", ob["held_under_attack"]), ("Cite as", ob["cite_as"])))
                 + "".join(f"<tr><td>Known limit to add</td><td>{e(k)}</td></tr>" for k in ob["known_limits_to_add"]) + "</table></div>")
    for title, keep in (("Findings", ("fail", "review", "error")), ("Held", ("pass",)), ("Not applicable", ("skipped",))):
        rows = [r for r in rep["results"] if r["status"] in keep]
        if not rows:
            continue
        parts.append(f"<h2>{title} ({len(rows)})</h2>")
        for r in rows:
            tri = done.get(r["id"])
            parts.append(f"<div class=card id='{e(r['id'])}'><span class='chip s-{e(r['status'])}'>{e(r['status'])}</span><span class='chip sev'>{e(r['severity'])}</span>"
                         f"<span class='chip sev'>{e(r['category'])} {e(r['category_name'])}</span><b>{e(r['title'])}</b> <code class=muted>{e(r['id'])}</code>"
                         f"<p>{e(r['summary'])}</p>")
            if r["status"] != "pass" and r.get("recommendation"):
                parts.append(f"<p class=muted>What to do: {e(r['recommendation'])}</p>")
            if tri:
                parts.append(f"<div class=tri>Triaged <b>{e(tri['decision'])}</b> by {e(tri['by'])}: {e(tri['reason'])} <span class=muted>({e(tri['at'])})</span></div>")
            if r["evidence"] and r["status"] != "skipped":
                parts.append("<details><summary>Evidence</summary>")
                for ev in r["evidence"][:3]:
                    if isinstance(ev, dict) and "reply" in ev:
                        rp = ev["reply"]
                        parts.append("<pre>" + e(f"asked: {excerpt(ev['prompt'], 600)}") + (e(f"\ncontext: {excerpt(ev['context'], 600)}") if ev.get("context") else "")
                                     + e(f"\nanswer: {excerpt(rp.get('text') or '', 1200)}") + (e(f"\nerror: {rp['error']}") if rp.get("error") else "")
                                     + (e("\ntool calls: " + json.dumps(rp["tool_calls"])[:600]) if rp.get("tool_calls") else "")
                                     + e(f"\n{rp.get('latency_ms', 0)} ms") + "</pre>")
                    else:
                        parts.append("<pre>" + e(json.dumps(ev, indent=1)[:1500]) + "</pre>")
                parts.append("</details>")
            if r.get("metrics"):
                parts.append("<div class=muted style='font-size:13px'>" + e(", ".join(f"{k} {v}" for k, v in r["metrics"].items())) + "</div>")
            parts.append("</div>")
    if rep.get("triage"):
        parts.append("<h2>Triage log</h2><div class=card><table><tr><th>Finding</th><th>Decision</th><th>By</th><th>Reason</th><th>When</th></tr>"
                     + "".join(f"<tr><td><code>{e(x['result_id'])}</code></td><td>{e(x['decision'])}</td><td>{e(x['by'])}</td><td>{e(x['reason'])}</td><td>{e(x['at'])}</td></tr>" for x in rep["triage"])
                     + "</table></div>")
    parts.append("</main></body></html>")
    return "".join(parts)


def save(rep: dict, out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, rep["id"])
    paths = {"json": base + ".json", "md": base + ".md", "html": base + ".html"}
    with open(paths["json"], "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2, ensure_ascii=False)
    with open(paths["md"], "w", encoding="utf-8") as f:
        f.write(to_markdown(rep))
    with open(paths["html"], "w", encoding="utf-8") as f:
        f.write(to_html(rep))
    return paths


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        rep = json.load(f)
    if rep.get("kind") != "ai-playground-report":
        raise ValueError(f"{path} is not a playground report")
    return rep


def compare(a: dict, b: dict) -> list:
    """Per result id: what changed between two reports of the same solution (a before, b after)."""
    ra, rb = {r["id"]: r for r in a["results"]}, {r["id"]: r for r in b["results"]}
    rows = []
    for rid in sorted(set(ra) | set(rb)):
        sa, sb = ra.get(rid, {}).get("status", "absent"), rb.get(rid, {}).get("status", "absent")
        if sa != sb:
            rank = {"fail": 0, "error": 1, "review": 2, "pass": 3}
            if sa in rank and sb in rank:
                change = "better" if rank[sb] > rank[sa] else "worse"
            else:
                change = "new" if sa == "absent" else "gone" if sb == "absent" else "changed"
            rows.append({"id": rid, "before": sa, "after": sb, "change": change})
    return rows
