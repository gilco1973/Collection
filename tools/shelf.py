#!/usr/bin/env python3
"""The shelf tool: validates every component manifest, checks vendored copies, regenerates SHELF.md, runs tests.

"Shelf" and not "catalog": in the platform specification a catalog is a consumer's signed tool catalog (§4.12); the
components index is the shelf, so champions learn one meaning.

    python3 tools/shelf.py --check          # manifests valid, vendored files identical, every export current (CI)
    python3 tools/shelf.py --write          # regenerate SHELF.md, the hub's collection.ts and the knowledge-base pages
    python3 tools/shelf.py --test           # run every component's test command (add --only python|typescript|skills)
    python3 tools/shelf.py --list           # one line per component
    python3 tools/shelf.py --sign NAME --role owner|ai-security --by "Name <email>" [--used-in PROJECT]
    python3 tools/shelf.py --apply-signoffs FILE   # sign-offs exported from the hub's sign-off queue, into the manifests

Standard library only. A component is a directory under components/ that holds a `component.json` (the contract is
in CONTRIBUTING.md). Nothing here reads a component's code; the manifest and the README are the interface.

Exports: SHELF.md (the human index); hub/src/api/mock/collection.ts (every component as a listing on the hub's
Discover page, with a detail page built from its README); exports/knowledgebase/ (one page per component, one
SKILL.md per skill, the components index and the skills rows) that tools/publish_kb.py applies to a checkout of the
knowledge base, a standalone product. Tags must come from that product's taxonomy (tools/kb-taxonomy.json).
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPONENTS = os.path.join(ROOT, "components")
SHELF_MD = os.path.join(ROOT, "SHELF.md")
HUB_TS = os.path.join(ROOT, "hub", "src", "api", "mock", "collection.ts")
KB_EXPORT = os.path.join(ROOT, "exports", "knowledgebase")
KB_TAXONOMY = os.path.join(ROOT, "tools", "kb-taxonomy.json")

# The categories of AI component. Order is the shelf's order. `for` says who uses one; `needs` what it must contain
# beyond the common contract; `hub` the Discover tab it is listed under.
CATEGORIES = {
    "agent": {"label": "Agents", "for": "operators, from the hub or a channel; engineers deploy one", "hub": "agent", "glyph": "sparkle", "kb_owner": "ai-platform-engineering",
              "needs": "a template (TEMPLATE.md: role, stages, what it may propose, what it never does), the tools it may call and the harness it runs inside, declared in `agent`"},
    "harness": {"label": "Harnesses", "for": "engineers building an agent", "hub": "tool", "glyph": "layers", "kb_owner": "ai-platform-engineering",
                "needs": "the loop an agent runs inside: fixed hooks, action tiers, budgets, kill switches, a chained record"},
    "tool": {"label": "Tools", "for": "engineers; an agent calls one through its harness", "hub": "tool", "glyph": "layers", "kb_owner": "ai-platform-engineering",
             "needs": "code with one clear surface and a test that proves it"},
    "integration": {"label": "Integrations", "for": "engineers connecting a system", "hub": "tool", "glyph": "bolt", "kb_owner": "ai-platform-engineering",
                    "needs": "a client for an external system and an in-memory fake behind the same methods"},
    "pattern": {"label": "Patterns", "for": "engineers adopting a practice", "hub": "tool", "glyph": "pen", "kb_owner": "ai-platform-architecture",
                "needs": "a small reference implementation of one practice, with the practice page it belongs to"},
    "skill": {"label": "Skills", "for": "anyone: a person or a coding assistant follows it, nothing to run", "hub": "knowledge", "glyph": "book", "kb_owner": "ai-platform-enablement",
              "needs": "SKILL.md with the procedure and its checks, a template and a filled example"},
}
KINDS = tuple(CATEGORIES)
LANGUAGES = ("python", "typescript", "markdown", "mixed")
STATUSES = ("ready", "draft", "deprecated")
REQUIRED = ("name", "category", "language", "summary", "status", "source", "owner", "tags", "test", "spec", "version", "signoff", "walkthrough", "example")
SIGNOFF_ROLES = ("owner", "ai_security")
KIND_LABEL = {k: v["label"] for k, v in CATEGORIES.items()}


class CatalogError(Exception):
    pass


def find_manifests() -> list[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(COMPONENTS):
        dirnames[:] = [d for d in dirnames if d not in ("node_modules", "__pycache__", "_template", ".git")]
        if "component.json" in filenames:
            out.append(os.path.join(dirpath, "component.json"))
    return sorted(out)


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        try:
            m = json.load(f)
        except ValueError as e:
            raise CatalogError(f"{rel(path)}: not valid JSON ({e})")
    m["_dir"] = os.path.dirname(path)
    m["_rel"] = rel(os.path.dirname(path))
    return m


def rel(path: str) -> str:
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def validate(m: dict) -> list[str]:
    p = []
    for k in REQUIRED:
        if k not in m:
            p.append(f"missing field `{k}`")
    if p:
        return p
    if m["name"] != os.path.basename(m["_dir"]):
        p.append(f"name `{m['name']}` does not match its directory `{os.path.basename(m['_dir'])}`")
    if m["category"] not in KINDS: p.append(f"category must be one of {KINDS}")
    if m["language"] not in LANGUAGES: p.append(f"language must be one of {LANGUAGES}")
    if m["status"] not in STATUSES: p.append(f"status must be one of {STATUSES}")
    if not isinstance(m["tags"], list) or not m["tags"]: p.append("tags must be a non-empty list")
    if not isinstance(m["source"], dict) or "project" not in m["source"]: p.append("source must be an object with at least `project`")
    if len(m["summary"]) > 160: p.append("summary is longer than 160 characters")
    if not os.path.exists(os.path.join(m["_dir"], "README.md")): p.append("README.md is missing")
    if m["category"] == "skill" and not os.path.exists(os.path.join(m["_dir"], "SKILL.md")): p.append("a skill needs SKILL.md")
    if m["category"] == "agent":
        ag = m.get("agent")
        if not isinstance(ag, dict) or not ag.get("template") or not isinstance(ag.get("tools"), list) or not ag.get("tools") or not ag.get("harness"):
            p.append("an agent declares `agent`: {template, tools, harness}; it needs all three")
        else:
            if not os.path.exists(os.path.join(m["_dir"], ag["template"])): p.append(f"agent.template {ag['template']} is missing")
            elif agent_template(m) is None: p.append(f"agent.template {ag['template']} needs a ```json block: name, role, ladder, stages, tools by tier, never")
            for t in ag["tools"]:
                if category_of(t) is None: p.append(f"agent.tools names an unknown component `{t}`")
                elif category_of(t) not in ("tool", "integration", "pattern"): p.append(f"agent.tools: `{t}` is a {category_of(t)}, not a tool, integration or pattern")
            if category_of(ag["harness"]) != "harness": p.append(f"agent.harness must name a harness component; `{ag['harness']}` is {category_of(ag['harness']) or 'unknown'}")
    elif "agent" in m:
        p.append("only an agent carries `agent`")
    if m["language"] in ("python", "typescript", "mixed") and not m["test"]: p.append("a code component needs a test command")
    for v in m.get("vendored", []):
        if not isinstance(v, dict) or "path" not in v or "from" not in v:
            p.append("vendored entries are {path, from}"); continue
        here, there = os.path.join(m["_dir"], v["path"]), os.path.join(ROOT, v["from"])
        if not os.path.exists(here): p.append(f"vendored file {v['path']} is missing")
        elif not os.path.exists(there): p.append(f"vendored source {v['from']} does not exist")
        elif open(here, "rb").read() != open(there, "rb").read(): p.append(f"vendored file {v['path']} differs from {v['from']}; copy it again")
    if not isinstance(m.get("version"), str) or not re.fullmatch(r"\d+\.\d+\.\d+", m["version"]):
        p.append("version must be semantic (major.minor.patch)")
    so = m.get("signoff")
    if not isinstance(so, dict) or any(r not in so for r in SIGNOFF_ROLES):
        p.append("signoff must have `owner` and `ai_security` entries ({by, date, version}, or null while pending)")
    else:
        for role in SIGNOFF_ROLES:
            e = so[role]
            if e is not None and (not isinstance(e, dict) or not e.get("by") or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(e.get("date", ""))) or not e.get("version")):
                p.append(f"signoff.{role} must be null (pending) or {{by, date (YYYY-MM-DD), version}}")
    if not isinstance(m.get("walkthrough"), str) or not os.path.exists(os.path.join(m["_dir"], m.get("walkthrough") or "")):
        p.append("walkthrough must name a file in the component (WALKTHROUGH.md)")
    ex = m.get("example")
    if not isinstance(ex, dict) or not ex.get("path") or not os.path.exists(os.path.join(m["_dir"], ex["path"])):
        p.append("example must be {path, run}: a live example file that exists")
    elif m["language"] in ("python", "typescript", "mixed") and not ex.get("run"):
        p.append("a code component's example needs a `run` command")
    sp = m.get("spec")
    if not isinstance(sp, dict) or not sp.get("sections") or not sp.get("requirements") or not sp.get("replacement_test"):
        p.append("spec must name the specification sections and requirement ids it implements and its replacement test (§14.3)")
    elif not all(re.fullmatch(r"PLT-[A-Z]+-\d+", r) for r in sp["requirements"]):
        p.append("spec.requirements must be PLT-<family>-<n> ids")
    for tag in m.get("tags", []) if isinstance(m.get("tags"), list) else []:
        if kb_taxonomy() and tag not in kb_taxonomy():
            p.append(f"tag `{tag}` is not in the knowledge base's taxonomy (kb.config.yaml)")
    for dep in m.get("pairs_with", []):
        if not any(os.path.basename(d) == dep for d in all_dirs()):
            p.append(f"pairs_with names an unknown component `{dep}`")
    ui = m.get("used_in", [])
    if not isinstance(ui, list) or not all(isinstance(x, str) and x.strip() for x in ui):
        p.append("used_in must be a list of project names (where the component has been used for real)")
    return p


_taxonomy: set | None = None


def kb_taxonomy() -> set:
    """The tags the knowledge base's contract allows, mirrored in tools/kb-taxonomy.json."""
    global _taxonomy
    if _taxonomy is None:
        _taxonomy = set(json.load(open(KB_TAXONOMY, encoding="utf-8"))["tags"]) if os.path.exists(KB_TAXONOMY) else set()
    return _taxonomy


