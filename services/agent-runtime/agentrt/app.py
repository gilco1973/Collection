"""The runtime's HTTP surface: the MCP transport from mcp-tool-server, plus a small run API and health.

    GET  /health                       anonymous: the wiring by name, the record's length and head (a count, never a walk)
    GET  /ready                        anonymous: 200 when the record verifies (walked at most once a minute) and the keys are reachable, else 503
    POST /mcp, GET /.well-known/...    the MCP server (the template's tools; W1 as elicitation; 403 on taint)
    POST /runs {ticket_key, service}   the agent's first read as one call: read, think, propose, park the write
    POST /runs/{session}/confirm {hash}   the person confirms the exact parked write; it runs once
    GET  /runs/{session}               the run's record so far (the person whose run it is)
Every route but /health and /ready carries the person's bearer. Logs are ids only, each line with the request id
the caller sent (or one minted here) so a report and a log line meet. Runs are rate-limited per person: the bearer
is resolved to the person it names, so a second token of the same person shares the bucket.
"""
from __future__ import annotations
import collections, hashlib, json, logging, threading, time
from http.server import ThreadingHTTPServer
from . import vendor  # noqa: F401
from .ops import RateLimiter, current_request_id, readiness, request_id
from actionloop import catalog as C
from actionloop.harness import Stop
from mcpserver.transports import make_http_handler

log = logging.getLogger("agentrt")
FORBIDDEN_STOPS = ("taint.forbids_tier", "ladder.violation")   # a confirmed write refused for good (403)
FINAL_STOPS = ("budget.", "kill.")                              # the run is over: the budget is spent or a switch is thrown (409, nothing to retry)
BAD_BODY = object()  # `_body` answered the request already (4xx); distinct from any JSON value a body can carry


