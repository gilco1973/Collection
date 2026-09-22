"""The collection's contract, checked on a candidate component before anyone is asked to sign it.

CONTRIBUTING.md is the contract and `tools/shelf.py --check` enforces it inside the repository. This check runs
anywhere (a candidate in its own repository, a zip from another team) and reports in the playground's terms:
what is missing, what leaks, what does not run. The manifest rules are a port of the shelf tool's `validate()`
(the playground imports nothing from `tools/`): what the shelf accepts passes here and what it refuses fails here.

Running the component's own tests and example is NOT a sandbox. The command runs in a throwaway copy of the
directory, as the tester's own user, with a minimal environment (PATH and the locale; HOME, TMPDIR and the XDG
directories point into the throwaway directory, so the tester's credentials files and variables are not handed
over), in a process group of its own that is killed when the time limit expires and again when the command ends.
That keeps an honest candidate from touching the source tree or leaving processes behind; it does not stop hostile
code, which can read and write anything the tester's user can (the source directory included, found for example
through /proc) and can leave its process group. For code you do not trust, run the playground itself in a
container (`playground/deploy/Dockerfile`).
"""
from __future__ import annotations

import ast
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from .probes import Result

# The shelf's vocabulary (tools/shelf.py): keep these in step with it.
CATEGORIES = ("agent", "harness", "tool", "integration", "pattern", "skill")
LANGUAGES = ("python", "typescript", "markdown", "mixed")
CODE_LANGUAGES = ("python", "typescript", "mixed")
STATUSES = ("ready", "draft", "deprecated")
REQUIRED = ("name", "category", "language", "summary", "status", "source", "owner", "tags", "test", "spec", "version", "signoff",
            "walkthrough", "example", "requires")
SIGNOFF_ROLES = ("owner", "ai_security")
SKILL_CHECKS_HEADING = "## Checks before finishing"
AGENT_TEMPLATE_KEYS = ("name", "role", "ladder", "stages", "tools", "never")
AGENT_TOOL_CATEGORIES = ("tool", "integration", "pattern")
SEMVER = re.compile(r"\d+\.\d+\.\d+")                     # fullmatch, as the shelf does: no pre-release suffix
REQUIREMENT_ID = re.compile(r"PLT-[A-Z]+-\d+")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# README headings: (heading, what a missing one costs). The five-minute start and the known limits are what a
# consumer and a signer cannot do without; the rest of the template is asked for, and a person judges it.
README_HEADINGS = ("Five-minute start", "What is inside", "How to reuse it", "Rules it enforces", "Where it came from", "Known limits")
README_REQUIRED = ("Five-minute start", "Known limits")
README_MINOR = ("Rules it enforces", "What it is for")
TIERS = ("R", "W1", "W2", "MONEY")
SKIP_DIRS = {"__pycache__", "node_modules", ".git", ".venv", "venv", "dist", ".pytest_cache", ".mypy_cache"}
# Directories that hold test data, not code: a package-shaped directory in there does not make an import local.
DATA_DIRS = {"fixtures", "fixture", "__fixtures__", "testdata", "test_data"}

PLACEHOLDER = re.compile(r"(?i)x{4,}|\*{3,}|<[^>]*>|\$\{|\{\{|%\(|^\$|changeme|change_me|example|placeholder|dummy|fake|redacted|your|test|\.\.\.")
SECRET_PATTERNS = [
    ("an AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("a private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("a GitHub token", re.compile(r"\b(?:ghp|gho|ghs|ghu)_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}")),
    ("a Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("an API key (sk- shape)", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{24,}")),
    ("a Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("a signed JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{16,}")),
]
# A credential written as a value: `password = "..."`, `"password": "..."`, `client_secret: ...`, `DB_PASSWORD=...`.
SECRET_KEY = r"[A-Za-z0-9_.-]*(?:password|passwd|passphrase|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|credential)s?[A-Za-z0-9_.-]*"
# A key that describes a credential rather than holding one (`token_url`, `secret_name`, `password_field`).
DESCRIPTIVE_SUFFIX = (r"names?|urls?|uri|endpoint|env|var|header|field|ids?|ref|path|file|type|kind|label|len|length|prefix|pattern|regex|rx|count|"
                      r"ttl|expiry|expires(?:_in)?|scopes?|audience|param|lifetime|seconds|ms|at")
DESCRIPTIVE_KEY = re.compile(rf"(?i:[_.-](?:{DESCRIPTIVE_SUFFIX}))$"                  # token_url, SECRET_NAME
                             rf"|[a-z0-9](?:{DESCRIPTIVE_SUFFIX.replace('_in', 'In').title()})$")   # SecretId, tokenUrl
SECRET_QUOTED = re.compile(rf"""(?i)(?<![A-Za-z0-9_$])["']?({SECRET_KEY})["']?\s*(?::=|=>|[:=])\s*[bru]?(["'])([^"'\s]{{8,}})\2""")
SECRET_BARE = re.compile(rf"""(?i)^\s*(?:export\s+|set\s+)?["']?({SECRET_KEY})["']?\s*[:=]\s*([^\s"'#;,]{{8,}})\s*(?:[#;].*)?$""")
BARE_VALUE_EXT = (".env", ".yaml", ".yml", ".ini", ".cfg", ".toml", ".properties", ".conf", ".txt", ".md", ".sh", "")
GUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
URL = re.compile(r"https?://([A-Za-z0-9.-]+)")
PLACEHOLDER_HOST = re.compile(r"(^|\.)(example(\.[a-z]+)?|invalid|test|local|localhost|internal)$|^localhost$|^127\.0\.0\.1$|^0\.0\.0\.0$|^\[?::1\]?$", re.I)
# distribution name -> import name, for the common packages whose names differ
IMPORT_NAMES = {"pillow": "pil", "pyyaml": "yaml", "beautifulsoup4": "bs4", "scikit_learn": "sklearn", "python_dateutil": "dateutil",
                "opencv_python": "cv2", "pyjwt": "jwt", "python_dotenv": "dotenv", "protobuf": "google"}
GENERATED = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "Pipfile.lock"}
TEXT_EXT = (".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".mts", ".cts", ".jsx", ".json", ".md", ".txt", ".yaml", ".yml", ".toml", ".cfg",
            ".ini", ".sh", ".env", ".html", ".css", ".properties", ".conf", "")
