#!/usr/bin/env python3
"""Services vendor files from components the way components vendor from each other: a copy, declared, checked.

    python3 services/vendor.py --check     # every listed copy is byte-identical to its source (CI)
    python3 services/vendor.py --write     # copy again after a component changed
"""
from __future__ import annotations
import json, os, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "services", "vendor.json")


def main(argv=None) -> int:
    a = (argv if argv is not None else sys.argv[1:]) or ["--check"]
    files = json.load(open(MANIFEST, encoding="utf-8"))["files"]
    problems = []
    for dest, src in files.items():
        d, s = os.path.join(ROOT, dest), os.path.join(ROOT, src)
        if not os.path.exists(s):
            problems.append(f"{src} does not exist"); continue
        if "--write" in a:
            os.makedirs(os.path.dirname(d), exist_ok=True); shutil.copyfile(s, d); continue
        if not os.path.exists(d) or open(d, "rb").read() != open(s, "rb").read():
            problems.append(f"{dest} differs from {src}; run python3 services/vendor.py --write")
    if problems:
        print("\n".join(problems)); return 1
    print(f"ok: {len(files)} vendored files {'written' if '--write' in a else 'identical to their components'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
