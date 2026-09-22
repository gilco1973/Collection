"""The collection's contract, checked on a candidate component before anyone is asked to sign it.

CONTRIBUTING.md is the contract and `tools/shelf.py --check` enforces it inside the repository. This check runs
anywhere (a candidate in its own repository, a zip from another team) and reports in the playground's terms:
what is missing, what leaks, what does not run. It runs the component's own tests and example in a temporary copy,
with a minimal environment and a time limit, so a candidate's code never runs in its source tree or sees the
tester's credentials.
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

from .probes import Result

CATEGORIES = ("agent", "harness", "tool", "integration", "pattern", "skill")
LANGUAGES = ("python", "typescript", "markdown", "mixed")
STATUSES = ("ready", "draft", "deprecated")
README_HEADINGS = ("Five-minute start", "What is inside", "How to reuse it", "Rules it enforces", "Where it came from", "Known limits")
TIERS = ("R", "W1", "W2", "MONEY")
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
SKIP_DIRS = {"__pycache__", "node_modules", ".git", ".venv", "venv", "dist", ".pytest_cache", ".mypy_cache"}
SECRET_PATTERNS = [
    ("an AWS access key id", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("a private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("a GitHub token", re.compile(r"\b(ghp|gho|ghs|ghu)_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}")),
    ("a Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("an API key (sk- shape)", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{24,}")),
    ("a Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("a signed JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{16,}")),
    ("a password in code", re.compile(r"(?i)\b(password|passwd|secret|api_key|apikey|client_secret)\s*[:=]\s*[\"'](?![^\"']*(?:example|placeholder|changeme|your|xxx|\*\*\*|<|\$\{|test|dummy|fake))[^\"'\s]{10,}[\"']")),
]
GUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
URL = re.compile(r"https?://([A-Za-z0-9.-]+)")
PLACEHOLDER_HOST = re.compile(r"(^|\.)(example(\.[a-z]+)?|invalid|test|local|localhost|internal)$|^localhost$|^127\.0\.0\.1$|^0\.0\.0\.0$|^\[?::1\]?$", re.I)
# distribution name -> import name, for the common packages whose names differ
IMPORT_NAMES = {"pillow": "pil", "pyyaml": "yaml", "beautifulsoup4": "bs4", "scikit_learn": "sklearn", "python_dateutil": "dateutil",
                "opencv_python": "cv2", "pyjwt": "jwt", "python_dotenv": "dotenv", "protobuf": "google"}
GENERATED = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "Pipfile.lock"}
TEXT_EXT = (".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".json", ".md", ".txt", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".sh", ".env", ".html", ".css", "")


def placeholder_guid(g: str) -> bool:
    hexes = g.replace("-", "").lower()
    return len(set(hexes)) <= 2 or hexes in ("0123456789abcdef0123456789abcdef",) or re.fullmatch(r"(0+1?|1+|f+|a+|12345678.*)", hexes) is not None


def text_files(root: str):
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f in GENERATED:
                continue
            path = os.path.join(dirpath, f)
            if os.path.splitext(f)[1].lower() in TEXT_EXT and os.path.getsize(path) <= 1_000_000:
                yield path


def R(id, title, severity, status, summary, evidence=(), recommendation="", metrics=None) -> Result:
    return Result(f"contract/{id}", title, "CONTRACT", severity, status, summary, list(evidence), recommendation, "contract", metrics or {})


def taxonomy(start: str) -> list | None:
    """The knowledge base's tags, when the candidate sits in a checkout of the collection."""
    d = os.path.abspath(start)
    for _ in range(6):
        p = os.path.join(d, "tools", "kb-taxonomy.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f).get("tags")
        d = os.path.dirname(d)
    return None


def check_manifest(root: str) -> tuple:
    path = os.path.join(root, "component.json")
    rec = "Fill the manifest as CONTRIBUTING.md describes; python3 tools/new_component.py scaffolds a complete one."
    if not os.path.exists(path):
        return None, R("manifest", "A manifest", "high", "fail", "there is no component.json", recommendation=rec)
    try:
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
    except ValueError as e:
        return None, R("manifest", "A manifest", "high", "fail", f"component.json is not JSON: {e}", recommendation=rec)
    problems = []
    name = os.path.basename(os.path.abspath(root))
    if m.get("name") != name:
        problems.append(f"`name` is {m.get('name')!r}, the directory is {name!r}")
    if not SEMVER.match(str(m.get("version", ""))):
        problems.append("`version` is not a semantic version")
    if m.get("category") not in CATEGORIES:
        problems.append(f"`category` is one of {', '.join(CATEGORIES)}")
    if m.get("language") not in LANGUAGES:
        problems.append(f"`language` is one of {', '.join(LANGUAGES)}")
    if m.get("status") not in STATUSES:
        problems.append(f"`status` is one of {', '.join(STATUSES)}")
    if not isinstance(m.get("summary"), str) or not m["summary"] or len(m["summary"]) > 160 or "\n" in m["summary"]:
        problems.append("`summary` is one line of at most 160 characters")
    if not isinstance(m.get("owner"), str) or not m["owner"]:
        problems.append("`owner` names the person who answers questions (their handle)")
    src = m.get("source")
    if not isinstance(src, dict) or not all(k in src for k in ("project", "path", "snapshot")):
        problems.append("`source` is {project, path, snapshot}")
    if not isinstance(m.get("spec"), dict):
        problems.append("`spec` names the specification sections and the replacement test")
    if not isinstance(m.get("used_in", []), list):
        problems.append("`used_in` is a list of project names")
    if not isinstance(m.get("requires"), list):
        problems.append("`requires` lists runtime dependencies beyond the standard library (empty when none)")
    tags = m.get("tags")
    allowed = taxonomy(root)
    if not isinstance(tags, list) or not tags:
        problems.append("`tags` lists at least one tag from the knowledge base's taxonomy")
    elif allowed is not None and set(tags) - set(allowed):
        problems.append(f"tags not in the taxonomy: {', '.join(sorted(set(tags) - set(allowed)))}")
    if m.get("language") != "markdown" and not m.get("test"):
        problems.append("`test` is the command that proves it works")
    wt = m.get("walkthrough")
    if not wt or not os.path.exists(os.path.join(root, str(wt))):
        problems.append("`walkthrough` names a WALKTHROUGH.md that exists")
    ex = m.get("example")
    if not isinstance(ex, dict) or not ex.get("path") or not os.path.exists(os.path.join(root, str(ex.get("path")))):
        problems.append("`example` is {path, run} and the path exists")
    so = m.get("signoff")
    if not isinstance(so, dict) or set(so) != {"owner", "ai_security"}:
        problems.append("`signoff` is {owner, ai_security}")
    if m.get("category") == "agent" and not isinstance(m.get("agent"), dict):
        problems.append("an agent names `agent`: {template, tools, harness}")
    if problems:
        return m, R("manifest", "A complete manifest", "high", "fail", f"{len(problems)} problem(s) in component.json: " + "; ".join(problems[:6]),
                    [{"problems": problems}], rec)
    return m, R("manifest", "A complete manifest", "high", "pass", f"component.json is complete: {m['name']} {m['version']}, {m['category']}, {m['status']}")


def check_readme(root: str) -> Result:
    path = os.path.join(root, "README.md")
    rec = "Use components/_template/README.md: every heading, and a five-minute start that runs as written."
    if not os.path.exists(path):
        return R("readme", "A README in the template's shape", "medium", "fail", "there is no README.md", recommendation=rec)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    heads = [h.strip().lower() for h in re.findall(r"^##\s+(.+)$", text, re.M)]
    missing = [h for h in README_HEADINGS if not any(x.startswith(h.lower()) for x in heads)]
    lead = re.sub(r"^#[^\n]*\n", "", text.lstrip()).split("\n## ")[0].strip()
    if "what it is for" not in heads and not lead:
        missing.insert(0, "What it is for (or a lead paragraph)")
    if missing:
        return R("readme", "A README in the template's shape", "medium", "fail", "the README lacks: " + ", ".join(missing), recommendation=rec)
    return R("readme", "A README in the template's shape", "medium", "pass", "every heading of the template is there")


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


def check_self_contained(root: str, m: dict | None) -> Result:
    rec = "Import only the standard library, the component's own files, and what `requires` declares; vendor shared files with `vendored`."
    requires = set()
    for r in (m or {}).get("requires", []) if isinstance((m or {}).get("requires"), list) else []:
        if isinstance(r, str) and r.strip():
            dist = re.split(r"[<>=\[ (;]", r.strip())[0].lower().replace("-", "_")
            requires |= {dist, IMPORT_NAMES.get(dist, dist)}
    local = set()
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        local |= {d for d in dirs} | {os.path.splitext(f)[0] for f in files if f.endswith(".py")}
    stdlib = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}
    outside, parse_errors = [], []
    for path in text_files(root):
        rel = os.path.relpath(path, root)
        if path.endswith(".py"):
            try:
                with open(path, encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=rel)
            except (SyntaxError, UnicodeDecodeError) as e:
                parse_errors.append(f"{rel}: {e.__class__.__name__}")
                continue
            optional = set()
            for t in ast.walk(tree):
                if isinstance(t, ast.Try) and any(isinstance(h.type, ast.Name) and h.type.id in ("ImportError", "ModuleNotFoundError") or
                                                  isinstance(h.type, ast.Tuple) and any(getattr(e, "id", "") in ("ImportError", "ModuleNotFoundError") for e in h.type.elts)
                                                  for h in t.handlers):
                    optional |= {id(n) for b in t.body for n in ast.walk(b)}
            for node in ast.walk(tree):
                if id(node) in optional:
                    continue
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        base = os.path.dirname(path)
                        for _ in range(node.level - 1):
                            base = os.path.dirname(base)
                        if os.path.commonpath([base, root]) != root:
                            outside.append(f"{rel}: from {'.' * node.level}{node.module or ''} reaches outside the component")
                        continue
                    names = [(node.module or "").split(".")[0]]
                else:
                    if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in ("insert", "append") and "sys.path" in ast.unparse(node.func) and ".." in ast.unparse(node):
                        outside.append(f"{rel}: adds a parent directory to sys.path")
                    continue
                for n in names:
                    if n and n not in stdlib and n not in local and n.lower() not in requires:
                        outside.append(f"{rel}: imports {n}")
        elif path.endswith((".ts", ".tsx", ".js", ".mjs")):
            with open(path, encoding="utf-8", errors="replace") as f:
                for spec in re.findall(r"""(?:from|import|require\()\s*["'](\.\./[^"']+)["']""", f.read()):
                    target = os.path.normpath(os.path.join(os.path.dirname(path), spec))
                    if not target.startswith(os.path.abspath(root)):
                        outside.append(f"{rel}: imports {spec}")
    if parse_errors:
        outside += [f"cannot parse {p}" for p in parse_errors]
    if outside:
        uniq = sorted(set(outside))
        return R("self-contained", "Self-contained", "high", "fail", f"{len(uniq)} import(s) outside the standard library, the component and `requires`: " + "; ".join(uniq[:5]),
                 [{"imports": uniq[:50]}], rec)
    return R("self-contained", "Self-contained", "high", "pass", "imports only the standard library, its own files and what `requires` declares")


