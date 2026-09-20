"""The runtime's HTTP surface: the MCP transport from mcp-tool-server, plus a small run API and health.

    GET  /health                       anonymous
    POST /mcp, GET /.well-known/...    the MCP server (the template's tools; W1 as elicitation; 403 on taint)
    POST /runs {ticket_key, service}   the agent's first read as one call: read, think, propose, park the write
    POST /runs/{session}/confirm {hash}   the person confirms the exact parked write; it runs once
    GET  /runs/{session}               the run's record so far
Every route but /health carries the person's bearer. Logs are ids only.
"""
from __future__ import annotations
import json, logging, threading, time
from http.server import ThreadingHTTPServer
from . import vendor  # noqa: F401
from actionloop.harness import Stop
from mcpserver.transports import make_http_handler

log = logging.getLogger("agentrt")


def make_handler(w, resource: str):
    Base = make_http_handler(w.server, resource=resource)
    runs: dict[str, dict] = {}
    lock = threading.Lock()

    class Handler(Base):
        def _json(self, status, body, headers=None):
            raw = json.dumps(body).encode()
            self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw)))
            for k, v in (headers or {}).items(): self.send_header(k, v)
            self.end_headers(); self.wfile.write(raw)

        def _session(self):
            token = self._bearer()
            if not token:
                self._json(401, {"title": "Unauthenticated"}, {"WWW-Authenticate": "Bearer"}); return None
            try:
                return w.harness.admit(token, board="incidents", ticket_key=None, budget=__import__("agent").budget_from(w.template))
            except Exception as e:
                self._json(401, {"title": "Unauthenticated", "detail": type(e).__name__}); return None

        def do_GET(self):
            if self.path == "/health":
                return self._json(200, {"status": "ok", "agent": w.template["name"], "env": w.settings.env, "build": w.settings.build_sha, "identity": w.settings.identity, "signing": w.settings.signing,
                                        "engine": w.settings.engine, "targets": {t: type(c).__name__ for t, c in w.targets.items()}, "records": w.audit.verify()})
            if self.path.startswith("/runs/"):
                sid = self.path.split("/")[2]
                with lock:
                    r = runs.get(sid)
                return self._json(200, r) if r else self._json(404, {"title": "Not found"})
            return super().do_GET()

        def _body(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length > w.settings.max_body_bytes:
                self._json(413, {"title": "Body too large", "detail": f"at most {w.settings.max_body_bytes} bytes"}); return None
            try:
                return json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._json(400, {"title": "Bad request", "detail": "the body is not JSON"}); return None

        def do_POST(self):
            if self.path == "/runs":
                t0 = time.time(); body = self._body()
                if body is None: return
                s = self._session()
                if not s: return
                try:
                    r = w.agent.run(s, str(body.get("ticket_key", "")), str(body.get("service", "")))
                except Stop as e:
                    return self._json(409, {"title": "Stopped", "reason": e.reason, "detail": e.detail, "session": s.id})
                except Exception as e:
                    log.warning("run failed session=%s error=%s", s.id, type(e).__name__)
                    return self._json(502, {"title": "The run failed", "detail": type(e).__name__, "session": s.id})
                out = {"session": s.id, "ticket_key": body.get("ticket_key"), "first_read": r["first_read"], "proposal": r["proposal"], "comment": r["comment"], "parked": r["parked"], "blocked": r["blocked"], "tainted": r["tainted"], "posted": None}
                with lock:
                    runs[s.id] = out
                log.info("run session=%s tainted=%s parked=%s blocked=%s ms=%d", s.id, r["tainted"], bool(r["parked"]), r["blocked"], int((time.time() - t0) * 1000))
                return self._json(200, out)
            if self.path.startswith("/runs/") and self.path.endswith("/confirm"):
                sid = self.path.split("/")[2]; body = self._body()
                if body is None: return
                with lock:
                    r = runs.get(sid)
                if not r: return self._json(404, {"title": "Not found"})
                token = self._bearer()
                if not token: return self._json(401, {"title": "Unauthenticated"}, {"WWW-Authenticate": "Bearer"})
                try:
                    s = w.harness.resume(sid, token)
                    if not r["parked"] or body.get("hash") != r["parked"]["hash"]:
                        return self._json(409, {"title": "Nothing parked with that hash"})
                    posted = w.agent.post(s, s.chain.human.id, r["parked"])
                except Stop as e:
                    return self._json(403 if e.reason in ("taint.forbids_tier", "ladder.violation") else 409, {"title": "Stopped", "reason": e.reason})
                except Exception as e:
                    return self._json(409, {"title": "Not confirmed", "detail": type(e).__name__})
                with lock:
                    r["posted"] = posted.get("data"); r["parked"] = None
                w.harness.end(s, "turn.complete")
                return self._json(200, r)
            return super().do_POST()

    return Handler


def serve(w, host: str, port: int, resource: str) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), make_handler(w, resource))
    httpd.daemon_threads = True
    return httpd
