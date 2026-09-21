#!/usr/bin/env python3
"""Publish the Collection's pages into a checkout of the knowledge base, a standalone product.

    python3 tools/publish_kb.py /path/to/knowledge-base [--check]

Copies exports/knowledgebase/docs/** (generated: one page per component, one SKILL.md per skill, the components
index) and content/knowledgebase/docs/** (authored: practices, the use case, the programme) into <checkout>/docs;
gives each section README the block it needs so every page is linked from its section (between
`<!-- collection:start -->` and `<!-- collection:end -->` markers, inserted once, replaced on every run); adds the
`components` section to kb.config.yaml if it is missing. Idempotent: running it twice changes nothing the second
time. `--check` reports what would change and exits 1 if anything would, for a CI job in the product.

Then, in the checkout: `poetry run kb-librarian index --write && poetry run kb-librarian check`.
"""
from __future__ import annotations
import argparse, os, re, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPORT = os.path.join(ROOT, "exports", "knowledgebase")
CONTENT = os.path.join(ROOT, "content", "knowledgebase")
START, END = "<!-- collection:start -->", "<!-- collection:end -->"

# Where each section's block goes when the markers are not there yet: after the first match of the anchor.
ANCHORS = {
    "skills": re.compile(r"^\| \[policy-qa\].*$|^\| \[[^\]]+\]\([^)]+/SKILL\.md\).*$(?![\s\S]*^\| \[)", re.M),   # the last row of the catalog table
    "best-practices": re.compile(r"^\| \[Observability\].*$", re.M),
    "paved-roads": re.compile(r"^\[Use case 001\].*$", re.M),
    "onboarding": re.compile(r"^5\. \[Checklist\].*$", re.M),
}


def read(p): return open(p, encoding="utf-8").read()


def block_for(section: str) -> str | None:
    for base in (EXPORT, CONTENT):
        p = os.path.join(base, "sections", f"{section}.md")
        if os.path.exists(p):
            body = read(p).strip("\n")
            return body if body else None
    return None


def with_block(text: str, section: str, block: str) -> str:
    inner = f"{START}\n{block}\n{END}"
    if START in text and END in text:
        return text[: text.index(START)] + inner + text[text.index(END) + len(END):]
    m = ANCHORS[section].search(text)
    if m:
        return text[: m.end()] + "\n" + inner + text[m.end():]
    return text.rstrip("\n") + "\n\n" + inner + "\n"


def config_with_section(cfg: str, snippet: str) -> str:
    if re.search(r"^\s+- id: components\s*$", cfg, re.M):
        return cfg
    m = re.search(r"^frontmatter:", cfg, re.M)
    if not m:
        print("note: kb.config.yaml has no `frontmatter:` key; the components section goes at the end of the file")
        return cfg.rstrip("\n") + "\n" + snippet.rstrip("\n") + "\n"
    return cfg[: m.start()].rstrip("\n") + "\n" + snippet.rstrip("\n") + "\n" + cfg[m.start():]


def plan(checkout: str) -> dict:
    """path in the checkout -> new content, for every file that would change."""
    changes = {}
    docs = os.path.join(checkout, "docs")
    for base in (os.path.join(EXPORT, "docs"), os.path.join(CONTENT, "docs")):
        for dirpath, _, files in os.walk(base):
            for f in files:
                src = os.path.join(dirpath, f); dst = os.path.join(docs, os.path.relpath(src, base))
                if not os.path.exists(dst) or read(dst) != read(src):
                    changes[dst] = read(src)
    for section in ANCHORS:
        block = block_for(section)
        readme = os.path.join(docs, section, "README.md")
        if block and os.path.exists(readme):
            new = with_block(read(readme), section, block)
            if new != read(readme): changes[readme] = new
    cfg = os.path.join(checkout, "kb.config.yaml")
    snippet = os.path.join(CONTENT, "kb.config.section.yaml")
    if os.path.exists(cfg) and os.path.exists(snippet):
        new = config_with_section(read(cfg), read(snippet))
        if new != read(cfg): changes[cfg] = new
    return changes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("checkout"); ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if not os.path.exists(os.path.join(a.checkout, "kb.config.yaml")):
        print(f"{a.checkout} is not a knowledge-base checkout (no kb.config.yaml)"); return 2
    if not os.path.isdir(os.path.join(EXPORT, "docs")):
        print("exports/knowledgebase is missing: run python3 tools/shelf.py --write first"); return 2
    changes = plan(a.checkout)
    for p in sorted(changes):
        print(("would write " if a.check else "wrote ") + os.path.relpath(p, a.checkout))
    if a.check:
        print(f"{len(changes)} file(s) would change"); return 1 if changes else 0
    for p, content in changes.items():
        os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "w", encoding="utf-8").write(content)
    print(f"{len(changes)} file(s) written. Next, in {a.checkout}: poetry run kb-librarian index --write && poetry run kb-librarian check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