def make_handler(w, resource: str, max_runs: int = 2000, socket_timeout_s: float = 30.0, verify_interval_s: float = 60.0):
    Base = make_http_handler(w.server, resource=resource, max_body_bytes=w.settings.max_body_bytes, socket_timeout_s=socket_timeout_s)
    runs: collections.OrderedDict[str, dict] = collections.OrderedDict()   # the newest max_runs; the record holds every run for good
    lock = threading.Lock()
    MAX_RUNS = max_runs
    limiter = RateLimiter(getattr(w.settings, "runs_per_minute", 0))
    verified = {"at": 0.0, "problem": None}
    verify_lock = threading.Lock()

    def record_verified():
        """The chain walked at most once per `verify_interval_s`, whoever asks: an anonymous readiness probe never
        holds the record's lock for a walk per call, and between walks the last result stands. The class names a
        failure, never the message."""
        with verify_lock:
            now = time.time()
            if verified["at"] and now - verified["at"] < verify_interval_s:
                return verified["problem"]
            try:
                w.audit.verify(); problem = None
            except Exception as e:  # noqa: BLE001
                problem = type(e).__name__
            verified.update(at=now, problem=problem)
            return problem

    def idp_ready():
        """The identity provider's keys are held and usable; a stale cache is refreshed at most once a minute (an
        anonymous readiness probe never becomes a fetch per call), and keys within their maximum age keep the task
        ready through a provider blip. The fake provider has none to fetch."""
        jwks = getattr(w.idp, "jwks", None)
        if jwks is None: return None
        jwks.refresh_if_due()
        if jwks.usable: return None
        return f"the identity provider's keys are unavailable ({jwks.last_error or 'no keys'})"

    def owner_of(sid: str, chain):
        """The resolved person, when it is the person the run belongs to; None otherwise."""
        if chain is None: return None
        j = w.harness.sessions.load_json(sid)
        return chain.human.id if j and j.get("chain", {}).get("human") == chain.human.id else None

    def repark(s, parked: dict) -> None:
        """The parked call back in the record with the hash the person saw, exactly as the harness parks it."""
        tier = C.lookup(w.harness.catalog, parked["tool"])["tier"]
        s.pending = {"tool": parked["tool"], "args": dict(parked["args"]), "tier": tier, "hash": parked["hash"]}
        w.harness.sessions.save(s)

    def rebuild(sid: str):
        """A run evicted from memory, rebuilt from the record: what the person may still confirm, or what became of
        it once it ended. None only when the record has no such session."""
        j = w.harness.sessions.load_json(sid)
        if not j: return None
        p, ended, posted = j.get("pending"), j.get("ended"), None
        if ended:
            # the write that ran: the chain's allowed W-tier decision with a result for this session (the chain
            # carries the result's summary, never its data)
            rows = w.conn.execute("SELECT body FROM audit WHERE event='decision' AND json_extract(body, '$.session') = ? ORDER BY seq", (sid,)).fetchall()
            for rec in (json.loads(r[0]) for r in rows):
                if rec.get("tier") != "R" and rec.get("decision") == "allow" and rec.get("result_summary") is not None:
                    posted = {"tool": rec.get("tool"), "seq": rec.get("seq"), "span_id": rec.get("span_id"), "from": "record"}
        return {"session": sid, "run_id": j.get("run_id"), "ticket_key": j.get("ticket_key"), "first_read": None, "proposal": None, "comment": None,
                "parked": {"hash": p["hash"], "tool": p["tool"], "args": dict(p["args"])} if p else None,
                "blocked": ended if ended and ended != "turn.complete" else None, "tainted": bool((j.get("taint") or {}).get("tainted")), "posted": posted, "ended": ended}

    class Handler(Base):
        """In flight is a request that arrived: the counter drain() waits on starts once the request line and headers
        parsed, never for a connection that is merely open (keep-alive idle, or a client that never sends)."""

        def handle_one_request(self):
            self._counted = False
            self._resolved = None   # the bearer is resolved once per request, not once per connection
            try:
                super().handle_one_request()
            finally:
                if self._counted:
                    with self.server.inflight_lock:
                        self.server.inflight -= 1

        def parse_request(self):
            ok = super().parse_request()
            if ok:
                request_id(self.headers.get("X-Request-Id"))
                with self.server.inflight_lock:
                    self.server.inflight += 1
                self._counted = True
            return ok

        def send_response(self, code, message=None):
            super().send_response(code, message)
            self.send_header("X-Request-Id", current_request_id())

        def _json(self, status, body, headers=None):
            raw = json.dumps(body).encode()
            self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw)))
            for k, v in (headers or {}).items(): self.send_header(k, v)
            self.end_headers(); self.wfile.write(raw)

        def _principal(self):
            """The bearer resolved once per request: (token, chain, problem), the chain None and the problem the
            exception's class name when the token is not one of this platform."""
            if getattr(self, "_resolved", None) is None:
                token, chain, problem = self._bearer() or "", None, None
                if token:
                    try:
                        chain = w.harness.identity.resolve(token, w.harness.consumer)
                    except Exception as e:  # noqa: BLE001 - not a token of this platform
                        problem = type(e).__name__
                self._resolved = (token, chain, problem)
            return self._resolved

        def _limited(self) -> bool:
            """One bucket per person: the bearer is resolved to the human it names, so a second token of the same
            person shares the bucket; a token that does not resolve gets a bucket by its hash (never logged).
            A 429 costs nothing downstream: no admit, no record."""
            token, chain, _ = self._principal()
            if not token: return False
            key = "person:" + chain.human.id if chain else "token:" + hashlib.sha256(token.encode()).hexdigest()[:16]
            wait = limiter.check(key)
            if wait:
                self._json(429, {"title": "Too many requests", "detail": "the limit is per person and per minute"}, {"Retry-After": str(int(wait))}); return True
            return False

        def _session(self):
            token, chain, problem = self._principal()
            if not token:
                self._json(401, {"title": "Unauthenticated"}, {"WWW-Authenticate": "Bearer"}); return None
            if chain is None:
                self._json(401, {"title": "Unauthenticated", "detail": problem}); return None
            try:
                return w.harness.admit(token, board="incidents", ticket_key=None, budget=__import__("agent").budget_from(w.template))
            except Exception as e:
                self._json(401, {"title": "Unauthenticated", "detail": type(e).__name__}); return None

        def do_GET(self):
            if self.path == "/health":
                # a count and the head, never a walk: an anonymous route costs one cheap statement under the record's lock
                n = w.conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
                return self._json(200, {"status": "ok", "agent": w.template["name"], "env": w.settings.env, "build": w.settings.build_sha, "identity": w.settings.identity, "signing": w.settings.signing,
                                        "engine": w.settings.engine, "targets": {t: type(c).__name__ for t, c in w.targets.items()}, "records": n, "head": w.audit.head()})
            if self.path == "/ready":
                ok, detail = readiness({"record": record_verified, "identity": idp_ready, "catalog": lambda: None if w.template.get("tools") else "no tools"})
                return self._json(200 if ok else 503, {"status": "ready" if ok else "not ready", "checks": detail})
            if self.path.startswith("/runs/"):
                sid = self.path.split("/")[2]
                token, chain, _ = self._principal()
                if not token: return self._json(401, {"title": "Unauthenticated"}, {"WWW-Authenticate": "Bearer"})
                if not owner_of(sid, chain): return self._json(404, {"title": "Not found"})  # not yours reads as not there
                with lock:
                    r = runs.get(sid)
                r = r or rebuild(sid)
                return self._json(200, r) if r else self._json(404, {"title": "Not found"})
            return super().do_GET()

        def _body(self):
            """The request's JSON object, or BAD_BODY once a 4xx was answered (or the client stopped sending)."""
            if self.headers.get("Transfer-Encoding"):
                self.close_connection = True
                self._json(411, {"title": "Length required", "detail": "send Content-Length, not Transfer-Encoding"}, {"Connection": "close"}); return BAD_BODY
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length < 0: raise ValueError(length)
            except ValueError:
                self.close_connection = True
                self._json(400, {"title": "Bad request", "detail": "Content-Length must be a non-negative integer"}, {"Connection": "close"}); return BAD_BODY
            if length > w.settings.max_body_bytes:
                remaining = min(length, 8 * w.settings.max_body_bytes)
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk: break
                    remaining -= len(chunk)
                self.close_connection = True
                self._json(413, {"title": "Body too large", "detail": f"at most {w.settings.max_body_bytes} bytes"}, {"Connection": "close"}); return BAD_BODY
            raw = self._read_body(length)
            if raw is None:
                return BAD_BODY  # the body never arrived in time: the connection is closed, nothing is answered
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                self._json(400, {"title": "Bad request", "detail": "the body is not JSON"}); return BAD_BODY
            if not isinstance(body, dict):
                self._json(400, {"title": "Bad request", "detail": "the body must be a JSON object"}); return BAD_BODY
            return body

        def do_POST(self):
            if self.path.startswith("/mcp") and self._limited(): return
            if self.path == "/runs":
                if self._limited(): return
                t0 = time.time(); body = self._body()
                if body is BAD_BODY: return
                s = self._session()
                if not s: return
                try:
                    r = w.agent.run(s, str(body.get("ticket_key", "")), str(body.get("service", "")))
                except Stop as e:
                    return self._json(409, {"title": "Stopped", "reason": e.reason, "detail": e.detail, "session": s.id, "run_id": s.run_id})
                except Exception as e:
                    log.warning("run failed session=%s error=%s", s.id, type(e).__name__)
                    return self._json(502, {"title": "The run failed", "detail": type(e).__name__, "session": s.id, "run_id": s.run_id})
                out = {"session": s.id, "run_id": s.run_id, "ticket_key": body.get("ticket_key"), "first_read": r["first_read"], "proposal": r["proposal"], "comment": r["comment"],
                       "parked": r["parked"], "blocked": r["blocked"], "tainted": r["tainted"], "posted": None, "ended": None}
                with lock:
                    runs[s.id] = out
                    while len(runs) > MAX_RUNS:
                        runs.popitem(last=False)
                log.info("run session=%s tainted=%s parked=%s blocked=%s ms=%d", s.id, r["tainted"], bool(r["parked"]), r["blocked"], int((time.time() - t0) * 1000))
                return self._json(200, out)
            if self.path.startswith("/runs/") and self.path.endswith("/confirm"):
                if self._limited(): return
                sid = self.path.split("/")[2]; body = self._body()
                if body is BAD_BODY: return
                token = self._bearer()
                if not token: return self._json(401, {"title": "Unauthenticated"}, {"WWW-Authenticate": "Bearer"})
                with lock:
                    r = runs.get(sid)
                if not r:
                    r = rebuild(sid)  # the record of truth outlives the in-memory map
                    if r:
                        with lock: runs[sid] = r
                if not r: return self._json(404, {"title": "Not found"})
                s = None
                try:
                    s = w.harness.resume(sid, token)
                    if not r["parked"] or body.get("hash") != r["parked"]["hash"]:
                        return self._json(409, {"title": "Nothing parked with that hash"})
                    posted = w.agent.post(s, s.chain.human.id, r["parked"])
                except Stop as e:
                    if e.reason in FORBIDDEN_STOPS:
                        return self._json(403, {"title": "Stopped", "reason": e.reason})
                    if s is not None and e.reason.startswith(FINAL_STOPS):
                        # the run is over: a spent budget or a thrown switch is not cured by confirming again; the
                        # session ends in the record and the parked call goes with it
                        w.harness.end(s, e.reason, e.detail)
                        with lock:
                            r["parked"] = None; r["blocked"] = e.reason; r["ended"] = e.reason
                        log.warning("confirm ended the run session=%s reason=%s", sid, e.reason)
                        return self._json(409, {"title": "Stopped", "reason": e.reason, "detail": "the run ended; nothing is parked any more"})
                    # the confirmation was consumed but the write did not happen (the handler failed): the same call
                    # is parked again in the record, so the person can confirm the same hash
                    repark(s, r["parked"])
                    log.warning("confirm did not post session=%s reason=%s; parked again", sid, e.reason)
                    return self._json(409, {"title": "Stopped", "reason": e.reason, "retry": True, "detail": "the write did not run; confirm the same hash again"})
                except Exception as e:
                    return self._json(409, {"title": "Not confirmed", "detail": type(e).__name__})
                with lock:
                    r["posted"] = posted.get("data"); r["parked"] = None; r["ended"] = "turn.complete"
                w.harness.end(s, "turn.complete")
                return self._json(200, r)
            return super().do_POST()

    return Handler


def serve(w, host: str, port: int, resource: str, max_runs: int = 2000, socket_timeout_s: float = 30.0, verify_interval_s: float = 60.0) -> ThreadingHTTPServer:
    """`socket_timeout_s`: a connection that sends nothing for that long is closed without an answer and holds no
    thread. `verify_interval_s`: how often at most `/ready` walks the chain."""
    httpd = ThreadingHTTPServer((host, port), make_handler(w, resource, max_runs, socket_timeout_s, verify_interval_s))
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
