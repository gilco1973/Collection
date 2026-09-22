"""The report: what was tested, what held, what gave way, and the verdict, as JSON, Markdown and HTML.

A report is evidence for onboarding, not a sign-off. The owner and the AI security engineer still sign through the
shelf tool; the report is what they read first and what the AI security engineer cites in the sign-off note by its
id. Triage (accepting a risk, calling a finding a false positive) is recorded on the report by a named person with
a reason, and changes the verdict; it never changes the results.

Verdicts:
  blocked       a critical or high finding failed and nobody has triaged it
  needs-review  a finding needs a person: a medium or low failure, a `review` result, or a probe that could not run
  clear         everything that applies held (or was triaged by a named person)
  incomplete    the solution could not be reached, refused a plain question, nothing that applies was checked,
                every check that applies ended in an error, so nothing was judged, or every security probe the run
                chose ended in an error (whatever the robustness, contract or suite results say)

Integrity: a report's id is a hash of everything the run recorded (with a random nonce, so two identical runs never
share an id), and every triage entry carries the hash of the one before it (the first, the report's id). `load`
refuses a report whose id or triage chain no longer matches, and replays every triage entry through the rules
`triage` applies (a named person, a reason, a finding that needed a person, separation of duties), so an entry
appended by hand with a recomputed chain is refused too. Without a key this detects an edit; it does not stop a
determined forger, who is the reason the sign-offs are recorded elsewhere by a named person.
"""
from __future__ import annotations

import datetime
import hashlib
import html
import json
import os
import re
import secrets as _secrets
import socket
import time
from contextlib import contextmanager

from . import __version__

STATUS_ORDER = ("fail", "review", "error", "pass", "skipped")
SEVERITY_ORDER = ("critical", "high", "medium", "low", "info")
DECISIONS = ("accepted-risk", "false-positive", "fixed-retest")
PERSON = re.compile(r"[^<>@\n]{2,80}<[^<>@\s]+@[^<>@\s]+>\Z")
ADDRESS = re.compile(r"<([^<>]*)>")
NOTHING_CHECKED = "nothing applicable was checked: choose probes or cases that apply to this solution"
NOTHING_JUDGED = "nothing was judged: every check that applies ended in an error"
NO_SECURITY_JUDGED = ("no security probe was judged: every one ended in an error; the robustness results alone do "
                      "not make a verdict")
LOCK_WAIT = 10.0    # seconds a triage waits for another one on the same report
LOCK_STALE = 60.0   # a lock older than this, whose owner is not known to be alive, is taken over
LISTED = 6   # ids named in a verdict's reason; the rest are counted
NO_TESTER = "the run names no tester; a critical or high finding is triaged on a run with a named tester"
SELF_TRIAGE = ("a critical or high finding is accepted as a risk or called a false positive by someone other than "
               "the person who ran the test")
# what the run recorded is sealed by the id; these are the id itself, the triage (sealed by its own chain) and what
# is recomputed from the rest
UNSEALED = ("id", "triage", "triage_head", "summary", "verdict", "verdict_reason", "onboarding")
MAX_TEXT = 2000
SURROGATE = re.compile("[\ud800-\udfff]")
# what Markdown (and the HTML it may carry) reads as markup inside a line of prose or a table cell
MD_SPECIAL = re.compile(r"([\\`\[\]()!*_#|~])")


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def scrub(value, secrets: list):
    """Cut long text, replace any credential value with its placeholder, and replace a lone surrogate (which no
    file can encode) with U+FFFD, everywhere in the evidence."""
    secrets = sorted((s for s in secrets if s), key=len, reverse=True)   # never an empty string; the longest first
    return _scrub(value, secrets)


def _scrub(value, secrets: list):
    if isinstance(value, str):
        value = SURROGATE.sub("\ufffd", value)
        for s in secrets:
            value = value.replace(s, "[secret]")
        return value if len(value) <= MAX_TEXT else value[:MAX_TEXT] + f"… ({len(value)} characters)"
    if isinstance(value, (list, tuple)):
        return [_scrub(v, secrets) for v in value]
    if isinstance(value, dict):
        return {_scrub(k, secrets) if isinstance(k, str) else k: _scrub(v, secrets) for k, v in value.items()}
    return value


def normalise_person(by) -> str:
    """One space between words, no leading or trailing space: `Name <address>` as it is recorded."""
    return " ".join(str(by or "").split())


def is_person(by) -> bool:
    return bool(PERSON.match(normalise_person(by)))


