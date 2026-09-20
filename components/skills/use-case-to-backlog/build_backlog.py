#!/usr/bin/env python3
"""From one plan (epics, tickets, phases, owners as data) to a backlog people and Jira can both read:
one Markdown file per epic and per ticket, a README index with totals, a by-phase table, the critical path,
and a CSV for Jira's importer.

    python3 build_backlog.py example_plan.py out/          # writes out/README.md, out/<KEY>-<slug>.md, out/jira-import.csv

A plan module defines PROJECT, LABEL, TITLE, COMPANION, FOOT, PHASES, OWNERS, EPICS and TICKETS (see
example_plan.py). Keys are placeholders until the Jira project exists; dependencies use the same placeholders.
"""
from __future__ import annotations
import csv, importlib.util, os, re, sys


def slug(text: str, n: int = 60) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:n].rstrip("-")


def load_plan(path: str):
    spec = importlib.util.spec_from_file_location("plan", path); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def by_epic(tickets, key): return [t for t in tickets if t["epic"] == key]
def by_phase(tickets, n): return [t for t in tickets if t["phase"] == n]
def points(ts): return sum(t["points"] for t in ts)


def ticket_file(t, plan, files):
    epic = next(e for e in plan.EPICS if e[0] == t["epic"])
    ph = plan.PHASES[t["phase"]]
    deps = ", ".join(f"[{d}]({files[d]})" for d in t["deps"]) or "none"
    blocks = ", ".join(f"[{o['key']}]({files[o['key']]})" for o in plan.TICKETS if t["key"] in o["deps"]) or "none"
    ac = "\n".join(f"- [ ] {a}" for a in t["ac"])
    refs = ", ".join(t["refs"])
    return f"""# {t['key']} · {t['summary']}

| Field | Value |
| --- | --- |
| Type | {t['type']} |
| Epic | [{epic[0]}]({files[epic[0]]}) · {epic[1]} |
| Phase | {t['phase']} · {ph[0]} ({ph[1]}) |
| Weeks | {t['weeks']} |
| Owner | {plan.OWNERS[t['owner']]} |
| Story points | {t['points']} |
| Priority | {t['prio']} |
| Depends on | {deps} |
| Blocks | {blocks} |
| Labels | {plan.LABEL}, phase-{t['phase']}, {t['epic'].lower()} |

## Description

{t['desc']}

## Acceptance criteria

{ac}

## References

{refs}

---
{plan.FOOT}
"""


def epic_file(e, plan, files):
    key, name, phase, owner, desc = e
    ts = by_epic(plan.TICKETS, key)
    rows = "\n".join(f"| [{t['key']}]({files[t['key']]}) | {t['phase']} | {t['weeks']} | {t['type']} | {plan.OWNERS[t['owner']]} | {t['points']} | {t['prio']} | {t['summary']} |" for t in ts)
    return f"""# {key} · {name}

| Field | Value |
| --- | --- |
| Type | Epic |
| Owner | {plan.OWNERS[owner]} |
| Starts in phase | {phase} · {plan.PHASES[phase][0]} |
| Tickets | {len(ts)} |
| Story points | {points(ts)} |
| Labels | {plan.LABEL}, epic |

## Description

{desc}

## Tickets

| Key | Phase | Weeks | Type | Owner | Points | Priority | Summary |
| --- | --- | --- | --- | --- | --- | --- | --- |
{rows}

---
{plan.FOOT}
"""


def critical_path(plan) -> str:
    """The longest dependency chain by points, as KEY (summary) → KEY (summary)."""
    tickets = {t["key"]: t for t in plan.TICKETS}
    best: dict[str, tuple[int, list]] = {}
    def walk(k):
        if k in best: return best[k]
        t = tickets[k]; deps = [d for d in t["deps"] if d in tickets]
        if not deps: best[k] = (t["points"], [k]); return best[k]
        p, chain = max((walk(d) for d in deps), key=lambda x: x[0])
        best[k] = (p + t["points"], chain + [k]); return best[k]
    if not tickets: return ""
    _, chain = max((walk(k) for k in tickets), key=lambda x: x[0])
    return " → ".join(f"{k} ({tickets[k]['summary'].split(':')[0][:40]})" for k in chain)