TS_EXT = (".ts", ".tsx", ".js", ".mjs", ".cjs", ".mts", ".cts", ".jsx")
TS_RELATIVE = re.compile(r"""(?:\bfrom|\bimport|\brequire)\s*\(?\s*["'](\.\.?(?:/[^"']*)?)["']""")
OUTPUT_TAIL_BYTES = 64 * 1024
RUN_MARKER = "AIPLAYGROUND_RUN"


def placeholder_guid(g: str) -> bool:
    hexes = g.replace("-", "").lower()
    return len(set(hexes)) <= 2 or hexes in ("0123456789abcdef0123456789abcdef",) or re.fullmatch(r"(0+1?|1+|f+|a+|12345678.*)", hexes) is not None


def placeholder_value(value: str) -> bool:
    """A value anyone can see is not a credential: XXXX, <...>, ${...}, ***, changeme, example, your-..."""
    return PLACEHOLDER.search(value) is not None or len(set(value)) <= 2


def within(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(root)]) == os.path.abspath(root)
    except ValueError:            # different drives
        return False


def text_files(root: str):
    """Every text file of the component; symlinks are skipped (they are reported by check_symlinks, never followed)."""
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not os.path.islink(os.path.join(dirpath, d))]
        for f in files:
            if f in GENERATED:
                continue
            path = os.path.join(dirpath, f)
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            if (os.path.splitext(f)[1].lower() in TEXT_EXT or f.startswith(".env")) and os.path.getsize(path) <= 1_000_000:
                yield path


def R(id, title, severity, status, summary, evidence=(), recommendation="", metrics=None) -> Result:
    return Result(f"contract/{id}", title, "CONTRACT", severity, status, summary, list(evidence), recommendation, "contract", metrics or {})


def checkout(start: str) -> str | None:
    """The root of the collection's checkout the candidate sits in (the directory with tools/kb-taxonomy.json), if any."""
    d = os.path.abspath(start)
    for _ in range(6):
        if os.path.exists(os.path.join(d, "tools", "kb-taxonomy.json")):
            return d
        d = os.path.dirname(d)
    return None


def taxonomy(start: str) -> list | None:
    """The knowledge base's tags, when the candidate sits in a checkout of the collection."""
    home = checkout(start)
    if home is None:
        return None
    with open(os.path.join(home, "tools", "kb-taxonomy.json"), encoding="utf-8") as f:
        return json.load(f).get("tags")


def shelf_categories(home: str | None) -> dict | None:
    """Component name -> category for every component of the checkout (as the shelf's find_manifests sees them)."""
    base = os.path.join(home, "components") if home else ""
    if not home or not os.path.isdir(base):
        return None
    out = {}
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in ("node_modules", "__pycache__", "_template", ".git"))
        if "component.json" in filenames:
            try:
                with open(os.path.join(dirpath, "component.json"), encoding="utf-8") as f:
                    cat = json.load(f).get("category")
            except (OSError, ValueError, AttributeError):
                cat = None
            out.setdefault(os.path.basename(dirpath), cat)
    return out


def agent_template_ok(path: str) -> bool:
    """The shelf's agent_template(): the first ```json block of TEMPLATE.md parses and has the keys an agent needs."""
    with open(path, encoding="utf-8") as f:
        block = re.search(r"```json\n(.*?)\n```", f.read(), re.S)
    if not block:
        return False
    try:
        t = json.loads(block.group(1))
    except ValueError:
        return False
    return isinstance(t, dict) and all(k in t for k in AGENT_TEMPLATE_KEYS)