def check_secrets(root: str) -> list:
    hits, guids, urls = [], [], {}
    for path in text_files(root):
        rel = os.path.relpath(path, root)
        with open(path, encoding="utf-8", errors="replace") as f:
            for no, line in enumerate(f, 1):
                for what, rx in SECRET_PATTERNS:
                    if rx.search(line):
                        hits.append(f"{rel}:{no}: {what}")
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


def run_in_copy(root: str, command: str, timeout: int) -> tuple:
    """Run a command in a throwaway copy of the component; (exit code or None on timeout, seconds, last lines)."""
    from .targets import child_env
    work = tempfile.mkdtemp(prefix="playground-")
    copy = os.path.join(work, os.path.basename(os.path.abspath(root)))
    shutil.copytree(root, copy, ignore=shutil.ignore_patterns(*SKIP_DIRS - {"dist"}))
    start = time.monotonic()
    try:
        p = subprocess.run(["/bin/sh", "-c", command], cwd=copy, capture_output=True, timeout=timeout, env={**child_env([]), "TMPDIR": work})
        code, out = p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired as e:
        code, out = None, ((e.stdout or b"") + (e.stderr or b"")).decode("utf-8", "replace")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return code, round(time.monotonic() - start, 1), "\n".join(out.strip().splitlines()[-25:])


def check_runs(root: str, m: dict | None, timeout: int = 300) -> list:
    out = []
    if not m:
        return out
    if m.get("test"):
        code, secs, tail = run_in_copy(root, m["test"], timeout)
        status = "pass" if code == 0 else "fail"
        why = "the tests pass" if code == 0 else ("the tests did not finish in time" if code is None else f"the tests fail (exit {code})")
        out.append(R("tests", "Tests green", "high", status, f"{why}: `{m['test']}` in {secs} s", [{"command": m["test"], "output": tail}],
                     "Every component proves itself with one command; fix the failures before asking for a sign-off.", {"seconds": secs}))
    ex = m.get("example") if isinstance(m.get("example"), dict) else {}
    if ex.get("run"):
        code, secs, tail = run_in_copy(root, ex["run"], timeout)
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
    if not os.path.exists(path):
        return [R("agent-template", "The agent's template", "high", "fail", f"the template {m['agent'].get('template')!r} does not exist", recommendation=rec)]
    with open(path, encoding="utf-8") as f:
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
    return {"path": os.path.abspath(root), "name": m.get("name"), "version": m.get("version"), "category": m.get("category"), "owner": m.get("owner")}
