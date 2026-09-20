#!/usr/bin/env python3
"""The catalog tool: validates every component manifest, checks vendored copies, regenerates CATALOG.md, runs tests.

    python3 tools/catalog.py --check          # manifests valid, vendored files identical, every export current (CI)
    python3 tools/catalog.py --write          # regenerate CATALOG.md, the hub's collection.ts and the knowledge-base pages
    python3 tools/catalog.py --test           # run every component's test command (add --only python|typescript|skills)
    python3 tools/catalog.py --list           # one line per component

Standard library only. A component is a directory under components/ that holds a `component.json` (the contract is
in CONTRIBUTING.md). Nothing here reads a component's code; the manifest and the README are the interface.

Exports: CATALOG.md (the human index); hub/src/api/mock/collection.ts (every component as a listing on the hub's
Discover page, with a detail page built from its README); knowledgebase/docs/components/<name>.md and
docs/skills/<name>/SKILL.md (pages the librarian keeps healthy). Tags must come from the knowledge base's taxonomy.
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPONENTS = os.path.join(ROOT, "components")
CATALOG_MD = os.path.join(ROOT, "CATALOG.md")
HUB_TS = os.path.join(ROOT, "hub", "src", "api", "mock", "collection.ts")
KB = os.path.join(ROOT, "knowledgebase")
KB_DOCS = os.path.join(KB, "docs")
KB_CONFIG = os.path.join(KB, "kb.config.yaml")
MARK_START, MARK_END = "<!-- collection:start -->", "<!-- collection:end -->"

KINDS = ("tool", "integration", "skill", "pattern")
LANGUAGES = ("python", "typescript", "markdown", "mixed")
STATUSES = ("ready", "draft", "deprecated")
REQUIRED = ("name", "kind", "language", "summary", "status", "source", "owner", "tags", "test")
KIND_LABEL = {"tool": "Tools", "integration": "Integrations", "skill": "Skills", "pattern": "Patterns"}


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
    if m["kind"] not in KINDS: p.append(f"kind must be one of {KINDS}")
    if m["language"] not in LANGUAGES: p.append(f"language must be one of {LANGUAGES}")
    if m["status"] not in STATUSES: p.append(f"status must be one of {STATUSES}")
    if not isinstance(m["tags"], list) or not m["tags"]: p.append("tags must be a non-empty list")
    if not isinstance(m["source"], dict) or "project" not in m["source"]: p.append("source must be an object with at least `project`")
    if len(m["summary"]) > 160: p.append("summary is longer than 160 characters")
    if not os.path.exists(os.path.join(m["_dir"], "README.md")): p.append("README.md is missing")
    if m["kind"] == "skill" and not os.path.exists(os.path.join(m["_dir"], "SKILL.md")): p.append("a skill needs SKILL.md")
    if m["language"] in ("python", "typescript", "mixed") and not m["test"]: p.append("a code component needs a test command")
    for v in m.get("vendored", []):
        if not isinstance(v, dict) or "path" not in v or "from" not in v:
            p.append("vendored entries are {path, from}"); continue
        here, there = os.path.join(m["_dir"], v["path"]), os.path.join(ROOT, v["from"])
        if not os.path.exists(here): p.append(f"vendored file {v['path']} is missing")
        elif not os.path.exists(there): p.append(f"vendored source {v['from']} does not exist")
        elif open(here, "rb").read() != open(there, "rb").read(): p.append(f"vendored file {v['path']} differs from {v['from']}; copy it again")
    for tag in m.get("tags", []) if isinstance(m.get("tags"), list) else []:
        if kb_taxonomy() and tag not in kb_taxonomy():
            p.append(f"tag `{tag}` is not in the knowledge base's taxonomy (kb.config.yaml)")
    for dep in m.get("pairs_with", []):
        if not any(os.path.basename(d) == dep for d in all_dirs()):
            p.append(f"pairs_with names an unknown component `{dep}`")
    return p


_taxonomy: set | None = None


def kb_taxonomy() -> set:
    """The tags kb.config.yaml allows, parsed from its `taxonomy: tags:` block without a YAML library."""
    global _taxonomy
    if _taxonomy is None:
        _taxonomy = set()
        if os.path.exists(KB_CONFIG):
            block = re.search(r"^taxonomy:\n\s+tags:\n((?:\s+- .+\n)+)", open(KB_CONFIG, encoding="utf-8").read(), re.M)
            if block:
                _taxonomy = {line.strip()[2:].strip() for line in block.group(1).splitlines() if line.strip().startswith("- ")}
    return _taxonomy


_dirs: list[str] | None = None


def all_dirs() -> list[str]:
    global _dirs
    if _dirs is None:
        _dirs = [os.path.dirname(x) for x in find_manifests()]
    return _dirs


def render(ms: list[dict]) -> str:
    lines = ["# Catalog", "", "Generated by `python3 tools/catalog.py --write`; do not edit by hand. One line per component; the README in each directory is the five-minute introduction.", ""]
    total = len(ms)
    ready = sum(1 for m in ms if m["status"] == "ready")
    lines += [f"{total} components, {ready} ready. Kinds: " + ", ".join(f"{KIND_LABEL[k].lower()} {sum(1 for m in ms if m['kind'] == k)}" for k in KINDS if any(m["kind"] == k for m in ms)), ""]
    for kind in KINDS:
        group = [m for m in ms if m["kind"] == kind]
        if not group: continue
        lines += [f"## {KIND_LABEL[kind]}", "", "| Component | Language | Status | Summary | From | Tags |", "| --- | --- | --- | --- | --- | --- |"]
        for m in group:
            src = m["source"].get("project", "")
            if m["source"].get("path"): src += f" (`{m['source']['path']}`)"
            lines.append(f"| [{m['name']}]({m['_rel']}/) | {m['language']} | {m['status']} | {m['summary']} | {src} | {', '.join(m['tags'])} |")
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


# ---------------- the hub export ----------------

HUB_KIND = {"tool": "tool", "integration": "tool", "pattern": "tool", "skill": "knowledge"}
HUB_LIFECYCLE = {"ready": "GA", "draft": "preview", "deprecated": "retired"}
HUB_GLYPH = {"tool": "layers", "integration": "bolt", "pattern": "pen", "skill": "book"}


def hub_listing(m: dict) -> dict:
    sec = readme_sections(m)
    return {"id": m["name"], "slug": m["name"], "kind": HUB_KIND[m["kind"]], "name": title_of(m), "description": m["summary"], "road": "R1",
            "lifecycle": HUB_LIFECYCLE[m["status"]], "icon": "m" if "security" in m["tags"] else "", "glyph": "shield" if "security" in m["tags"] else HUB_GLYPH[m["kind"]],
            "meta": [{"text": f"R1 · {m['kind']}", "kind": ""}, {"text": m["language"], "kind": "mono"}, {"text": HUB_LIFECYCLE[m["status"]], "kind": "ok" if m["status"] == "ready" else "warn"}],
            "footNote": f"from {m['source']['project']} · {m['source'].get('snapshot', '')}".rstrip(" ·"), "access": "open", "tagline": ", ".join(m["tags"]), "collection": True,
            "_sections": sec}


def hub_detail(m: dict, listing: dict) -> dict:
    sec = listing.pop("_sections")
    inside = table_rows(sec.get("What is inside", ""))
    rules = bullets(sec.get("Rules it enforces", ""))
    does = paragraphs(sec.get("What it is for", "") or sec.get("lead", ""))[:2] + rules[:4]
    steps = [s for s in paragraphs(sec.get("How to reuse it", ""))][:3] or ["Copy the directory into your project.", "Run the tests.", "Wire the transport, secrets or connection it names."]
    return {**listing, "crumbs": ["Discover", "Knowledge" if listing["kind"] == "knowledge" else "Tools", listing["name"]], "youActAt": "L1", "ladderMax": "L1",
            "headerChips": [{"text": "road R1", "kind": "line"}, {"text": m["language"], "kind": "mono"}, {"text": f"{m['kind']} · {m['status']}", "kind": "ok" if m["status"] == "ready" else "warn"}] + [{"text": t, "kind": "line"} for t in m["tags"]],
            "tiles": [{"label": "Language", "value": m["language"], "note": "standard library only" if m["language"] == "python" and not m["requires"] else ", ".join(m["requires"]) or "no runtime dependency"},
                      {"label": "Status", "value": m["status"], "note": f"snapshot {m['source'].get('snapshot', '')}"},
                      {"label": "Pairs with", "value": str(len(m.get("pairs_with", []))), "note": ", ".join(m.get("pairs_with", [])) or "stands alone"}],
            "does": does,
            "catalog": {"name": f"{m['name']} · component.json", "signed": False, "entries": [{"op": f, "tier": "R", "classes": "internal", "note": d[:120]} for f, d in inside[:8]]},
            "trust": [{"label": "Tests", "value": "green" if m["test"] else "n/a", "note": m["test"][:60] or "a checklist in SKILL.md"}, {"label": "Rules it enforces", "value": str(len(rules)), "note": "listed on the README"}],
            "evidence": [{"label": "README", "href": f"{m['_rel']}/README.md", "icon": "doc"}, {"label": "Tests", "href": f"{m['_rel']}/", "icon": "shield"}, {"label": "Knowledge base page", "href": kb_href(m), "icon": "db"}],
            "cost": [],
            "getStarted": [{"n": str(i + 1), "title": s[:90], "small": "", "state": "on" if i == 0 else ""} for i, s in enumerate(steps)],
            "owner": [{"label": "owner", "value": m["owner"]}, {"label": "source", "value": f"{m['source']['project']} · {m['source'].get('path', '')}".rstrip(" ·")}, {"label": "support", "value": "the AI champions channel"}],
            "versions": [{"version": m["source"].get("snapshot", "") or "0.1", "state": "current", "date": m["source"].get("snapshot", "")}],
            "changelogHref": f"{m['_rel']}/README.md"}


def kb_href(m: dict) -> str:
    return f"docs/skills/{m['name']}/SKILL.md" if m["kind"] == "skill" else f"docs/components/{m['name']}.md"


def render_hub(ms: list[dict]) -> str:
    listings = [hub_listing(m) for m in ms]
    details = {m["name"]: hub_detail(m, dict(l)) for m, l in zip(ms, listings)}
    for l in listings: l.pop("_sections", None)
    body = ("// Generated by `python3 tools/catalog.py --write` from components/*/component.json and each README. Do not edit.\n"
            "// Every component of the collection as a listing on Discover (under its kind's tab and in search) with a\n"
            "// listing page built from its README. `collection: true` keeps them out of the artboard's default \"All\" tab.\n"
            'import type { ConsumerDetail, ConsumerSummary } from "../types";\n\n'
            f"export const COLLECTION_LISTINGS: ConsumerSummary[] = {json.dumps(listings, indent=2, ensure_ascii=False)};\n\n"
            f"export const COLLECTION_DETAILS: Record<string, ConsumerDetail> = {json.dumps(details, indent=2, ensure_ascii=False)};\n")
    return body


# ---------------- the knowledge-base export ----------------

KB_OWNER = {"tool": "ai-platform-engineering", "integration": "ai-platform-engineering", "pattern": "ai-platform-architecture", "skill": "ai-platform-enablement"}


def _plain(text: str) -> str:
    """Markdown links become their text: knowledge-base links must resolve inside docs/, and READMEs point at code."""
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)


def render_kb_component(m: dict) -> str:
    readme = open(os.path.join(m["_dir"], "README.md"), encoding="utf-8").read()
    body = _plain(readme).replace("\n# ", "\n# ", 1)
    fm = (f"---\ntitle: {json.dumps(title_of(m))}\nowner: {KB_OWNER[m['kind']]}\nstatus: {'active' if m['status'] == 'ready' else ('deprecated' if m['status'] == 'deprecated' else 'draft')}\n"
          f"reviewed: '{m['source'].get('snapshot') or '2026-09-20'}'\ntags: [{', '.join(m['tags'])}]\naudience: [engineer]\n---\n")
    note = (f"\n> A component of the collection: `{m['_rel']}/` in the repository (kind {m['kind']}, {m['language']}, status {m['status']}). "
            f"Copy it from there; this page is its README, published by the catalog tool.\n")
    lines = body.splitlines()
    lines.insert(1, note)
    return fm + "\n".join(lines).rstrip() + "\n"


def render_kb_components_index(ms: list[dict]) -> str:
    rows = "\n".join(f"| [{title_of(m)}]({m['name']}.md) | {m['kind']} | {m['language']} | {m['summary']} |" for m in ms if m["kind"] != "skill")
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
a manifest and tests. They live in the repository under `components/`; the catalog tool publishes their READMEs here
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
one command, no hidden dependency, no secret. Open a pull request; the catalog tool checks the rest.
"""