_dirs: list[str] | None = None


def category_of(name: str) -> str | None:
    """The category another component declares, or None when no component has that name."""
    for d in all_dirs():
        if os.path.basename(d) == name:
            try:
                return json.load(open(os.path.join(d, "component.json"), encoding="utf-8")).get("category")
            except ValueError:
                return None
    return None


def agent_template(m: dict) -> dict | None:
    """The agent's template as data: the first ```json block of TEMPLATE.md, with the keys an agent needs."""
    text = open(os.path.join(m["_dir"], m["agent"]["template"]), encoding="utf-8").read()
    f = re.search(r"```json\n(.*?)\n```", text, re.S)
    if not f: return None
    try:
        t = json.loads(f.group(1))
    except ValueError:
        return None
    return t if all(k in t for k in ("name", "role", "ladder", "stages", "tools", "never")) else None


def all_dirs() -> list[str]:
    global _dirs
    if _dirs is None:
        _dirs = [os.path.dirname(x) for x in find_manifests()]
    return _dirs


def render(ms: list[dict]) -> str:
    lines = ["# The shelf", "", "Generated by `python3 tools/shelf.py --write`; do not edit by hand. One line per component; the README in each directory is the five-minute introduction.", ""]
    total = len(ms)
    ready = sum(1 for m in ms if m["status"] == "ready")
    signed = sum(1 for m in ms if signed_state(m) == "signed")
    lines += [f"{total} components, {ready} ready, {signed} signed by both the owner and the AI security engineer at their current version. The stage column is the onboarding process in CONTRIBUTING.md; the hub's sign-off queue and onboarding tracker show the same facts. Categories: " + ", ".join(f"{KIND_LABEL[k].lower()} {sum(1 for m in ms if m['category'] == k)}" for k in KINDS if any(m["category"] == k for m in ms)), ""]
    for kind in KINDS:
        group = [m for m in ms if m["category"] == kind]
        if not group: continue
        lines += [f"## {KIND_LABEL[kind]}", "", f"For {CATEGORIES[kind]['for']}. Each one has {CATEGORIES[kind]['needs']}.", "", "| Component | Version | Stage | Sign-off | Language | Status | Summary | From | Implements (spec §) | Walkthrough · example |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for m in group:
            src = m["source"].get("project", "")
            if m["source"].get("path"): src += f" (`{m['source']['path']}`)"
            lines.append(f"| [{m['name']}]({m['_rel']}/) | {m['version']} | {stage_of(m)['label']} | {signed_state(m)} | {m['language']} | {m['status']} | {m['summary']} | {src} | {spec_short(m)} | [walkthrough]({m['_rel']}/{m['walkthrough']}) · [example]({m['_rel']}/{m['example']['path']}) |")
        lines.append("")
    lines += ["## By tag", ""]
    tags: dict[str, list[str]] = {}
    for m in ms:
        for t in m["tags"]:
            tags.setdefault(t, []).append(f"[{m['name']}]({m['_rel']}/)")
    for t in sorted(tags):
        lines.append(f"- **{t}**: " + ", ".join(tags[t]))
    lines.append("")
    return "\n".join(lines)


# ---------------- the README as data ----------------

def readme_sections(m: dict) -> dict:
    """H2 heading -> body text of the component's README; the H1 line is dropped, the lead paragraph is under "lead"."""
    out, cur = {}, "lead"
    for line in open(os.path.join(m["_dir"], "README.md"), encoding="utf-8").read().splitlines():
        if line.startswith("# "): continue
        if line.startswith("## "): cur = line[3:].strip(); out[cur] = ""; continue
        out[cur] = out.get(cur, "") + line + "\n"
    return {k: v.strip() for k, v in out.items()}


def title_of(m: dict) -> str:
    return m["name"].replace("-", " ").capitalize().replace("Aws ", "AWS ").replace("Rs256", "RS256").replace("Oidc", "OIDC").replace("Pkce", "PKCE").replace("Llm", "LLM").replace(" api ", " API ").replace("Stdlib", "Stdlib").replace("Ids only", "Ids-only").replace("Jwt", "JWT")


def table_rows(text: str) -> list[tuple]:
    rows = []
    for line in text.splitlines():
        if line.startswith("|") and not line.startswith("| ---") and not line.lower().startswith("| file"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 2: rows.append((cells[0].strip("`"), cells[1]))
    return rows


def bullets(text: str) -> list[str]:
    return [line[2:].strip() for line in text.splitlines() if line.startswith("- ")]


def paragraphs(text: str) -> list[str]:
    return [p.replace("\n", " ").strip() for p in text.split("\n\n") if p.strip() and not p.startswith("```") and not p.startswith("|")]


def signed_state(m: dict) -> str:
    """"signed" when both sign-offs name the current version; otherwise which are pending or stale."""
    so = m["signoff"]; out = []
    for role in SIGNOFF_ROLES:
        e = so.get(role)
        label = "owner" if role == "owner" else "AI security"
        if not e: out.append(f"{label} pending")
        elif e.get("version") != m["version"]: out.append(f"{label} stale ({e['version']})")
    return "signed" if not out else "; ".join(out)


STAGES = ("scaffolded", "built", "used once for real", "owner signed", "AI security signed", "on the shelf")


def stage_of(m: dict) -> dict:
    """Where a component is on its way to the shelf: the stage index, its label, and what has to happen next.

    The stages are the onboarding process in CONTRIBUTING.md; each one is read from the manifest, never guessed:
    draft -> ready (tests green) -> used_in names a project -> owner signed at this version -> AI security signed
    at this version -> on the shelf (the hub lists it as GA). A deprecated component is past the shelf.
    """
    so = m["signoff"]; v = m["version"]
    signed = lambda role: bool(so.get(role)) and so[role].get("version") == v
    if m["status"] == "deprecated":
        return {"index": len(STAGES), "of": len(STAGES), "label": "deprecated", "next": "consumers move to its replacement; the directory stays until they have"}
    if m["status"] == "draft":
        return {"index": 0, "of": len(STAGES), "label": STAGES[0], "next": "fill the README, the walkthrough, the live example and the tests; set status to ready when the tests are green"}
    if not m.get("used_in"):
        return {"index": 1, "of": len(STAGES), "label": STAGES[1], "next": "use it once in a real project and record where (used_in, or the owner's sign-off form)"}
    if not signed("owner"):
        stale = so.get("owner") and so["owner"].get("version") != v
        return {"index": 2, "of": len(STAGES), "label": STAGES[2], "next": f"the owner ({m['owner']}) signs at {v}" + (f"; the {so['owner']['version']} sign-off is stale" if stale else "")}
    if not signed("ai_security"):
        stale = so.get("ai_security") and so["ai_security"].get("version") != v
        return {"index": 3, "of": len(STAGES), "label": STAGES[3], "next": f"an AI security engineer signs at {v}" + (f"; the {so['ai_security']['version']} sign-off is stale" if stale else "")}
    return {"index": 5, "of": len(STAGES), "label": STAGES[5], "next": "keep it: bump the version on any change a consumer would notice, and both sign again"}


def shelf_record(m: dict) -> dict:
    """The component as the hub's sign-off queue and onboarding tracker see it: facts from the manifest only."""
    return {"name": m["name"], "title": title_of(m), "version": m["version"], "category": m["category"], "language": m["language"], "owner": m["owner"], "status": m["status"],
            "summary": m["summary"], "signoff": {r: m["signoff"].get(r) for r in SIGNOFF_ROLES}, "signed": signed_state(m) == "signed", "state": signed_state(m),
            "usedIn": list(m.get("used_in", [])), "stage": stage_of(m),
            "gates": {"readme": os.path.exists(os.path.join(m["_dir"], "README.md")), "walkthrough": os.path.exists(os.path.join(m["_dir"], m["walkthrough"])),
                      "example": os.path.exists(os.path.join(m["_dir"], m["example"]["path"])), "tests": bool(m["test"]), "spec": bool(m["spec"]["requirements"])},
            "test": m["test"], "exampleRun": m["example"].get("run") or "", "hubPath": f"/discover/{HUB_SEGMENT[CATEGORIES[m['category']]['hub']]}/{m['name']}", "repoPath": m["_rel"]}


def spec_short(m: dict) -> str:
    sp = m["spec"]
    return "§" + ", §".join(sp["sections"]) + " · " + ", ".join(sp["requirements"][:4]) + (" …" if len(sp["requirements"]) > 4 else "")


# ---------------- the hub export ----------------

HUB_KIND = {k: v["hub"] for k, v in CATEGORIES.items()}
HUB_LIFECYCLE = {"ready": "GA", "draft": "preview", "deprecated": "retired"}
HUB_GLYPH = {k: v["glyph"] for k, v in CATEGORIES.items()}
HUB_SEGMENT = {"agent": "agents", "knowledge": "knowledge", "tool": "tools"}
HUB_CRUMB = {"agent": "Agents", "knowledge": "Knowledge", "tool": "Tools"}


def hub_listing(m: dict) -> dict:
    sec = readme_sections(m)
    return {"id": m["name"], "slug": m["name"], "kind": HUB_KIND[m["category"]], "name": title_of(m), "description": m["summary"], "road": "R1",
            "lifecycle": HUB_LIFECYCLE[m["status"]] if signed_state(m) == "signed" else ("retired" if m["status"] == "deprecated" else "preview"), "icon": "m" if "security" in m["tags"] else "", "glyph": "shield" if "security" in m["tags"] else HUB_GLYPH[m["category"]],
            "meta": [{"text": f"R1 · {m['category']}", "kind": ""}, {"text": m["language"], "kind": "mono"}, {"text": f"v{m['version']}", "kind": "mono"}, {"text": "signed" if signed_state(m) == "signed" else "sign-off pending", "kind": "ok" if signed_state(m) == "signed" else "warn"}],
            "footNote": f"from {m['source']['project']} · {m['source'].get('snapshot', '')}".rstrip(" ·"), "access": "open", "tagline": ", ".join(m["tags"]), "collection": True,
            "_sections": sec}


def hub_detail(m: dict, listing: dict) -> dict:
    sec = listing.pop("_sections")
    inside = table_rows(sec.get("What is inside", ""))
    tpl = agent_template(m) if m["category"] == "agent" else None
    catalog = ({"name": f"{m['name']} · {m['agent']['template']}", "signed": False,
                "entries": [{"op": f"{t['target']}.{t['op']}", "tier": t["tier"], "classes": t.get("classes", "internal"), "note": t.get("note", "")[:120]} for t in tpl["tools"]]}
               if tpl else {"name": f"{m['name']} · component.json", "signed": False, "entries": [{"op": f, "tier": "R", "classes": "internal", "note": d[:120]} for f, d in inside[:8]]})
    parts = ([{"label": "Template", "value": "1", "note": f"{m['agent']['template']} · {len(tpl['tools'])} tools by tier, {len(tpl['never'])} nevers" if tpl else m["agent"]["template"]},
              {"label": "Tools", "value": str(len(m["agent"]["tools"])), "note": ", ".join(m["agent"]["tools"])},
              {"label": "Harness", "value": "1", "note": f"{m['agent']['harness']} · ladder {tpl['ladder']}" if tpl else m["agent"]["harness"]}] if m["category"] == "agent" else [])
    rules = bullets(sec.get("Rules it enforces", ""))
    does = paragraphs(sec.get("What it is for", "") or sec.get("lead", ""))[:2] + rules[:4]
    steps = [s for s in paragraphs(sec.get("How to reuse it", ""))][:3] or ["Copy the directory into your project.", "Run the tests.", "Wire the transport, secrets or connection it names."]
    return {**listing, "crumbs": ["Discover", HUB_CRUMB[listing["kind"]], listing["name"]], "youActAt": "L1", "ladderMax": "L1",
            "headerChips": [{"text": "road R1", "kind": "line"}, {"text": m["language"], "kind": "mono"}, {"text": f"{m['category']} · {m['status']}", "kind": "ok" if m["status"] == "ready" else "warn"},
                            {"text": "spec §" + ", §".join(m["spec"]["sections"]), "kind": "accent"}] + [{"text": t, "kind": "line"} for t in m["tags"]],
            "tiles": parts + [{"label": "Language", "value": m["language"], "note": "standard library only" if m["language"] == "python" and not m["requires"] else ", ".join(m["requires"]) or "no runtime dependency"},
                      {"label": "Status", "value": m["status"], "note": f"snapshot {m['source'].get('snapshot', '')}"},
                      {"label": "Pairs with", "value": str(len(m.get("pairs_with", []))), "note": ", ".join(m.get("pairs_with", [])) or "stands alone"}],
            "does": does,
            "catalog": catalog,
            "trust": [{"label": "Tests", "value": "green" if m["test"] else "n/a", "note": m["test"][:60] or "a checklist in SKILL.md"}, {"label": "Rules it enforces", "value": str(len(rules)), "note": "listed on the README"},
                      {"label": "Implements", "value": "§" + ", §".join(m["spec"]["sections"]), "note": ", ".join(m["spec"]["requirements"])},
                      {"label": "Owner sign-off", "value": (m["signoff"]["owner"] or {}).get("date", "pending"), "note": (m["signoff"]["owner"] or {}).get("by", "signs with tools/shelf.py --sign")},
                      {"label": "AI security sign-off", "value": (m["signoff"]["ai_security"] or {}).get("date", "pending"), "note": (m["signoff"]["ai_security"] or {}).get("by", "signs with tools/shelf.py --sign")}],
            "evidence": [{"label": "README", "href": f"{m['_rel']}/README.md", "icon": "doc"}, {"label": "Walkthrough, step by step", "href": f"{m['_rel']}/{m['walkthrough']}", "icon": "doc"},
                         {"label": "Live example: " + (m["example"].get("run") or m["example"]["path"]), "href": f"{m['_rel']}/{m['example']['path']}", "icon": "pulse"},
                         {"label": "Tests", "href": f"{m['_rel']}/", "icon": "shield"}, {"label": "Knowledge base page", "href": kb_href(m), "icon": "db"},
                         {"label": "Replacement test: " + m["spec"]["replacement_test"][:110] + ("…" if len(m["spec"]["replacement_test"]) > 110 else ""), "href": f"{m['_rel']}/README.md#known-limits", "icon": "pulse"}],
            "cost": [],
            "getStarted": [{"n": str(i + 1), "title": s[:90], "small": "", "state": "on" if i == 0 else ""} for i, s in enumerate(steps)],
            "owner": [{"label": "owner", "value": m["owner"]}, {"label": "source", "value": f"{m['source']['project']} · {m['source'].get('path', '')}".rstrip(" ·")}, {"label": "support", "value": "the AI champions channel"}],
            "versions": [{"version": m["version"], "state": "current", "date": m["source"].get("snapshot", "")}],
            "changelogHref": f"{m['_rel']}/README.md"}


def kb_href(m: dict) -> str:
    """The page's route in the knowledge base's console, relative to its base URL."""
    return f"/kb/page/skills/{m['name']}/SKILL.md" if m["category"] == "skill" else f"/kb/page/components/{m['name']}.md"


def render_hub(ms: list[dict]) -> str:
    listings = [hub_listing(m) for m in ms]
    details = {m["name"]: hub_detail(m, dict(l)) for m, l in zip(ms, listings)}
    for l in listings: l.pop("_sections", None)
    body = ("// Generated by `python3 tools/shelf.py --write` from components/*/component.json and each README. Do not edit.\n"
            "// Every component of the collection as a listing on Discover (under its category's tab and in search) with a\n"
            "// listing page built from its README. `collection: true` keeps them out of the artboard's default \"All\" tab.\n"
            'import type { ConsumerDetail, ConsumerSummary, ShelfRecord } from "../types";\n\n'
            f"export const COLLECTION_LISTINGS: ConsumerSummary[] = {json.dumps(listings, indent=2, ensure_ascii=False)};\n\n"
            f"export const COLLECTION_DETAILS: Record<string, ConsumerDetail> = {json.dumps(details, indent=2, ensure_ascii=False)};\n\n"
            "// The same components as the sign-off queue and the onboarding tracker see them: version, sign-offs, stage.\n"
            f"export const COLLECTION_SHELF: ShelfRecord[] = {json.dumps([shelf_record(m) for m in ms], indent=2, ensure_ascii=False)};\n")
    return body


# ---------------- the knowledge-base export ----------------

KB_OWNER = {k: v["kb_owner"] for k, v in CATEGORIES.items()}


def _plain(text: str) -> str:
    """Markdown links become their text: knowledge-base links must resolve inside docs/, and READMEs point at code."""
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)


def render_kb_component(m: dict) -> str:
    readme = open(os.path.join(m["_dir"], "README.md"), encoding="utf-8").read()
    body = _plain(readme).replace("\n# ", "\n# ", 1)
    fm = (f"---\ntitle: {json.dumps(title_of(m))}\nowner: {KB_OWNER[m['category']]}\nstatus: {'active' if m['status'] == 'ready' else ('deprecated' if m['status'] == 'deprecated' else 'draft')}\n"
          f"reviewed: '{m['source'].get('snapshot') or '2026-09-20'}'\ntags: [{', '.join(m['tags'])}]\naudience: [engineer]\n---\n")
    note = (f"\n> A component of the collection: `{m['_rel']}/` in the repository (category {m['category']}, {m['language']}, status {m['status']}). "
            f"Copy it from there; this page is its README, published by the shelf tool. It is an interim implementation of the platform design "
            f"specification §{', §'.join(m['spec']['sections'])} ({', '.join(m['spec']['requirements'])}); the replacement test is under Known limits. "
            f"Version {m['version']}; sign-off: {signed_state(m)}; walkthrough `{m['walkthrough']}`; live example `{m['example']['path']}`.\n")
    lines = body.splitlines()
    lines.insert(1, note)
    return fm + "\n".join(lines).rstrip() + "\n"


def render_kb_components_index(ms: list[dict]) -> str:
    groups = []
    for k in KINDS:
        if k == "skill": continue
        group = [m for m in ms if m["category"] == k]
        if not group: continue
        groups.append(f"## {KIND_LABEL[k]}\n\nFor {CATEGORIES[k]['for']}. Each one has {CATEGORIES[k]['needs']}.\n\n| Component | Language | What it is |\n| --- | --- | --- |\n"
                      + "\n".join(f"| [{title_of(m)}]({m['name']}.md) | {m['language']} | {m['summary']} |" for m in group))
    rows = "\n\n".join(groups)
    return f"""---
title: Reusable components
owner: ai-platform-engineering
status: active
reviewed: '2026-09-20'
tags: [paved-road, agents]
audience: [engineer]
---
# Reusable components

Self-contained pieces of code an engineer copies into a project and uses the same day: tools, integrations and
patterns lifted from products that run in production, each with a README that gets someone running in five minutes,
a manifest and tests. They live in the repository under `components/`; the shelf tool publishes their READMEs here
and lists them on the hub's Discover page. Skills are in the [agent skills catalog](../skills/README.md).

| Component | Kind | Language | What it is |
| --- | --- | --- | --- |
{rows}

## Using one

1. Read its page here or the README in the repository.
2. Copy the directory into your project (Python components are standard library only unless the page says otherwise).
3. Run its tests with the one command the page names.
4. Wire the transport, secrets provider or connection it names; nothing else changes.

## Contributing one

The contract is `CONTRIBUTING.md` in the repository: one directory, a manifest, a five-minute README, tests behind
one command, no hidden dependency, no secret. Open a pull request; the shelf tool checks the rest.
"""


def kb_skill_rows(ms: list[dict]) -> str:
    return "\n".join(f"| [{m['name']}]({m['name']}/SKILL.md) | {m['summary']} | {KB_OWNER['skill']} |" for m in ms if m["category"] == "skill")


def kb_outputs(ms: list[dict]) -> dict:
    """path -> content under exports/knowledgebase/, mirroring the product's docs/ layout; tools/publish_kb.py applies it."""
    docs = os.path.join(KB_EXPORT, "docs")
    out = {os.path.join(docs, "components", "README.md"): render_kb_components_index(ms),
           os.path.join(KB_EXPORT, "sections", "skills.md"): kb_skill_rows(ms) + "\n",
           os.path.join(KB_EXPORT, "README.md"): "# Generated for the knowledge base\n\nWritten by `python3 tools/shelf.py --write`; do not edit. `docs/` mirrors the product's layout; `sections/skills.md` is the block "
                                                "its skills README gains. Apply with `python3 tools/publish_kb.py <checkout>`.\n"}
    for m in ms:
        if m["category"] == "skill":
            out[os.path.join(docs, "skills", m["name"], "SKILL.md")] = open(os.path.join(m["_dir"], "SKILL.md"), encoding="utf-8").read()
        else:
            out[os.path.join(docs, "components", f"{m['name']}.md")] = render_kb_component(m)
    return out


def exports(ms: list[dict]) -> dict:
    out = {SHELF_MD: render(ms)}
    if os.path.isdir(os.path.dirname(HUB_TS)): out[HUB_TS] = render_hub(ms)
    out.update(kb_outputs(ms))
    return out


def run_examples(ms: list[dict], only: str | None) -> int:
    failures = 0
    for m in ms:
        if only and m["language"] != only and not (only == "skills" and m["category"] == "skill"):
            continue
        run = m["example"].get("run")
        if not run:
            print(f"-- {m['name']}: the live example is a document, {m['example']['path']}"); continue
        print(f"== {m['name']}: {run}", flush=True)
        r = subprocess.run(run, shell=True, cwd=m["_dir"], capture_output=True, text=True)
        if r.returncode != 0:
            failures += 1; print(f"!! {m['name']} example failed ({r.returncode})\n{r.stdout[-800:]}{r.stderr[-800:]}", flush=True)
    return failures


def record_signoff(m: dict, role: str, by: str, date: str | None = None, used_in: str | None = None) -> str | None:
    """Write one sign-off into the manifest after the tests pass; returns a problem, or None when recorded.

    The manifest is the record and the commit is the signature: nothing here is a credential. `used_in` names the
    project the owner used the component in; an owner cannot sign before one is recorded.
    """
    import datetime
    role = role.replace("-", "_")
    if role not in SIGNOFF_ROLES: return f"unknown role `{role}`"
    if not by or not by.strip(): return "a sign-off needs a name"
    path = os.path.join(m["_dir"], "component.json"); raw = json.load(open(path, encoding="utf-8"))
    if used_in and used_in.strip() and used_in.strip() not in raw.get("used_in", []):
        raw.setdefault("used_in", []).append(used_in.strip())
    if role == "owner" and not raw.get("used_in"):
        return "the owner signs after the component has been used once for real: record the project (--used-in)"
    if raw["status"] != "ready": return f"status is {raw['status']}; a sign-off needs a ready component"
    if m["test"] and subprocess.run(m["test"], shell=True, cwd=m["_dir"], capture_output=True).returncode != 0:
        return "tests fail; a sign-off needs a green suite"
    raw["signoff"][role] = {"by": by.strip(), "date": date or datetime.date.today().isoformat(), "version": raw["version"]}
    json.dump(raw, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False); open(path, "a").write("\n")
    return None


def sign(ms: list[dict], name: str, role: str, by: str, used_in: str | None = None) -> int:
    m = next((x for x in ms if x["name"] == name), None)
    if not m:
        print(f"unknown component `{name}`"); return 2
    problem = record_signoff(m, role, by, used_in=used_in)
    if problem:
        print(f"{name}: {problem}"); return 1
    print(f"{name}: {role.replace('-', '_')} signed at {m['version']} by {by}; commit component.json to make it a record, then run --write")
    return 0


def apply_signoffs(ms: list[dict], path: str) -> int:
    """Apply a file the hub's sign-off queue exported: {"signoffs": [{component, role, by, date, version, usedIn?}]}.

    A sign-off names the version it was given at; one for another version is stale and skipped, since the person
    read a different component. Each applied entry is written into its manifest exactly as --sign would.
    """
    try:
        doc = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"cannot read {path}: {e}"); return 2
    entries = doc.get("signoffs") if isinstance(doc, dict) else None
    if not isinstance(entries, list):
        print("the file must be {\"signoffs\": [...]} as the hub exports it"); return 2
    by_name = {m["name"]: m for m in ms}; failures = 0; applied = 0
    for e in entries:
        m = by_name.get(e.get("component", "")); tag = f"{e.get('component')} · {e.get('role')}"
        if not m:
            print(f"!! {tag}: unknown component"); failures += 1; continue
        if e.get("version") != m["version"]:
            print(f"!! {tag}: signed at {e.get('version')}, the component is at {m['version']}; ask again"); failures += 1; continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(e.get("date", ""))):
            print(f"!! {tag}: date must be YYYY-MM-DD"); failures += 1; continue
        problem = record_signoff(m, str(e.get("role", "")), str(e.get("by", "")), e["date"], e.get("usedIn"))
        if problem:
            print(f"!! {tag}: {problem}"); failures += 1; continue
        applied += 1; print(f"ok {tag}: signed at {m['version']} by {e['by']} on {e['date']}")
    print(f"{applied} sign-off(s) written; commit the manifests (the commit is the signature) and run --write" + (f"; {failures} skipped" if failures else ""))
    return 1 if failures else 0


