"""A read-only MCP server over the shelf: a coding assistant discovers the collection without cloning it.

Tools: shelf_list (by category), shelf_get (the manifest with its stage and sign-off state), shelf_search (a word
in names, summaries and tags), shelf_stage (where a component is on its way to the shelf). Resources: every
component's README, walkthrough, template and SKILL.md as `shelf://<name>/<file>`. Nothing here runs, writes or
signs anything: the manifests in the repository stay the record and the hub and the shelf tool do the writing.

    python3 server.py --root <path to the repository>      # newline-delimited JSON-RPC on stdin/stdout
"""
from __future__ import annotations
import argparse, json, os, re, sys
import protocol as P

SERVER = {"name": "shelf", "version": "1.0.0"}
FILES = ("README.md", "WALKTHROUGH.md", "TEMPLATE.md", "SKILL.md", "component.json")
CATEGORIES = ("agent", "harness", "tool", "integration", "pattern", "skill")
STAGES = ("scaffolded", "built", "used once for real", "owner signed", "AI security signed", "on the shelf")
SKIP = ("node_modules", "__pycache__", "_template", ".git")


def find_root(start: str | None) -> str:
    """The repository: the nearest ancestor with a components/ directory (or the path given)."""
    d = os.path.abspath(start or os.path.dirname(__file__))
    while True:
        if os.path.isdir(os.path.join(d, "components")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            raise SystemExit("no components/ directory above " + (start or __file__))
        d = parent


def stage_of(m: dict) -> dict:
    """The same rule as the shelf tool's: read from the manifest, never guessed."""
    so, v = m.get("signoff") or {}, m.get("version")
    signed = lambda r: bool(so.get(r)) and so[r].get("version") == v
    if m.get("status") == "deprecated": return {"index": 6, "label": "deprecated"}
    if m.get("status") == "draft": return {"index": 0, "label": STAGES[0]}
    if not m.get("used_in"): return {"index": 1, "label": STAGES[1]}
    if not signed("owner"): return {"index": 2, "label": STAGES[2]}
    if not signed("ai_security"): return {"index": 3, "label": STAGES[3]}
    return {"index": 5, "label": STAGES[5]}


class Shelf:
    def __init__(self, root: str):
        self.root = root
        self.components: dict[str, dict] = {}
        base = os.path.join(root, "components")
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP]
            if "component.json" in filenames:
                try:
                    m = json.load(open(os.path.join(dirpath, "component.json"), encoding="utf-8"))
                except ValueError:
                    continue
                m["_dir"] = dirpath
                self.components[m["name"]] = m

    def record(self, m: dict) -> dict:
        so = m.get("signoff") or {}
        return {"name": m["name"], "category": m.get("category"), "language": m.get("language"), "version": m.get("version"), "status": m.get("status"),
                "summary": m.get("summary"), "owner": m.get("owner"), "tags": m.get("tags", []), "stage": stage_of(m),
                "signoff": {r: (so.get(r) or None) for r in ("owner", "ai_security")}, "used_in": m.get("used_in", []),
                "pairs_with": m.get("pairs_with", []), "test": m.get("test"), "example": m.get("example"), "walkthrough": m.get("walkthrough"),
                "agent": m.get("agent"), "spec": m.get("spec"), "path": os.path.relpath(m["_dir"], self.root),
                "resources": [f"shelf://{m['name']}/{f}" for f in FILES if os.path.exists(os.path.join(m["_dir"], f))]}

    def get(self, name: str) -> dict:
        m = self.components.get(name)
        if not m:
            raise P.RpcError(P.INVALID_PARAMS, f"no component named {name!r}")
        return self.record(m)

    def list(self, category: str | None = None) -> list[dict]:
        if category and category not in CATEGORIES:
            raise P.RpcError(P.INVALID_PARAMS, f"category must be one of {CATEGORIES}")
        ms = [m for m in self.components.values() if not category or m.get("category") == category]
        ms.sort(key=lambda m: (CATEGORIES.index(m.get("category", "tool")) if m.get("category") in CATEGORIES else 9, m["name"]))
        return [{k: r[k] for k in ("name", "category", "language", "version", "status", "summary", "stage", "tags")} for r in map(self.record, ms)]

    def search(self, q: str) -> list[dict]:
        words = [w for w in re.split(r"\W+", q.lower()) if w]
        if not words:
            raise P.RpcError(P.INVALID_PARAMS, "q must contain a word")
        hits = []
        for m in self.components.values():
            hay = f"{m['name']} {m.get('summary', '')} {' '.join(m.get('tags', []))} {m.get('category', '')}".lower()
            score = sum(1 for w in words if w in hay)
            if score:
                hits.append((score, m["name"]))
        return [self.list_one(n) for _, n in sorted(hits, key=lambda x: (-x[0], x[1]))]

    def list_one(self, name: str) -> dict:
        r = self.record(self.components[name])
        return {k: r[k] for k in ("name", "category", "language", "version", "status", "summary", "stage", "tags")}

    def resources(self) -> list[dict]:
        out = []
        for m in self.components.values():
            for f in FILES:
                if os.path.exists(os.path.join(m["_dir"], f)):
                    out.append({"uri": f"shelf://{m['name']}/{f}", "name": f"{m['name']}/{f}", "title": f"{m['name']} · {f}",
                                "mimeType": "application/json" if f.endswith(".json") else "text/markdown"})
        return out

    def read(self, uri: str) -> dict:
        mt = re.fullmatch(r"shelf://([a-z0-9-]+)/([A-Za-z_.]+)", uri or "")
        if not mt or mt.group(2) not in FILES or mt.group(1) not in self.components:
            raise P.RpcError(P.INVALID_PARAMS, f"no resource {uri!r}: shelf://<component>/<{'|'.join(FILES)}>")
        path = os.path.join(self.components[mt.group(1)]["_dir"], mt.group(2))
        if not os.path.exists(path):
            raise P.RpcError(P.INVALID_PARAMS, f"{mt.group(1)} has no {mt.group(2)}")
        text = open(path, encoding="utf-8").read()
        return {"contents": [{"uri": uri, "mimeType": "application/json" if path.endswith(".json") else "text/markdown", "text": text}]}