def kb_skill_rows(ms: list[dict]) -> str:
    return "\n".join(f"| [{m['name']}]({m['name']}/SKILL.md) | {m['summary']} | {KB_OWNER['skill']} |" for m in ms if m["kind"] == "skill")


def splice(text: str, rows: str) -> str:
    if MARK_START not in text or MARK_END not in text:
        raise CatalogError("docs/skills/README.md lacks the collection markers")
    a, b = text.index(MARK_START) + len(MARK_START), text.index(MARK_END)
    return text[:a] + "\n" + rows + "\n" + text[b:]


def kb_outputs(ms: list[dict]) -> dict:
    """path -> content for every knowledge-base file the collection owns."""
    out = {os.path.join(KB_DOCS, "components", "README.md"): render_kb_components_index(ms)}
    for m in ms:
        if m["kind"] == "skill":
            out[os.path.join(KB_DOCS, "skills", m["name"], "SKILL.md")] = open(os.path.join(m["_dir"], "SKILL.md"), encoding="utf-8").read()
        else:
            out[os.path.join(KB_DOCS, "components", f"{m['name']}.md")] = render_kb_component(m)
    skills_readme = os.path.join(KB_DOCS, "skills", "README.md")
    out[skills_readme] = splice(open(skills_readme, encoding="utf-8").read(), kb_skill_rows(ms))
    return out