def manifest_problems(m, root: str) -> tuple:
    """The shelf's validate() on a candidate: (problems, notes). A problem is what the shelf refuses; a note is what
    cannot be checked outside a checkout of the collection."""
    if not isinstance(m, dict):
        return ["component.json is not a JSON object"], []
    p, notes = [], []
    home = checkout(root)
    shelf = shelf_categories(home)
    for k in REQUIRED:
        if k not in m:
            p.append(f"missing field `{k}`")
    code = m.get("language") in CODE_LANGUAGES
    name = os.path.basename(os.path.abspath(root))
    if "name" in m and m["name"] != name:
        p.append(f"`name` is {m['name']!r}, the directory is {name!r}")
    if "category" in m and m["category"] not in CATEGORIES:
        p.append(f"`category` is one of {', '.join(CATEGORIES)}")
    if "language" in m and m["language"] not in LANGUAGES:
        p.append(f"`language` is one of {', '.join(LANGUAGES)}")
    if "status" in m and m["status"] not in STATUSES:
        p.append(f"`status` is one of {', '.join(STATUSES)}")
    if "tags" in m and (not isinstance(m["tags"], list) or not m["tags"]):
        p.append("`tags` lists at least one tag from the knowledge base's taxonomy")
    if "requires" in m and (not isinstance(m["requires"], list) or not all(isinstance(x, str) and x.strip() for x in m["requires"])):
        p.append("`requires` is a list of dependency names (empty when the standard library is enough)")
    if "source" in m and (not isinstance(m["source"], dict) or "project" not in m["source"]):
        p.append("`source` is an object with at least `project`")
    if "summary" in m and (not isinstance(m["summary"], str) or len(m["summary"]) > 160):
        p.append("`summary` is text of at most 160 characters")
    if not os.path.isfile(os.path.join(root, "README.md")):
        p.append("README.md is missing")
    if m.get("category") == "skill":
        skill = os.path.join(root, "SKILL.md")
        if not os.path.isfile(skill):
            p.append("a skill needs SKILL.md")
        else:
            with open(skill, encoding="utf-8", errors="replace") as f:
                text = "\n" + f.read().replace("\r\n", "\n") + "\n"
            if f"\n{SKILL_CHECKS_HEADING}\n" not in text:
                p.append(f'SKILL.md needs its checklist under "{SKILL_CHECKS_HEADING}" (CONTRIBUTING.md, rule 6)')
    if m.get("category") == "agent":
        ag = m.get("agent")
        if (not isinstance(ag, dict) or not ag.get("template") or not isinstance(ag.get("tools"), list) or not ag.get("tools")
                or not ag.get("harness")):
            p.append("an agent declares `agent`: {template, tools, harness}; it needs all three")
        else:
            tpl = os.path.join(root, str(ag["template"]))
            if not isinstance(ag["template"], str) or not os.path.isfile(tpl):
                p.append(f"agent.template {ag['template']} is missing")
            elif not agent_template_ok(tpl):
                p.append(f"agent.template {ag['template']} needs a ```json block: name, role, ladder, stages, tools by tier, never")
            if shelf is None:
                if not all(isinstance(t, str) and t.strip() for t in ag["tools"]) or not isinstance(ag["harness"], str):
                    p.append("agent.tools and agent.harness name components")
                notes.append("agent.tools and agent.harness are not checked against the collection (not inside a checkout)")
            else:
                for t in ag["tools"]:
                    cat = shelf.get(t) if isinstance(t, str) else None
                    if cat is None:
                        p.append(f"agent.tools names an unknown component `{t}`")
                    elif cat not in AGENT_TOOL_CATEGORIES:
                        p.append(f"agent.tools: `{t}` is a {cat}, not a tool, integration or pattern")
                harness = shelf.get(ag["harness"]) if isinstance(ag["harness"], str) else None
                if harness != "harness":
                    p.append(f"agent.harness must name a harness component; `{ag['harness']}` is {harness or 'unknown'}")
    elif "agent" in m:
        p.append("only an agent carries `agent`")
    if "test" in m and code and not m["test"]:
        p.append("`test` is the command that proves it works (a code component needs one)")
    vendored = m.get("vendored", [])
    if not isinstance(vendored, list):
        p.append("`vendored` is a list of {path, from}")
        vendored = []
    for v in vendored:
        if not isinstance(v, dict) or not isinstance(v.get("path"), str) or not isinstance(v.get("from"), str):
            p.append("vendored entries are {path, from}")
            continue
        here = os.path.join(root, v["path"])
        if not os.path.isfile(here):
            p.append(f"vendored file {v['path']} is missing")
        elif home is None or not os.path.isdir(os.path.join(home, "components")):
            notes.append(f"vendored {v['path']} is not compared with {v['from']} (not inside a checkout)")
        elif not os.path.isfile(os.path.join(home, v["from"])):
            p.append(f"vendored source {v['from']} does not exist")
        else:
            with open(here, "rb") as a, open(os.path.join(home, v["from"]), "rb") as b:
                if a.read() != b.read():
                    p.append(f"vendored file {v['path']} differs from {v['from']}; copy it again")
    if "version" in m and (not isinstance(m["version"], str) or not SEMVER.fullmatch(m["version"])):
        p.append("`version` is not a semantic version (major.minor.patch)")
    if "signoff" in m:
        so = m["signoff"]
        if not isinstance(so, dict) or any(r not in so for r in SIGNOFF_ROLES):
            p.append("`signoff` has `owner` and `ai_security` entries ({by, date, version}, or null while pending)")
        else:
            for role in SIGNOFF_ROLES:
                e = so[role]
                if e is not None and (not isinstance(e, dict) or not e.get("by") or not DATE.fullmatch(str(e.get("date", ""))) or not e.get("version")):
                    p.append(f"signoff.{role} is null (pending) or {{by, date (YYYY-MM-DD), version}}, never a hand-written value")
    if "walkthrough" in m and (not isinstance(m["walkthrough"], str) or not m["walkthrough"] or not os.path.isfile(os.path.join(root, m["walkthrough"]))):
        p.append("`walkthrough` names a WALKTHROUGH.md that exists")
    if "example" in m:
        ex = m["example"]
        if not isinstance(ex, dict) or not isinstance(ex.get("path"), str) or not ex["path"] or not os.path.exists(os.path.join(root, ex["path"])):
            p.append("`example` is {path, run} and the path exists")
        elif code and not ex.get("run"):
            p.append("a code component's example needs a `run` command")
    if "spec" in m:
        sp = m["spec"]
        if not isinstance(sp, dict) or not sp.get("sections") or not sp.get("requirements") or not sp.get("replacement_test"):
            p.append("`spec` names the specification sections and requirement ids it implements and its replacement test (§14.3)")
        elif not isinstance(sp["requirements"], list) or not all(isinstance(r, str) and REQUIREMENT_ID.fullmatch(r) for r in sp["requirements"]):
            p.append("spec.requirements are PLT-<family>-<n> ids")
    allowed = taxonomy(root)
    if isinstance(m.get("tags"), list) and allowed:
        bad = [t for t in m["tags"] if not isinstance(t, str) or t not in allowed]
        if bad:
            p.append(f"tags not in the knowledge base's taxonomy: {', '.join(sorted(map(str, bad)))}")
    pairs = m.get("pairs_with", [])
    if not isinstance(pairs, list):
        p.append("`pairs_with` is a list of component names")
    elif pairs and shelf is None:
        notes.append("pairs_with is not checked against the collection (not inside a checkout)")
    elif pairs:
        for dep in pairs:
            if not isinstance(dep, str) or dep not in shelf:
                p.append(f"pairs_with names an unknown component `{dep}`")
    ui = m.get("used_in", [])
    if not isinstance(ui, list) or not all(isinstance(x, str) and x.strip() for x in ui):
        p.append("`used_in` is a list of project names (where the component has been used for real)")
    return p, notes