TOOLS = [
    {"name": "shelf_list", "title": "List the shelf", "description": "Every component of the collection, or those of one category (agent, harness, tool, integration, pattern, skill), with version, status, stage and tags.",
     "inputSchema": {"type": "object", "properties": {"category": {"type": "string", "enum": list(CATEGORIES)}}, "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}},
    {"name": "shelf_get", "title": "One component", "description": "A component's manifest as the shelf reads it: version, both sign-offs, stage, what it pairs with, its test and example commands, its agent parts if any, and the resource URIs of its README, walkthrough and template.",
     "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}},
    {"name": "shelf_search", "title": "Search the shelf", "description": "Components whose name, summary, tags or category contain the words given, best match first.",
     "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"], "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}},
    {"name": "shelf_stage", "title": "Where a component is", "description": "The component's stage on its way to the shelf (scaffolded, built, used once for real, owner signed, AI security signed, on the shelf) and its sign-off state.",
     "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}},
]


class ShelfServer:
    def __init__(self, shelf: Shelf):
        self.shelf, self.initialized = shelf, False

    def handle(self, msg: dict) -> dict | None:
        method, params, mid = msg.get("method"), msg.get("params") or {}, msg.get("id")
        try:
            if not isinstance(params, dict):
                raise P.RpcError(P.INVALID_REQUEST, "params must be an object")
            if P.is_notification(msg):
                if method == "notifications/initialized":
                    self.initialized = True
                return None
            if method == "initialize":
                return P.result(mid, {"protocolVersion": P.PROTOCOL_VERSION, "capabilities": {"tools": {"listChanged": False}, "resources": {"subscribe": False, "listChanged": False}},
                                      "serverInfo": SERVER, "instructions": "Read-only. The shelf is the collection's components; copy one from its path, run its test, sign it off on the hub."})
            if method == "ping":
                return P.result(mid, {})
            if method == "tools/list":
                return P.result(mid, {"tools": TOOLS})
            if method == "tools/call":
                args = params.get("arguments") or {}
                if not isinstance(args, dict):
                    raise P.RpcError(P.INVALID_PARAMS, "arguments must be an object")
                return P.result(mid, self.call(params.get("name"), args))
            if method == "resources/list":
                return P.result(mid, {"resources": self.shelf.resources()})
            if method == "resources/read":
                return P.result(mid, self.shelf.read(params.get("uri")))
            raise P.RpcError(P.METHOD_NOT_FOUND, f"method not found: {method}")
        except P.RpcError as e:
            return P.error(mid, e)
        except Exception as e:  # noqa: BLE001 - a defect answers as an error, by class; the server keeps serving
            return P.error(mid, P.RpcError(P.INTERNAL_ERROR, f"internal error: {type(e).__name__}"))

    def call(self, name: str | None, args: dict) -> dict:
        for k, v in args.items():
            if v is not None and not isinstance(v, str):
                raise P.RpcError(P.INVALID_PARAMS, f"argument {k} must be a string")
        if name == "shelf_list": data = self.shelf.list(args.get("category"))
        elif name == "shelf_get": data = self.shelf.get(str(args.get("name", "")))
        elif name == "shelf_search": data = self.shelf.search(str(args.get("q", "")))
        elif name == "shelf_stage":
            r = self.shelf.get(str(args.get("name", ""))); data = {"name": r["name"], "version": r["version"], "stage": r["stage"], "signoff": r["signoff"], "used_in": r["used_in"]}
        else:
            raise P.RpcError(P.INVALID_PARAMS, f"unknown tool {name!r}")
        return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, indent=1)}], "structuredContent": data if isinstance(data, dict) else {"items": data}, "isError": False}