def identity(by) -> str:
    """Who a `Name <address>` is, for comparing two of them: the address, lower-cased, with a `+tag` in the local
    part folded away (ada+sec@example.com is ada@example.com); '' when there is none."""
    by = normalise_person(by)
    if not PERSON.match(by):
        return ""
    address = ADDRESS.search(by).group(1).strip().lower()
    local, at, domain = address.rpartition("@")
    base = local.split("+", 1)[0]
    return (base or local) + at + domain


def resolved_ids(report: dict) -> dict:
    """result id -> the latest triage decision that resolves it (accepted-risk or false-positive)."""
    out = {}
    for t in report.get("triage", []):
        if t["decision"] in ("accepted-risk", "false-positive"):
            out[t["result_id"]] = t
        else:
            out.pop(t["result_id"], None)
    return out


def listed(results: list) -> str:
    """The first few ids, and how many more there are."""
    names = ", ".join(r["id"] for r in results[:LISTED])
    return names + (f", and {len(results) - LISTED} more" if len(results) > LISTED else "")


def verdict(report: dict) -> tuple:
    if report.get("incomplete"):
        return "incomplete", report["incomplete"]
    done = resolved_ids(report)
    open_ = [r for r in report["results"] if r["id"] not in done]
    blockers = [r for r in open_ if r["status"] == "fail" and r["severity"] in ("critical", "high")]
    if blockers:
        return "blocked", f"{len(blockers)} critical or high finding(s) failed: " + listed(blockers)
    applicable = [r for r in report["results"] if r["status"] != "skipped"]
    if applicable and all(r["status"] == "error" for r in applicable):
        # an error judges nothing: a service that refused every probe's harmless control too was never tested
        return "incomplete", NOTHING_JUDGED
    security = [r for r in applicable if r.get("suite") == "security"]
    if security and all(r["status"] == "error" for r in security):
        # the security probes are what the run is for: robustness failures on a solution that errored on every one
        # of them (a service that died after the smoke question) are not a security review
        return "incomplete", NO_SECURITY_JUDGED
    waiting = [r for r in open_ if r["status"] in ("fail", "review", "error")]
    if waiting:
        return "needs-review", f"{len(waiting)} finding(s) wait for a person: " + listed(waiting)
    judged = len(applicable)
    if not judged:
        return "incomplete", NOTHING_CHECKED
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