def check_manifest(root: str) -> tuple:
    path = os.path.join(root, "component.json")
    rec = "Fill the manifest as CONTRIBUTING.md describes; python3 tools/new_component.py scaffolds a complete one."
    if not os.path.isfile(path):
        return None, R("manifest", "A manifest", "high", "fail", "there is no component.json", recommendation=rec)
    try:
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
    except (ValueError, UnicodeDecodeError) as e:
        return None, R("manifest", "A manifest", "high", "fail", f"component.json is not JSON: {e}", recommendation=rec)
    problems, notes = manifest_problems(m, root)
    if not isinstance(m, dict):
        return None, R("manifest", "A manifest", "high", "fail", problems[0], recommendation=rec)
    if problems:
        return m, R("manifest", "A complete manifest", "high", "fail", f"{len(problems)} problem(s) in component.json: " + "; ".join(problems[:6]),
                    [{"problems": problems, "not_checked": notes}], rec)
    extra = f" (not checked: {'; '.join(notes)})" if notes else ""
    return m, R("manifest", "A complete manifest", "high", "pass",
                f"component.json is complete: {m['name']} {m['version']}, {m['category']}, {m['status']}{extra}", [{"not_checked": notes}] if notes else [])


def check_readme(root: str) -> Result:
    path = os.path.join(root, "README.md")
    title = "A README in the template's shape"
    rec = "Use components/_template/README.md: every heading, and a five-minute start that runs as written."
    if not os.path.isfile(path):
        return R("readme", title, "medium", "fail", "there is no README.md", recommendation=rec)
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    heads = [h.strip().lower() for h in re.findall(r"^##\s+(.+)$", text, re.M)]
    missing = [h for h in README_HEADINGS if not any(x.startswith(h.lower()) for x in heads)]
    lead = re.sub(r"^#[^\n]*\n", "", text.lstrip()).split("\n## ")[0].strip()
    if "what it is for" not in heads and not lead:
        missing.insert(0, "What it is for")
    if not missing:
        return R("readme", title, "medium", "pass", "every heading of the template is there")
    listed = ", ".join("What it is for (or a lead paragraph)" if h == "What it is for" else h for h in missing)
    if any(h in README_REQUIRED for h in missing):
        return R("readme", title, "medium", "fail", "the README lacks: " + listed, [{"missing": missing}], rec)
    severity = "low" if all(h in README_MINOR for h in missing) else "medium"
    return R("readme", title, severity, "review", "the README lacks: " + listed + ". The shelf accepts it; a reviewer decides whether the "
             "README still gets a newcomer running and tells a signer what it guarantees.", [{"missing": missing}], rec)