MAX_LINE_BYTES = 1_000_000


def serve_stdio(server: ShelfServer, inp=None, out=None) -> None:
    """One JSON-RPC message per line. Bytes are read and decoded with replacement (a bad byte is a parse error, not
    the end of the server); a line above MAX_LINE_BYTES is drained and refused."""
    inp, out = inp or sys.stdin, out or sys.stdout
    raw = getattr(inp, "buffer", inp)
    while True:
        line = raw.readline(MAX_LINE_BYTES + 1)
        if not line:
            break
        if isinstance(line, bytes):
            too_long = len(line) > MAX_LINE_BYTES
            while too_long and not line.endswith(b"\n"):
                more = raw.readline(MAX_LINE_BYTES)
                if not more: break
                line = line[-1:] + more[-1:]  # drain; keep only the tail to see the newline
            line = "<line too long>" if too_long else line.decode("utf-8", "replace")  # the tail that was kept may be blank: the answer does not depend on it
        else:
            too_long = len(line) > MAX_LINE_BYTES
        if too_long:  # before the blank-line skip: a refused line is always answered
            out.write(P.dumps(P.error(None, P.RpcError(P.PARSE_ERROR, f"line above {MAX_LINE_BYTES} bytes"))) + "\n"); out.flush(); continue
        if not line.strip():
            continue
        try:
            msg = P.parse(line)
        except P.RpcError as e:
            out.write(P.dumps(P.error(None, e)) + "\n"); out.flush(); continue
        if P.is_response(msg):
            continue
        res = server.handle(msg)
        if res is not None:
            out.write(P.dumps(res) + "\n"); out.flush()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", help="the repository (default: found above this file)")
    a = ap.parse_args(argv)
    serve_stdio(ShelfServer(Shelf(find_root(a.root))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