def run_tests(ms: list[dict], only: str | None) -> int:
    failures = 0
    for m in ms:
        if only and m["language"] != only and not (only == "skills" and m["category"] == "skill"):
            continue
        if not m["test"]:
            print(f"-- {m['name']}: no test command"); continue
        print(f"== {m['name']}: {m['test']}", flush=True)
        r = subprocess.run(m["test"], shell=True, cwd=m["_dir"])
        if r.returncode != 0:
            failures += 1; print(f"!! {m['name']} failed ({r.returncode})", flush=True)
    return failures


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true"); ap.add_argument("--write", action="store_true")
    ap.add_argument("--test", action="store_true"); ap.add_argument("--list", action="store_true"); ap.add_argument("--examples", action="store_true")
    ap.add_argument("--sign", metavar="NAME"); ap.add_argument("--role", choices=("owner", "ai-security", "ai_security")); ap.add_argument("--by"); ap.add_argument("--used-in", metavar="PROJECT")
    ap.add_argument("--apply-signoffs", metavar="FILE")
    ap.add_argument("--only", choices=("python", "typescript", "markdown", "mixed", "skills"))
    a = ap.parse_args(argv)
    if not (a.check or a.write or a.test or a.list or a.examples or a.sign or a.apply_signoffs):
        ap.print_help(); return 2
    ms = []
    problems = []
    for path in find_manifests():
        try:
            m = load(path)
        except CatalogError as e:
            problems.append(str(e)); continue
        for p in validate(m):
            problems.append(f"{m['_rel']}: {p}")
        ms.append(m)
    ms.sort(key=lambda m: (KINDS.index(m["category"]), m["name"]))
    if problems:
        print("\n".join(problems)); return 1
    if a.sign:
        if not (a.role and a.by): print("--sign needs --role and --by"); return 2
        return sign(ms, a.sign, a.role, a.by, a.used_in)
    if a.apply_signoffs:
        return apply_signoffs(ms, a.apply_signoffs)
    if a.examples:
        f = run_examples(ms, a.only)
        print(f"FAILED: {f} live example(s) failed" if f else "ok: every live example ran")
        return 1 if f else 0
    if a.list:
        for m in ms: print(f"{m['category']:<12}{m['language']:<12}{m['status']:<8}{m['version']:<8}{stage_of(m)['label']:<22}{signed_state(m):<38}{m['name']:<28}{m['summary'][:60]}")
    if a.write:
        for path, content in exports(ms).items():
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w", encoding="utf-8").write(content)
        print(f"wrote SHELF.md, the hub's collection.ts and exports/knowledgebase ({len(ms)} components)")
    if a.check:
        stale = [rel(p) for p, c in exports(ms).items() if not os.path.exists(p) or open(p, encoding="utf-8").read() != c]
        if stale:
            print("stale exports (run python3 tools/shelf.py --write):\n  " + "\n  ".join(stale)); return 1
        print(f"ok: {len(ms)} manifests valid, vendored copies identical, every export current")
    if a.test:
        f = run_tests(ms, a.only)
        print(f"{'FAILED' if f else 'ok'}: {f} component test suite(s) failed" if f else "ok: every component test suite passed")
        return 1 if f else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