def check_signoffs(m: dict | None) -> Result:
    rec = "Sign-offs are recorded only by a named person with tools/shelf.py --sign (or the hub's queue); never write them into the manifest."
    if not m or not isinstance(m.get("signoff"), dict):
        return R("signoffs", "Sign-offs untouched", "info", "skipped", "no manifest to read")
    filled = {k: v for k, v in m["signoff"].items() if v}
    if not filled:
        return R("signoffs", "Sign-offs untouched", "high", "pass", "both sign-offs are pending, as a candidate's should be")
    stale = [k for k, v in filled.items() if not isinstance(v, dict) or v.get("version") != m.get("version")]
    notes = [f"{k}: {v.get('by') if isinstance(v, dict) else v} at {v.get('version') if isinstance(v, dict) else '?'}" for k, v in filled.items()]
    return R("signoffs", "Sign-offs untouched", "high", "review",
             "the manifest already carries sign-offs (" + "; ".join(notes) + ")" + (f"; stale: {', '.join(stale)}" if stale else "") +
             ". Confirm each was recorded by the person named, through the shelf tool.", [{"signoff": m["signoff"]}], rec)


def local_modules(root: str) -> set:
    """Top-level names the component's own code can import: packages (directories with __init__.py) and modules
    (.py files), anywhere in the tree except test-data directories and symlinks."""
    local = set()
    for dirpath, dirs, files in os.walk(root):
        if set(os.path.relpath(dirpath, root).split(os.sep)) & DATA_DIRS:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not os.path.islink(os.path.join(dirpath, d))]
        local |= {d for d in dirs if d not in DATA_DIRS and os.path.isfile(os.path.join(dirpath, d, "__init__.py"))}
        local |= {f[:-3] for f in files if f.endswith(".py") and not os.path.islink(os.path.join(dirpath, f))}
    return local


def import_error_handler(t: ast.Try) -> bool:
    names = ("ImportError", "ModuleNotFoundError")
    for h in t.handlers:
        if isinstance(h.type, ast.Name) and h.type.id in names:
            return True
        if isinstance(h.type, ast.Tuple) and any(getattr(e, "id", "") in names for e in h.type.elts):
            return True
    return False


def dynamic_import(node: ast.Call):
    """(True, literal name or None) for importlib.import_module(...) / __import__(...); (False, None) otherwise."""
    f = node.func
    fname = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
    if fname not in ("import_module", "__import__"):
        return False, None
    arg = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "name"), None)
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return True, arg.value
    return True, None