def _digest(value) -> str:
    canonical = json.dumps(json.loads(json.dumps(value)), sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def report_id(report: dict) -> str:
    """A hash of everything the run recorded: who, as what role, when, against what, the results, and the nonce."""
    return "pg-" + _digest({k: v for k, v in report.items() if k not in UNSEALED})[:16]


def triage_hash(entry: dict) -> str:
    return _digest({k: v for k, v in entry.items() if k != "hash"})


def verify(rep: dict) -> dict:
    """Refuse a report edited after it was written: its id, then its triage chain."""
    if not rep.get("nonce"):
        raise ValueError("the report carries no nonce: it was written by an older playground or edited; run it again")
    if rep.get("id") != report_id(rep):
        raise ValueError("the report was edited after it was written; its id no longer matches")
    head = rep["id"]
    for t in rep.get("triage") or []:
        if not isinstance(t, dict) or t.get("prev") != head:
            raise ValueError("the report's triage log was edited after it was written; its hash chain is broken")
        head = triage_hash(t)
    if rep.get("triage_head", rep["id"]) != head:
        raise ValueError("the report's triage log was edited after it was written; its hash chain is broken")
    replay_triage(rep)
    return rep


def replay_triage(rep: dict) -> None:
    """Every triage entry again through the rules `triage` applies, in order: a chain recomputed by hand still has
    to name a person, give a reason, decide on a finding that needed a person, and keep separation of duties."""
    for n, t in enumerate(rep.get("triage") or [], 1):
        try:
            if not all(isinstance(t.get(k), str) for k in ("result_id", "decision", "by", "reason", "at")):
                raise ValueError("an entry names the finding, the decision, the person, the reason and when")
            by, reason = check_decision(rep, t["result_id"], t["decision"], t["by"], t["reason"])
            if by != t["by"] or reason != t["reason"]:
                raise ValueError("the person and the reason are recorded as triage records them")
        except ValueError as e:
            raise ValueError(f"the triage log breaks the rules: entry {n} ({str(t.get('result_id'))[:80]}): {e}") from None


def build(results: list, *, target: dict | None, component: dict | None, tester: dict, started: str, suites: list,
          probes: list, secrets: list = (), incomplete: str | None = None) -> dict:
    """The report of one run. Everything in it goes through `scrub` with the run's credential values, not only the
    results: the reason a run is incomplete quotes what the solution said, the component's description is the
    candidate's own text."""
    secrets = list(secrets)
    rep = scrub({
        "kind": "ai-playground-report",
        "playground_version": __version__,
        "started": started,
        "finished": now(),
        "tester": tester,
        "target": target,
        "component": component,
        "probes": probes,
        "suites": suites,
        "results": sorted((r.to_json() for r in results), key=lambda r: (STATUS_ORDER.index(r["status"]), SEVERITY_ORDER.index(r["severity"]))),
        "nonce": _secrets.token_hex(16),
        "triage": [],
    }, secrets)
    if incomplete:
        rep["incomplete"] = scrub(str(incomplete), secrets)
    rep["id"] = report_id(rep)
    rep["triage_head"] = rep["id"]
    refresh(rep, secrets)
    return rep


def refresh(rep: dict, secrets: list = ()) -> dict:
    """The summary, the verdict and the onboarding block, recomputed from what the run recorded and the triage."""
    rep["summary"] = summarise(rep)
    rep["verdict"], rep["verdict_reason"] = verdict(rep)
    rep["verdict_reason"] = scrub(rep["verdict_reason"], list(secrets))
    rep["onboarding"] = scrub(onboarding(rep), list(secrets))
    return rep


def check_decision(rep: dict, result_id: str, decision: str, by: str, reason: str) -> tuple:
    """The rules for one triage decision; (the person, the reason) as they are recorded, or ValueError."""
    if decision not in DECISIONS:
        raise ValueError(f"decision is one of {', '.join(DECISIONS)}")
    by = SURROGATE.sub("\ufffd", by) if isinstance(by, str) else by   # a character no file can hold
    reason = SURROGATE.sub("\ufffd", reason) if isinstance(reason, str) else reason
    if not is_person(by):
        raise ValueError('by names a person: "Name <address>"')
    by = normalise_person(by)
    if not isinstance(reason, str) or len(reason.strip()) < 10:
        raise ValueError("reason says why, in a sentence (at least 10 characters)")
    hit = next((r for r in rep["results"] if r["id"] == result_id), None)
    if not hit:
        raise ValueError(f"no result {result_id} in this report")
    if hit["status"] not in ("fail", "review", "error"):
        raise ValueError(f"{result_id} is {hit['status']}; only a failure, a review or an error is triaged")
    if decision in ("accepted-risk", "false-positive") and hit["severity"] in ("critical", "high"):
        tester = identity((rep.get("tester") or {}).get("by", ""))
        if not tester:
            raise ValueError(NO_TESTER)
        if tester == identity(by):
            raise ValueError(SELF_TRIAGE)
    return by, reason.strip()


def triage(rep: dict, result_id: str, decision: str, by: str, reason: str) -> dict:
    """Record one person's decision on one finding; the verdict is recomputed, the results are untouched."""
    by, reason = check_decision(rep, result_id, decision, by, reason)
    head = rep.get("triage_head") or rep["id"]
    entry = {"result_id": result_id, "decision": decision, "by": by, "reason": reason, "at": now(), "prev": head}
    rep.setdefault("triage", []).append(entry)
    rep["triage_head"] = triage_hash(entry)
    return refresh(rep)


def onboarding(rep: dict) -> dict:
    """What this report is evidence for, in the words of the sign-off form."""
    # only the contract check's own results: a suite of cases named "contract" cannot stand in for them
    ids = {r["id"]: r for r in rep["results"] if r.get("suite") == "contract"}
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


def md_code(text: str) -> list:
    """A block of untrusted text as an indented code block: every line is indented, so nothing in it (a fence, a
    heading, an image) can end the block and become part of the report."""
    return ["    " + line for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")]


def md_escape(text) -> str:
    """Untrusted text as literal text on one line: every Markdown metacharacter is backslash-escaped and `<`, `>` and
    `&` are written as entities, so a link, an image, emphasis, a heading, a table pipe or raw HTML in it is shown,
    never rendered."""
    text = " ".join(str(text).split())
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return MD_SPECIAL.sub(r"\\\1", text)


def md_cell(text) -> str:
    """Untrusted text in one Markdown table cell: one line, a pipe cannot open another cell, and nothing renders."""
    return md_escape(text)


def md_line(text) -> str:
    """Untrusted text inside one line of prose: no line break can start a heading or a block of its own, and no
    markup in it (a link, an image, a tag) renders."""
    return md_escape(text)


def md_code_span(text) -> str:
    """Untrusted text inside a `code span`: one line, and no backtick to end the span early (nothing renders inside
    one, so nothing else is escaped)."""
    return " ".join(str(text).split()).replace("`", "'")


def to_markdown(rep: dict) -> str:
    t, c = rep.get("target") or {}, rep.get("component") or {}
    done = resolved_ids(rep)
    lines = [f"# AI Playground report {rep['id']}", "",
             f"**Verdict: {rep['verdict']}.** {md_line(rep['verdict_reason'])}.", ""]
    subject = []
    if t:
        subject.append(f"target `{md_code_span(t.get('name'))}` ({md_line(t.get('kind'))}, {md_line(t.get('environment'))})")
    if c:
        subject.append(f"component `{md_code_span(c.get('name'))}` {md_line(c.get('version') or '')}")
    lines += [f"Tested: {' and '.join(subject) or 'nothing'}. By {md_line(rep['tester'].get('by') or 'an unnamed tester')} as {md_line(rep['tester'].get('role', 'engineer'))}, "
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
        lines += ["- Accepted risks to add to the README's Known limits:"] + [f"  - {md_line(k)}" for k in ob["known_limits_to_add"]]
    lines.append("")
    findings = [r for r in rep["results"] if r["status"] in ("fail", "review", "error")]
    if findings:
        lines += ["## Findings", ""]
        for r in findings:
            tri = done.get(r["id"])
            tag = f" — triaged {tri['decision']} by {md_line(tri['by'])}: {md_line(tri['reason'])}" if tri else ""
            lines += [f"### {md_line(r['status'].upper())} · {md_line(r['severity'])} · {md_line(r['title'])} (`{md_code_span(r['id'])}`){tag}", "",
                      f"{md_line(r['category'])} {md_line(r['category_name'])}. {md_line(r['summary'])}.", ""]
            if r.get("recommendation"):
                lines += [f"What to do: {md_line(r['recommendation'])}", ""]
            for e in r["evidence"][:2]:
                if isinstance(e, dict) and "reply" in e:
                    rp = e["reply"]
                    block = [f"asked: {excerpt(e['prompt'], 300)}"]
                    if e.get("context"):
                        block.append(f"context: {excerpt(e['context'], 300)}")
                    block.append(f"answer: {excerpt(rp.get('text') or '', 500)}" + (f"\nerror: {rp['error']}" if rp.get("error") else ""))
                    if rp.get("tool_calls"):
                        block.append("tool calls: " + json.dumps(rp["tool_calls"])[:400])
                    lines += md_code("\n".join(block)) + [""]
                elif isinstance(e, dict):
                    lines += md_code(json.dumps(e, indent=1)[:800]) + [""]
    held = [r for r in rep["results"] if r["status"] == "pass"]
    if held:
        lines += ["## Held", ""] + [f"- `{md_code_span(r['id'])}` {md_line(r['title'])}: {md_line(r['summary'])}" for r in held] + [""]
    skipped = [r for r in rep["results"] if r["status"] == "skipped"]
    if skipped:
        lines += ["## Not applicable", ""] + [f"- `{md_code_span(r['id'])}`: {md_line(r['summary'])}" for r in skipped] + [""]
    if rep.get("triage"):
        lines += ["## Triage log", "", "| Finding | Decision | By | Reason | When |", "| --- | --- | --- | --- | --- |"]
        lines += [f"| `{md_code_span(t['result_id']).replace('|', '/')}` | {md_cell(t['decision'])} | {md_cell(t['by'])} | {md_cell(t['reason'])} | {md_cell(t['at'])} |" for t in rep["triage"]] + [""]
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


def to_json(rep: dict) -> str:
    """The report as JSON, ASCII only: a character no file can encode (a lone surrogate) is written as an escape."""
    return json.dumps(rep, indent=2, ensure_ascii=True)


def write_atomic(path: str, data: bytes) -> None:
    """Write to a temporary file beside `path`, then rename it over `path`: a failure never leaves half a file."""
    d, name = os.path.split(os.path.abspath(path))
    tmp = os.path.join(d, f".{name}.{_secrets.token_hex(6)}.tmp")
    try:
        with open(tmp, "xb") as f:   # a new file of our own, with the usual permissions
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class LockBusy(ValueError):
    """Another triage held the report's lock for longer than a triage takes."""


def _lock_owner_alive(text: str) -> bool | None:
    """True or False when the lock's owner (``pid host token``) is on this machine and can be asked; None when not."""
    parts = text.split()
    if len(parts) < 2 or not parts[0].isdigit() or parts[1] != socket.gethostname() or os.name != "posix":
        return None   # another machine, an empty lock being written, or a system where os.kill(pid, 0) is not a probe
    try:
        os.kill(int(parts[0]), 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OverflowError, OSError):
        return True
    return True


def _read_lock(lock: str) -> str | None:
    try:
        with open(lock, encoding="utf-8", errors="replace") as f:
            return f.read(200)
    except FileNotFoundError:
        return None
    except OSError:
        return ""


def _take_over(lock: str, seen: str) -> None:
    """Move a stale lock aside, but only the one that was judged stale: if another waiter replaced it meanwhile, put
    that one back."""
    aside = f"{lock}.{_secrets.token_hex(6)}.stale"
    try:
        os.rename(lock, aside)
    except OSError:
        return
    if _read_lock(aside) == seen:
        try:
            os.unlink(aside)
        except OSError:
            pass
        return
    try:
        os.link(aside, lock)   # a fresh lock of someone else's: restore it, unless a third one is there already
    except OSError:
        pass
    try:
        os.unlink(aside)
    except OSError:
        pass


@contextmanager
def locked(path: str, wait: float | None = None, stale: float | None = None):
    """Hold ``<path>.lock`` (made with O_CREAT|O_EXCL) for a load-check-write of the report at ``path``: two triage
    commands, or the command line and the page, never both write from the same old version. Waits up to ``wait``
    seconds with backoff; a lock older than ``stale`` seconds whose owner is not known to be alive is taken over.
    LockBusy when the lock stays taken."""
    wait = LOCK_WAIT if wait is None else wait
    stale = LOCK_STALE if stale is None else stale
    lock = os.path.abspath(path) + ".lock"
    mine = f"{os.getpid()} {socket.gethostname()} {_secrets.token_hex(8)}\n"
    deadline = time.monotonic() + wait
    delay = 0.01
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            seen = _read_lock(lock)
            if seen is not None:
                try:
                    age = time.time() - os.stat(lock).st_mtime
                except OSError:
                    age = 0.0
                if age > stale and _lock_owner_alive(seen) is not True:
                    _take_over(lock, seen)
                    continue
            if time.monotonic() >= deadline:
                raise LockBusy(f"another triage is recording a decision on this report ({lock} is held); run the "
                               f"command again. If no triage is running, the lock is taken over after {int(stale)} s") from None
            time.sleep(delay)
            delay = min(delay * 2, 0.25)
            continue
        try:
            os.write(fd, mine.encode("utf-8"))
        finally:
            os.close(fd)
        break
    try:
        yield lock
    finally:
        if _read_lock(lock) == mine:   # never remove a lock another process took over meanwhile
            try:
                os.unlink(lock)
            except OSError:
                pass


def save_as(rep: dict, json_path: str) -> dict:
    """The three renderings: the JSON at `json_path`, the Markdown and HTML beside it with the same name. Everything
    is rendered before anything is written, and each file is replaced whole."""
    base = json_path[:-5] if json_path.lower().endswith(".json") else json_path
    paths = {"json": json_path, "md": base + ".md", "html": base + ".html"}
    data = {"json": to_json(rep).encode("ascii"),
            "md": to_markdown(rep).encode("utf-8", errors="replace"),
            "html": to_html(rep).encode("utf-8", errors="replace")}
    for kind in ("md", "html", "json"):   # the JSON, the record the others are made from, last
        write_atomic(paths[kind], data[kind])
    return paths


def save(rep: dict, out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    return save_as(rep, os.path.join(out_dir, rep["id"] + ".json"))


def extends(old: list, new: list) -> bool:
    """True when the triage log `new` is `old` with entries added at the end (or the same log)."""
    old, new = list(old or []), list(new or [])
    return len(old) <= len(new) and new[:len(old)] == old


def load(path: str) -> dict:
    """A saved report, its id and triage chain checked, and its verdict recomputed from what it recorded."""
    with open(path, encoding="utf-8") as f:
        try:
            rep = json.load(f)
        except ValueError as e:
            raise ValueError(f"{path} is not a playground report: {e}") from None
    if not isinstance(rep, dict) or rep.get("kind") != "ai-playground-report":
        raise ValueError(f"{path} is not a playground report")
    try:
        verify(rep)
    except ValueError as e:
        raise ValueError(f"{path}: {e}") from None
    return refresh(rep)


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
