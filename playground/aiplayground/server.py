"""The web interface: the same targets, runs and reports as the command line, in a browser.

    python3 -m aiplayground serve [--port 8765] [--data ~/.aiplayground]

It listens on loopback only and prints a link carrying a random token; every API call must present that token, and
the Host header must be the loopback address, so another page in the same browser (or a DNS-rebinding site) cannot
drive the playground at a solution. Runs happen on a worker thread; the page polls their progress.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import sys
import threading
import traceback
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from . import config as C
from . import probes as P
from . import report as Rp
from . import runner
from . import suites as S
from .store import Store
from .targets import open_target

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_BODY = 1_000_000
CSP = "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
REPORT_CSP = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"


class Jobs:
    """Runs in progress: id -> {state, done, total, label, report_id, error}."""

    def __init__(self):
        self.lock = threading.Lock()
        self.items: dict = {}

    def start(self, fn) -> str:
        jid = uuid.uuid4().hex[:12]
        with self.lock:
            self.items[jid] = {"id": jid, "state": "running", "done": 0, "total": 0, "label": "starting", "report_id": None, "error": None}

        def progress(done, total, label):
            with self.lock:
                self.items[jid].update(done=done, total=total, label=label)

        def work():
            try:
                rid = fn(progress)
                with self.lock:
                    self.items[jid].update(state="done", report_id=rid)
            except Exception as e:   # the page shows the error; the server keeps serving
                with self.lock:
                    self.items[jid].update(state="failed", error=f"{type(e).__name__}: {e}"[:400])
                traceback.print_exc(file=sys.stderr)

        threading.Thread(target=work, daemon=True).start()
        return jid

    def get(self, jid):
        with self.lock:
            return dict(self.items[jid]) if jid in self.items else None


def make_server(data_dir: str, port: int = 8765, host: str = "127.0.0.1", token: str | None = None, quiet: bool = False) -> ThreadingHTTPServer:
    store = Store(data_dir)
    jobs = Jobs()
    token = token or secrets.token_urlsafe(24)
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "ai-playground/" + __version__
        sys_version = ""

        def log_message(self, fmt, *args):
            if not quiet:   # method and path only: never the query, never a header
                sys.stderr.write("%s %s\n" % (self.command, self.path.split("?")[0]))

        # plumbing -------------------------------------------------------------------------------------------------
        def send(self, code, body: bytes, ctype: str, extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def json(self, code, payload):
            self.send(code, json.dumps(payload).encode("utf-8"), "application/json")

        def problem(self, code, message):
            self.json(code, {"error": message})

        def body(self):
            n = self.headers.get("Content-Length")
            if n is None or not n.isdigit():
                raise ValueError("Content-Length is required")
            if int(n) > MAX_BODY:
                raise OverflowError
            data = self.rfile.read(int(n))
            return json.loads(data or b"{}")

        def host_ok(self):
            server_port = self.server.server_address[1]
            return self.headers.get("Host", "") in allowed_hosts | {f"127.0.0.1:{server_port}", f"localhost:{server_port}"}

        def authed(self):
            given = self.headers.get("X-Playground-Token", "")
            return hmac.compare_digest(given.encode(), token.encode())

        # routes ---------------------------------------------------------------------------------------------------
        def do_GET(self):
            self.route("GET")

        def do_POST(self):
            self.route("POST")

        def do_DELETE(self):
            self.route("DELETE")

        def route(self, method):
            if not self.host_ok():
                return self.problem(421, "the playground answers on its loopback address only")
            path = urllib.parse.urlsplit(self.path).path
            if method == "GET" and path in ("/", "/index.html"):
                return self.static("index.html", "text/html; charset=utf-8")
            if method == "GET" and path in ("/app.js", "/app.css"):
                return self.static(path[1:], "text/javascript; charset=utf-8" if path.endswith(".js") else "text/css; charset=utf-8")
            if not path.startswith("/api/"):
                return self.problem(404, "not found")
            if not self.authed():
                return self.problem(401, "open the link the playground printed when it started (it carries the token)")
            if method == "POST" and self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self.problem(415, "send application/json")
            try:
                return self.api(method, path)
            except OverflowError:
                return self.problem(413, f"the request is larger than {MAX_BODY} bytes")
            except (C.ConfigError, S.SuiteError, ValueError) as e:
                return self.problem(422, str(e))
            except KeyError as e:
                return self.problem(404, f"not found: {e.args[0] if e.args else ''}")

        def static(self, name, ctype):
            with open(os.path.join(HERE, "static", name), "rb") as f:
                self.send(200, f.read(), ctype, {"Content-Security-Policy": CSP})

        def api(self, method, path):
            parts = path.strip("/").split("/")[1:]   # after "api"
            if parts == ["meta"] and method == "GET":
                return self.json(200, {"version": __version__, "presets": list(C.PRESETS), "kinds": list(C.KINDS), "environments": list(C.ENVIRONMENTS),
                                       "roles": list(runner.ROLES), "defaults": runner.DEFAULT_PROBES, "decisions": list(Rp.DECISIONS), "data": store.dir})
            if parts == ["probes"] and method == "GET":
                return self.json(200, P.catalog())
            if parts == ["targets"]:
                if method == "GET":
                    return self.json(200, store.targets())
                if method == "POST":
                    t = store.save_target(self.body())
                    return self.json(201, t.describe())
            if len(parts) == 2 and parts[0] == "targets":
                if method == "GET":
                    return self.json(200, store.raw_target(parts[1]))
                if method == "DELETE":
                    return self.json(200, {"deleted": store.delete_target(parts[1])})
            if len(parts) == 3 and parts[0] == "targets" and method == "POST":
                t = store.load_target(parts[1])
                if parts[2] == "ask":
                    b = self.body()
                    ad = open_target(t)
                    try:
                        r = ad.ask(str(b.get("prompt", "")), system=str(b.get("system", "")), context=str(b.get("context", "")))
                    finally:
                        ad.close()
                    return self.json(200, Rp.scrub(r.to_json(), C.secret_values(t)))
                if parts[2] == "tools":
                    ad = open_target(t)
                    try:
                        if not ad.tool_server:
                            return self.problem(422, f"{t.name} answers questions; it lists no tools")
                        return self.json(200, ad.tools())
                    except RuntimeError as e:
                        return self.problem(502, str(e))
                    finally:
                        ad.close()
                if parts[2] == "call":
                    b = self.body()
                    ad = open_target(t)
                    try:
                        if not ad.tool_server:
                            return self.problem(422, f"{t.name} answers questions; it has no tools to call")
                        args = b.get("arguments", {})
                        if not isinstance(args, dict):
                            return self.problem(422, "arguments is an object")
                        r = ad.call_tool(str(b.get("name", "")), args)
                    finally:
                        ad.close()
                    return self.json(200, Rp.scrub(r.to_json(), C.secret_values(t)))
            if parts == ["runs"]:
                if method == "GET":
                    return self.json(200, store.runs())
                if method == "POST":
                    return self.start_run(self.body())
            if len(parts) == 2 and parts == ["jobs", parts[1]] and method == "GET":
                j = jobs.get(parts[1])
                return self.json(200, j) if j else self.problem(404, "no such job")
            if len(parts) >= 2 and parts[0] == "runs":
                rep = store.run(parts[1])
                if rep is None:
                    return self.problem(404, "no such run")
                if len(parts) == 2 and method == "GET":
                    return self.json(200, rep)
                if len(parts) == 3 and parts[2] == "triage" and method == "POST":
                    b = self.body()
                    rep = store.triage(parts[1], str(b.get("result_id", "")), str(b.get("decision", "")), str(b.get("by", "")), str(b.get("reason", "")))
                    return self.json(200, rep)
                if len(parts) == 3 and parts[2] in ("report.html", "report.md", "report.json") and method == "GET":
                    kind = parts[2].split(".")[1]
                    if kind == "html":
                        return self.send(200, Rp.to_html(rep).encode("utf-8"), "text/html; charset=utf-8", {"Content-Security-Policy": REPORT_CSP})
                    if kind == "md":
                        return self.send(200, Rp.to_markdown(rep).encode("utf-8"), "text/markdown; charset=utf-8",
                                         {"Content-Disposition": f'attachment; filename="{rep["id"]}.md"'})
                    return self.send(200, json.dumps(rep, indent=2).encode("utf-8"), "application/json",
                                     {"Content-Disposition": f'attachment; filename="{rep["id"]}.json"'})
            if parts == ["compare"] and method == "GET":
                q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                a, b = store.run((q.get("a") or [""])[0]), store.run((q.get("b") or [""])[0])
                if not a or not b:
                    return self.problem(404, "name two runs: ?a=<id>&b=<id>")
                return self.json(200, {"before": {"id": a["id"], "verdict": a["verdict"]}, "after": {"id": b["id"], "verdict": b["verdict"]}, "changes": Rp.compare(a, b)})
            return self.problem(404 if method == "GET" else 405, "no such route")

        def start_run(self, b):
            name = b.get("target") or None
            comp = b.get("component") or None
            if not name and not comp:
                raise ValueError("name a target, a component directory, or both")
            t = store.load_target(name) if name else None
            if comp and not os.path.isdir(comp):
                raise ValueError(f"not a directory on this machine: {comp}")
            role = b.get("role") or "engineer"
            by = str(b.get("by") or "")
            if by and not Rp.PERSON.match(by):
                raise ValueError('the tester is "Name <address>"')
            suites = []
            for s in b.get("suites") or []:
                suites.append(S.load(s if isinstance(s, dict) else str(s)))
            probes = b.get("probes")
            if t is not None:
                P.select(runner.DEFAULT_PROBES[role] if probes is None else probes, t)   # an unknown probe is a 422 now, not a failed job later
            run_component = bool(b.get("run_component", True))

            def work(progress):
                rep = runner.run(t, probes=probes, suites=suites, component_dir=comp, run_component=run_component, by=by, role=role, progress=progress)
                store.add_run(rep)
                return rep["id"]

            return self.json(202, {"job": jobs.start(work)})

    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.token = token
    httpd.store = store
    return httpd


def main(port: int = 8765, data_dir: str | None = None, host: str = "127.0.0.1") -> int:
    if host not in ("127.0.0.1", "localhost", "::1"):
        print("serve: the playground listens on loopback only; reach it from elsewhere through an SSH tunnel", file=sys.stderr)
        return 3
    data_dir = data_dir or os.path.join(os.path.expanduser("~"), ".aiplayground")
    httpd = make_server(data_dir, port, host)
    real_port = httpd.server_address[1]
    print(f"AI Playground {__version__}: http://127.0.0.1:{real_port}/#token={httpd.token}", flush=True)
    print(f"data: {httpd.store.dir}   (Ctrl-C to stop)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