def check_self_contained(root: str, m: dict | None) -> Result:
    rec = "Import only the standard library, the component's own files, and what `requires` declares; vendor shared files with `vendored`."
    root = os.path.abspath(root)
    requires = set()
    reqs = (m or {}).get("requires")
    for r in reqs if isinstance(reqs, list) else []:
        if isinstance(r, str) and r.strip():
            dist = re.split(r"[<>=!~\[ (;]", r.strip())[0].lower().replace("-", "_")
            requires |= {dist, IMPORT_NAMES.get(dist, dist)}
    local = local_modules(root)
    stdlib = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}

    def allowed(n: str) -> bool:
        return not n or n in stdlib or n in local or n.lower() in requires

    outside, dynamic, parse_errors = [], [], []
    for path in text_files(root):
        rel = os.path.relpath(path, root)
        if path.endswith(".py"):
            try:
                with open(path, encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=rel)
            except (SyntaxError, UnicodeDecodeError, ValueError) as e:
                parse_errors.append(f"{rel}: {e.__class__.__name__}")
                continue
            optional = set()     # absolute imports guarded by `except ImportError` are optional dependencies
            for t in ast.walk(tree):
                if isinstance(t, ast.Try) and import_error_handler(t):
                    optional |= {id(n) for b in t.body for n in ast.walk(b)}
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    if id(node) not in optional:
                        outside += [f"{rel}: imports {n}" for n in (a.name.split(".")[0] for a in node.names) if not allowed(n)]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:       # relative: always checked, guarded or not
                        base = os.path.dirname(path)
                        for _ in range(node.level - 1):
                            base = os.path.dirname(base)
                        if not within(base, root):
                            outside.append(f"{rel}: from {'.' * node.level}{node.module or ''} reaches outside the component")
                    elif id(node) not in optional and not allowed((node.module or "").split(".")[0]):
                        outside.append(f"{rel}: imports {(node.module or '').split('.')[0]}")
                elif isinstance(node, ast.Call):
                    is_dyn, name = dynamic_import(node)
                    if is_dyn:
                        where = f"{rel}:{node.lineno}"
                        if name is None:
                            dynamic.append(f"{where}: a dynamic import of a computed name ({ast.unparse(node)[:80]})")
                        elif name.startswith("."):
                            dynamic.append(f"{where}: a relative dynamic import {name!r}; confirm it stays inside the component")
                        elif id(node) not in optional and not allowed(name.split(".")[0]):
                            dynamic.append(f"{where}: imports {name.split('.')[0]} dynamically")
                    elif (getattr(node.func, "attr", "") in ("insert", "append") and "sys.path" in ast.unparse(node.func)
                          and ".." in ast.unparse(node)):
                        outside.append(f"{rel}: adds a parent directory to sys.path")
        elif path.endswith(TS_EXT):
            with open(path, encoding="utf-8", errors="replace") as f:
                for spec in TS_RELATIVE.findall(f.read()):
                    if not within(os.path.normpath(os.path.join(os.path.dirname(path), spec)), root):
                        outside.append(f"{rel}: imports {spec}")
    outside += [f"cannot parse {p}" for p in parse_errors]
    if outside:
        uniq = sorted(set(outside))
        more = f"; and {len(set(dynamic))} dynamic import(s) to confirm" if dynamic else ""
        return R("self-contained", "Self-contained", "high", "fail", f"{len(uniq)} import(s) outside the standard library, the component and `requires`: "
                 + "; ".join(uniq[:5]) + more, [{"imports": uniq[:50], "dynamic": sorted(set(dynamic))[:50]}], rec)
    if dynamic:
        uniq = sorted(set(dynamic))
        return R("self-contained", "Self-contained", "medium", "review", f"{len(uniq)} dynamic import(s) a person must confirm: " + "; ".join(uniq[:5]),
                 [{"dynamic": uniq[:50]}], rec)
    return R("self-contained", "Self-contained", "high", "pass", "imports only the standard library, its own files and what `requires` declares")


def secret_value(key: str, value: str) -> bool:
    """A key that names a credential, holding a value that is neither a placeholder nor a plain identifier."""
    if DESCRIPTIVE_KEY.search(key) or placeholder_value(value):
        return False
    classes = sum(bool(re.search(rx, value)) for rx in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9_.-]"))
    return classes >= 2 or len(value) >= 24


def secret_hits(rel: str, line: str, bare: bool) -> list:
    out = []
    for what, rx in SECRET_PATTERNS:
        if any(what == "a private key" or not placeholder_value(mt.group(0)) for mt in rx.finditer(line)):
            out.append(what)
    if any(secret_value(mt.group(1), mt.group(3)) for mt in SECRET_QUOTED.finditer(line)):
        out.append("a credential written as a value")
    elif bare:
        mt = SECRET_BARE.match(line)
        if mt and secret_value(mt.group(1), mt.group(2)):
            out.append("a credential written as a value")
    return out


def check_secrets(root: str) -> list:
    hits, guids, urls = [], [], {}
    for path in text_files(root):
        rel = os.path.relpath(path, root)
        name = os.path.basename(path)
        bare = name.startswith(".env") or os.path.splitext(name)[1].lower() in BARE_VALUE_EXT
        with open(path, encoding="utf-8", errors="replace") as f:
            for no, line in enumerate(f, 1):
                hits += [f"{rel}:{no}: {what}" for what in secret_hits(rel, line, bare)]
                for g in GUID.findall(line):
                    if not placeholder_guid(g):
                        guids.append(f"{rel}:{no}: {g}")
                for host in URL.findall(line):
                    host = host.rstrip(".").lower()
                    if "." in host and not PLACEHOLDER_HOST.search(host):
                        urls.setdefault(host, f"{rel}:{no}")
    out = []
    rec = "Credentials are names read at call time (secrets-by-name); placeholders look like placeholders (example.com, 00000000-…)."
    if hits:
        out.append(R("secrets", "No secrets in the files", "critical", "fail", f"{len(hits)} secret-shaped string(s): " + "; ".join(hits[:5]), [{"hits": hits[:50]}], rec))
    else:
        out.append(R("secrets", "No secrets in the files", "critical", "pass", "no secret-shaped string in any text file"))
    if guids:
        out.append(R("real-ids", "No real tenant or group ids", "high", "review", f"{len(guids)} id(s) that do not look like placeholders: " + "; ".join(guids[:5]),
                     [{"ids": guids[:50]}], "Replace real tenant, group and object ids with visible placeholders."))
    else:
        out.append(R("real-ids", "No real tenant or group ids", "high", "pass", "every GUID-shaped id is a visible placeholder"))
    if urls:
        listed = [f"{h} ({w})" for h, w in sorted(urls.items())]
        out.append(R("real-urls", "No real addresses", "medium", "review", f"{len(urls)} host(s) that are not placeholders: " + ", ".join(listed[:8]),
                     [{"hosts": listed[:50]}], "Use example.com, *.example.internal or localhost; a public specification link is fine once a person confirms it."))
    else:
        out.append(R("real-urls", "No real addresses", "medium", "pass", "every address is a placeholder or loopback"))
    return out