def exports(ms: list[dict]) -> dict:
    out = {CATALOG_MD: render(ms)}
    if os.path.isdir(os.path.dirname(HUB_TS)): out[HUB_TS] = render_hub(ms)
    if os.path.isdir(KB_DOCS): out.update(kb_outputs(ms))
    return out


def run_tests(ms: list[dict], only: str | None) -> int:
    failures = 0
    for m in ms:
        if only and m["language"] != only and not (only == "skills" and m["kind"] == "skill"):
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
    ap.add_argument("--test", action="store_true"); ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", choices=("python", "typescript", "markdown", "mixed", "skills"))
    a = ap.parse_args(argv)
    if not (a.check or a.write or a.test or a.list):
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
    ms.sort(key=lambda m: (KINDS.index(m["kind"]), m["name"]))
    if problems:
        print("\n".join(problems)); return 1
    if a.list:
        for m in ms: print(f"{m['kind']:<12}{m['language']:<12}{m['status']:<12}{m['name']:<32}{m['summary']}")
    if a.write:
        for path, content in exports(ms).items():
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w", encoding="utf-8").write(content)
        print(f"wrote CATALOG.md, the hub's collection.ts and the knowledge-base pages ({len(ms)} components)")
    if a.check:
        stale = [rel(p) for p, c in exports(ms).items() if not os.path.exists(p) or open(p, encoding="utf-8").read() != c]
        if stale:
            print("stale exports (run python3 tools/catalog.py --write):\n  " + "\n  ".join(stale)); return 1
        print(f"ok: {len(ms)} manifests valid, vendored copies identical, every export current")
    if a.test:
        f = run_tests(ms, a.only)
        print(f"{'FAILED' if f else 'ok'}: {f} component test suite(s) failed" if f else "ok: every component test suite passed")
        return 1 if f else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