def readme(plan, files):
    ts = plan.TICKETS
    phases = "\n".join(f"| {n} | {name} | {weeks} | {len(by_phase(ts, n))} | {points(by_phase(ts, n))} |" for n, (name, weeks, _) in plan.PHASES.items())
    epics = "\n".join(f"| [{e[0]}]({files[e[0]]}) | {e[1]} | {plan.OWNERS[e[3]]} | {len(by_epic(ts, e[0]))} | {points(by_epic(ts, e[0]))} |" for e in plan.EPICS)
    ordered = sorted(ts, key=lambda t: (t["phase"], t["weeks"], t["key"]))
    rows = "\n".join(f"| [{t['key']}]({files[t['key']]}) | {t['epic']} | {t['phase']} | {t['weeks']} | {t['type']} | {plan.OWNERS[t['owner']]} | {t['points']} | {t['prio']} | {t['summary']} |" for t in ordered)
    owners = "\n".join(f"| {k} | {v} |" for k, v in plan.OWNERS.items())
    return f"""# {plan.TITLE}

One Markdown file per epic and per ticket, written to be pasted into Jira (or imported from `jira-import.csv`). Keys `{plan.PROJECT}-n` are placeholders until the project exists; dependencies use the same placeholders. Phases, weeks and identifiers refer to {plan.COMPANION}.

**Totals:** {len(plan.EPICS)} epics · {len(ts)} tickets · {points(ts)} story points

## By phase

| Phase | Name | Weeks | Tickets | Points |
| --- | --- | --- | --- | --- |
{phases}

## Epics

| Key | Epic | Owner | Tickets | Points |
| --- | --- | --- | --- | --- |
{epics}

## All tickets

| Key | Epic | Phase | Weeks | Type | Owner | Points | Priority | Summary |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
{rows}

## Critical path

{critical_path(plan)}

## Owners

| Code | Role |
| --- | --- |
{owners}
"""


def write_csv(plan, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["Issue ID", "Summary", "Issue Type", "Epic Name", "Epic Link", "Description", "Priority", "Story Points", "Labels", "Blocked by"])
        for key, name, phase, owner, desc in plan.EPICS:
            w.writerow([key, name, "Epic", name, "", desc, "High", points(by_epic(plan.TICKETS, key)), f"{plan.LABEL} epic", ""])
        for t in plan.TICKETS:
            desc = t["desc"] + "\n\nAcceptance criteria:\n" + "\n".join(f"- {a}" for a in t["ac"]) + "\n\nReferences: " + ", ".join(t["refs"])
            w.writerow([t["key"], t["summary"], t["type"], "", t["epic"], desc, t["prio"], t["points"], f"{plan.LABEL} phase-{t['phase']} {t['epic'].lower()}", " ".join(t["deps"])])


def build(plan_path: str, out: str) -> dict:
    plan = load_plan(plan_path); os.makedirs(out, exist_ok=True)
    files = {e[0]: f"{e[0]}-{slug(e[1])}.md" for e in plan.EPICS}
    files.update({t["key"]: f"{t['key']}-{slug(t['summary'])}.md" for t in plan.TICKETS})
    for e in plan.EPICS: open(os.path.join(out, files[e[0]]), "w", encoding="utf-8").write(epic_file(e, plan, files))
    for t in plan.TICKETS: open(os.path.join(out, files[t["key"]]), "w", encoding="utf-8").write(ticket_file(t, plan, files))
    open(os.path.join(out, "README.md"), "w", encoding="utf-8").write(readme(plan, files))
    write_csv(plan, os.path.join(out, "jira-import.csv"))
    return {"epics": len(plan.EPICS), "tickets": len(plan.TICKETS), "points": points(plan.TICKETS), "files": len(files) + 2}


if __name__ == "__main__":
    if len(sys.argv) != 3: sys.exit(__doc__)
    print(build(sys.argv[1], sys.argv[2]))