def check_symlinks(root: str) -> Result:
    """Symlinks are never followed by the scans; one that points outside the component is shown to a person."""
    root = os.path.realpath(root)
    outside, count = [], 0
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for n in dirs + files:
            path = os.path.join(dirpath, n)
            if not os.path.islink(path):
                continue
            count += 1
            if not within(os.path.realpath(path), root):
                outside.append(f"{os.path.relpath(path, root)} -> {os.readlink(path)}")
    title = "No links out of the component"
    if outside:
        return R("symlinks", title, "medium", "review", f"{len(outside)} symlink(s) point outside the component: " + "; ".join(outside[:5]),
                 [{"symlinks": outside[:50]}], "A component is one directory a consumer copies; replace a link out of it with the file, or vendor it.")
    return R("symlinks", title, "medium", "pass", f"{count} symlink(s), none pointing outside the component" if count else "no symlinks")


def run_env(work: str) -> dict:
    """The command's whole environment: PATH and the locale, with HOME, the temporary and the XDG directories inside
    the throwaway directory. Nothing else of the tester's environment is passed."""
    env = {k: os.environ[k] for k in ("PATH", "LANG", "LC_ALL", "SYSTEMROOT") if k in os.environ}
    home, tmp = os.path.join(work, "home"), os.path.join(work, "tmp")
    dirs = {"HOME": home, "TMPDIR": tmp, "TEMP": tmp, "TMP": tmp, "XDG_CONFIG_HOME": os.path.join(home, ".config"),
            "XDG_CACHE_HOME": os.path.join(home, ".cache"), "XDG_DATA_HOME": os.path.join(home, ".local", "share"),
            "XDG_STATE_HOME": os.path.join(home, ".local", "state"), "XDG_RUNTIME_DIR": os.path.join(work, "run")}
    for d in dirs.values():
        os.makedirs(d, mode=0o700, exist_ok=True)
    env.update(dirs)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def kill_group(p: subprocess.Popen) -> None:
    """SIGKILL the command's process group (the shell leads it), reap the shell, and wait briefly for the rest to go."""
    pgid = p.pid
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        p.wait()
        return
    p.wait()
    deadline = time.monotonic() + 1.0
    while group_running(pgid) and time.monotonic() < deadline:
        time.sleep(0.02)


