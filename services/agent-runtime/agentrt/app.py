"""The runtime's HTTP surface: the MCP transport from mcp-tool-server, plus a small run API and health.

    GET  /health                       anonymous: the wiring by name and the chain's length
    GET  /ready                        anonymous: 200 when the record verifies and the keys are reachable, else 503
    POST /mcp, GET /.well-known/...    the MCP server (the template's tools; W1 as elicitation; 403 on taint)
    POST /runs {ticket_key, service}   the agent's first read as one call: read, think, propose, park the write
    POST /runs/{session}/confirm {hash}   the person confirms the exact parked write; it runs once
    GET  /runs/{session}               the run's record so far (the person whose run it is)
Every route but /health and /ready carries the person's bearer. Logs are ids only, each line with the request id
the caller sent (or one minted here) so a report and a log line meet. Runs are rate-limited per person.
"""
from __future__ import annotations
import collections, hashlib, json, logging, threading, time
from http.server import ThreadingHTTPServer
from . import vendor  # noqa: F401
from .ops import RateLimiter, current_request_id, readiness, request_id
from actionloop.harness import Stop
from mcpserver.transports import make_http_handler

log = logging.getLogger("agentrt")


def make_handler(w, resource: str, max_runs: int = 2000):
    Base = make_http_handler(w.server, resource=resource, max_body_bytes=w.settings.max_body_bytes)
    runs: collections.OrderedDict[str, dict] = collections.OrderedDict()   # the newest max_runs; the record holds every run for good
    lock = threading.Lock()
    MAX_RUNS = max_runs
    limiter = RateLimiter(getattr(w.settings, "runs_per_minute", 0))

    def idp_ready():
        """The identity provider's keys are cached and fresh, or reachable now; the fake provider has none to fetch."""
        jwks = getattr(w.idp, "jwks", None)
        if jwks is None: return None
        if jwks._keys and time.time() - jwks._at < jwks.ttl: return None
        jwks._refresh()
        return None if jwks._keys else "the JWKS has no signing keys"

    def owner_of(sid: str, token: str | None):
        """The person the bearer resolves to, when it is the person the run belongs to; None otherwise."""
        if not token: return None
        try:
            chain = w.harness.identity.resolve(token, w.harness.consumer)
        except Exception:  # noqa: BLE001 - not a token of this platform
            return None
        j = w.harness.sessions.load_json(sid)
        return chain.human.id if j and j.get("chain", {}).get("human") == chain.human.id else None

    def rebuild(sid: str):
        """A run evicted from memory but still pending in the record: what the person may still confirm."""
        j = w.harness.sessions.load_json(sid)
        p = (j or {}).get("pending")
        if not p: return None
        return {"session": sid, "ticket_key": j.get("ticket_key"), "first_read": None, "proposal": None, "comment": None,
                "parked": {"hash": p["hash"], "tool": p["tool"], "args": dict(p["args"])}, "blocked": None, "tainted": bool((j.get("taint") or {}).get("tainted")), "posted": None}

    class Handler(Base):
        def handle(self):
            with self.server.inflight_lock:
                self.server.inflight += 1
            try:
                super().handle()
            finally:
                with self.server.inflight_lock:
                    self.server.inflight -= 1

        def parse_request(self):
            ok = super().parse_request()
            if ok: request_id(self.headers.get("X-Request-Id"))
            return ok

        def send_response(self, code, message=None):
            super().send_response(code, message)
            self.send_header("X-Request-Id", current_request_id())

        def _json(self, status, body, headers=None):
            raw = json.dumps(body).encode()
            self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw)))
            for k, v in (headers or {}).items(): self.send_header(k, v)
            self.end_headers(); self.wfile.write(raw)

        def _limited(self) -> bool:
            """One bucket per bearer (hashed, never logged); a 429 costs nothing downstream: no admit, no record."""
            token = self._bearer() or ""
            wait = limiter.check(hashlib.sha256(token.encode()).hexdigest()[:16]) if token else 0
            if wait:
                self._json(429, {"title": "Too many requests", "detail": "the limit is per person and per minute"}, {"Retry-After": str(int(wait))}); return True
            return False

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
            if self.path == "/ready":
                ok, detail = readiness({"record": w.audit.verify, "identity": idp_ready, "catalog": lambda: None if w.template.get("tools") else "no tools"})
                return self._json(200 if ok else 503, {"status": "ready" if ok else "not ready", "checks": detail})
            if self.path.startswith("/runs/"):
                sid = self.path.split("/")[2]
                if not self._bearer(): return self._json(401, {"title": "Unauthenticated"}, {"WWW-Authenticate": "Bearer"})
                if not owner_of(sid, self._bearer()): return self._json(404, {"title": "Not found"})  # not yours reads as not there
                with lock:
                    r = runs.get(sid)
                r = r or rebuild(sid)
                return self._json(200, r) if r else self._json(404, {"title": "Not found"})
            return super().do_GET()

        def _body(self):
            if self.headers.get("Transfer-Encoding"):
                self.close_connection = True
                self._json(411, {"title": "Length required", "detail": "send Content-Length, not Transfer-Encoding"}, {"Connection": "close"}); return None
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length < 0: raise ValueError(length)
            except ValueError:
                self.close_connection = True
                self._json(400, {"title": "Bad request", "detail": "Content-Length must be a non-negative integer"}, {"Connection": "close"}); return None
            if length > w.settings.max_body_bytes:
                remaining = min(length, 8 * w.settings.max_body_bytes)
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk: break
                    remaining -= len(chunk)
                self.close_connection = True
                self._json(413, {"title": "Body too large", "detail": f"at most {w.settings.max_body_bytes} bytes"}, {"Connection": "close"}); return None
            try:
                return json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._json(400, {"title": "Bad request", "detail": "the body is not JSON"}); return None

        def do_POST(self):
            if self.path.startswith("/mcp") and self._limited(): return
            if self.path == "/runs":
                if self._limited(): return
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
                    while len(runs) > MAX_RUNS:
                        runs.popitem(last=False)
                log.info("run session=%s tainted=%s parked=%s blocked=%s ms=%d", s.id, r["tainted"], bool(r["parked"]), r["blocked"], int((time.time() - t0) * 1000))
                return self._json(200, out)
            if self.path.startswith("/runs/") and self.path.endswith("/confirm"):
                if self._limited(): return
                sid = self.path.split("/")[2]; body = self._body()
                if body is None: return
                token = self._bearer()
                if not token: return self._json(401, {"title": "Unauthenticated"}, {"WWW-Authenticate": "Bearer"})
                with lock:
                    r = runs.get(sid)
                if not r:
                    r = rebuild(sid)  # the record of truth outlives the in-memory map
                    if r:
                        with lock: runs[sid] = r
                if not r: return self._json(404, {"title": "Not found"})
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


def serve(w, host: str, port: int, resource: str, max_runs: int = 2000) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), make_handler(w, resource, max_runs))
    httpd.daemon_threads = True
    httpd.inflight, httpd.inflight_lock = 0, threading.Lock()
    return httpd


def drain(httpd, timeout_s: float = 25.0, sleep=time.sleep) -> bool:
    """After `shutdown()`: waits for the requests still being handled (a run mid-flight finishes and is recorded);
    True when none remain, False when the timeout passed first."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        with httpd.inflight_lock:
            if httpd.inflight == 0: return True
        sleep(0.05)
    with httpd.inflight_lock:
        return httpd.inflight == 0
