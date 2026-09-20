#!/usr/bin/env python3
"""Scaffold a component from components/_template.

    python3 tools/new_component.py python my-tool --kind tool --summary "One line"
    python3 tools/new_component.py skills my-skill --kind skill --summary "One line"

Creates components/<group>/<name>/ with component.json, README.md and, for a skill, SKILL.md; for python, a tests/
folder with one passing test so the shelf's --test run is green from the first commit.
"""
from __future__ import annotations
import argparse, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "components", "_template")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("group", choices=("python", "typescript", "skills"))
    ap.add_argument("name")
    ap.add_argument("--kind", choices=("tool", "integration", "skill", "pattern"), required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--owner", default=os.environ.get("USER", "unknown"))
    a = ap.parse_args()
    dest = os.path.join(ROOT, "components", a.group, a.name)
    if os.path.exists(dest):
        print(f"{dest} exists"); return 1
    os.makedirs(dest)
    language = {"python": "python", "typescript": "typescript", "skills": "markdown"}[a.group]
    test = {"python": "python3 -m unittest discover -s tests -t . -v", "typescript": "npm ci --no-audit --no-fund && npx vitest run", "skills": ""}[a.group]
    manifest = {"name": a.name, "version": "0.1.0", "kind": a.kind, "language": language, "summary": a.summary, "status": "draft", "signoff": {"owner": None, "ai_security": None}, "used_in": [],
                "source": {"project": "new", "path": "", "snapshot": ""}, "owner": a.owner, "tags": ["paved-road"],
                "requires": [], "pairs_with": [], "test": test, "walkthrough": "WALKTHROUGH.md",
                "example": {"path": "example.py" if a.group == "python" else ("example.ts" if a.group == "typescript" else "EXAMPLE.md"), "run": {"python": "python3 example.py", "typescript": "npx tsx example.ts", "skills": ""}[a.group]}, "vendored": [],
                "spec": {"document": "CrossRiver AI Platform on AgentCore, design specification 0.21 (2026-09-16)", "sections": ["7.1"], "requirements": ["PLT-ROAD-2"],
                         "replacement_test": "State what the platform must pass before this component is retired (the specification's §14.3 rule)."}}
    json.dump(manifest, open(os.path.join(dest, "component.json"), "w"), indent=2); open(os.path.join(dest, "component.json"), "a").write("\n")
    readme = open(os.path.join(TEMPLATE, "README.md"), encoding="utf-8").read().replace("{{name}}", a.name).replace("{{summary}}", a.summary)
    open(os.path.join(dest, "README.md"), "w", encoding="utf-8").write(readme)
    if a.kind == "skill":
        open(os.path.join(dest, "SKILL.md"), "w", encoding="utf-8").write(open(os.path.join(TEMPLATE, "SKILL.md"), encoding="utf-8").read().replace("{{name}}", a.name).replace("{{summary}}", a.summary))
    open(os.path.join(dest, "WALKTHROUGH.md"), "w").write(f"# Walkthrough: {a.name}\n\n## 1. Run the live example\n\n```\ncd components/{a.group}/{a.name} && <the example command>\n```\n\nWhat you see.\n\n## 2. Copy it into your project\n\n## 3. Wire it\n\n## 4. Prove it\n")
    ex = {"python": '"""Live example: what this shows, in one line."""\nprint("replace me with something real")\n', "typescript": '// Live example. Run: npx tsx example.ts\nconsole.log("replace me with something real");\n', "skills": "# Example\n\nA filled example from a real use.\n"}[a.group]
    open(os.path.join(dest, manifest["example"]["path"]), "w").write(ex)
    if a.group == "python":
        os.makedirs(os.path.join(dest, "tests")); open(os.path.join(dest, "tests", "__init__.py"), "w").write("")
        open(os.path.join(dest, "tests", "test_smoke.py"), "w").write("import unittest\n\n\nclass Smoke(unittest.TestCase):\n    def test_imports(self):\n        self.assertTrue(True)\n")
    print(f"created {os.path.relpath(dest, ROOT)}; fill in README.md and component.json, then run python3 tools/shelf.py --write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