def group_running(pgid: int) -> bool:
    """Whether a process of the group still runs. On Linux zombies do not count (an init that does not reap would
    otherwise keep the group alive); elsewhere, whether the group can still be signalled."""
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        pids = None
    if pids is None:
        try:
            os.killpg(pgid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False
    for pid in pids:
        try:
            with open(f"/proc/{pid}/stat", encoding="ascii", errors="replace") as f:
                fields = f.read().rsplit(")", 1)[1].split()
        except (OSError, IndexError):
            continue
        if len(fields) > 2 and fields[2] == str(pgid) and fields[0] not in ("Z", "X"):
            return True
    return False


def kill_marked(marker: str) -> None:
    """Best effort, Linux: kill any process that left the group (setsid) but still carries this run's marker."""
    needle = f"{RUN_MARKER}={marker}".encode()
    try:
        pids = [int(p) for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return
    for pid in pids:
        if pid == os.getpid():
            continue
        try:
            with open(f"/proc/{pid}/environ", "rb") as f:
                if needle in f.read().split(b"\0"):
                    os.kill(pid, signal.SIGKILL)
        except (OSError, ValueError):
            continue


def run_in_copy(root: str, command: str, timeout: int) -> tuple:
    """Run a command in a throwaway copy of the component; (exit code or None on timeout, seconds, last lines).

    Not a sandbox: see the module's docstring."""
    work = tempfile.mkdtemp(prefix="playground-")
    start = time.monotonic()
    code, out = None, ""
    try:
        copy = os.path.join(work, os.path.basename(os.path.abspath(root)))
        shutil.copytree(root, copy, symlinks=True, ignore=shutil.ignore_patterns(*SKIP_DIRS - {"dist"}))
        env = run_env(work)
        marker = secrets.token_hex(12)
        env[RUN_MARKER] = marker
        with tempfile.TemporaryFile(dir=work) as log:
            p = subprocess.Popen(["/bin/sh", "-c", command], cwd=copy, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                 start_new_session=True, close_fds=True)
            try:
                code = p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                code = None
            finally:
                kill_group(p)           # on the time limit, and after a clean exit: nothing it started outlives the check
                kill_marked(marker)
            size = log.seek(0, os.SEEK_END)
            log.seek(max(0, size - OUTPUT_TAIL_BYTES))
            out = log.read().decode("utf-8", "replace")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return code, round(time.monotonic() - start, 1), "\n".join(out.strip().splitlines()[-25:])


def check_runs(root: str, m: dict | None, timeout: int = 300) -> list:
    out = []
    if not m:
        return out
    if m.get("test"):
        code, secs, tail = run_in_copy(root, str(m["test"]), timeout)
        status = "pass" if code == 0 else "fail"
        why = "the tests pass" if code == 0 else ("the tests did not finish in time" if code is None else f"the tests fail (exit {code})")
        out.append(R("tests", "Tests green", "high", status, f"{why}: `{m['test']}` in {secs} s", [{"command": m["test"], "output": tail}],
                     "Every component proves itself with one command; fix the failures before asking for a sign-off.", {"seconds": secs}))
    ex = m.get("example") if isinstance(m.get("example"), dict) else {}
    if ex.get("run"):
        code, secs, tail = run_in_copy(root, str(ex["run"]), timeout)
        status = "pass" if code == 0 else "fail"
        why = "the live example runs" if code == 0 else ("the example did not finish in time" if code is None else f"the example fails (exit {code})")
        out.append(R("example", "The live example runs", "high", status, f"{why}: `{ex['run']}` in {secs} s", [{"command": ex["run"], "output": tail}],
                     "The live example is what both signers run; it must work from a clean copy.", {"seconds": secs}))
    return out


def check_agent(root: str, m: dict | None) -> list:
    if not m or m.get("category") != "agent" or not isinstance(m.get("agent"), dict):
        return []
    path = os.path.join(root, str(m["agent"].get("template", "")))
    rec = "An agent's template names its tools by tier and what it never does; money is refused on the platform."
    if not os.path.isfile(path):
        return [R("agent-template", "The agent's template", "high", "fail", f"the template {m['agent'].get('template')!r} does not exist", recommendation=rec)]
    with open(path, encoding="utf-8", errors="replace") as f:
        block = re.search(r"```json\s*(\{.*?\})\s*```", f.read(), re.S)
    try:
        tpl = json.loads(block.group(1)) if block else None
    except ValueError:
        tpl = None
    if not isinstance(tpl, dict):
        return [R("agent-template", "The agent's template", "high", "fail", "the template's first ```json block is missing or not JSON", recommendation=rec)]
    missing = [k for k in ("name", "role", "ladder", "stages", "tools", "never", "budget") if k not in tpl]
    out = []
    if missing:
        out.append(R("agent-template", "The agent's template", "high", "fail", "the template lacks: " + ", ".join(missing), recommendation=rec))
    else:
        out.append(R("agent-template", "The agent's template", "high", "pass", f"{len(tpl['tools'])} tool(s), {len(tpl['never'])} never line(s), a budget"))
    tools = tpl.get("tools") or []
    money = [t.get("op", t.get("name", "?")) for t in tools if isinstance(t, dict) and t.get("tier") == "MONEY"]
    badtier = [t.get("op", t.get("name", "?")) for t in tools if isinstance(t, dict) and t.get("tier") not in TIERS]
    if money:
        out.append(R("agent-money", "No money tool", "critical", "fail", f"the template lists money tools: {', '.join(money)}", recommendation=rec))
    elif badtier:
        out.append(R("agent-money", "Every tool has a tier", "high", "fail", f"tools without a tier (R, W1, W2): {', '.join(badtier)}", recommendation=rec))
    else:
        out.append(R("agent-money", "No money tool", "critical", "pass", "every tool has a tier and none moves money"))
    return out


def check(root: str, run: bool = True, timeout: int = 300) -> list:
    """Every contract check on the directory, in the order a reviewer reads them."""
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        return [R("manifest", "A manifest", "high", "error", f"not a directory: {root}")]
    m, manifest = check_manifest(root)
    results = [manifest, check_readme(root), check_signoffs(m), check_self_contained(root, m)]
    results += check_secrets(root)
    results.append(check_symlinks(root))
    results += check_agent(root, m)
    if run:
        results += check_runs(root, m, timeout)
    else:
        results.append(R("tests", "Tests green", "high", "skipped", "not run (--no-run)"))
    return results


def describe(root: str) -> dict:
    try:
        with open(os.path.join(root, "component.json"), encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError):
        m = {}
    if not isinstance(m, dict):
        m = {}
    return {"path": os.path.abspath(root), "name": m.get("name"), "version": m.get("version"), "category": m.get("category"), "owner": m.get("owner")}
