"""The HTTP application: the hub's contract on the standard library's server.

Every route is authenticated (bearer -> principal) except /health. Errors are RFC 9457 problems. Mutations with
an Idempotency-Key replay the first response for the same person. Writes to a brief carry If-Match. Turns stream
as `event: view` server-sent events. Logs carry ids only. The built hub is served from `static_dir` with an SPA
fallback so one process is the whole deployable.
"""
from __future__ import annotations
import json, logging, mimetypes, os, re, threading, time, urllib.parse, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from . import briefs as B
from .auth import AuthError, bearer
from .catalog import Catalog
from .store import Store

log = logging.getLogger("hubapi")


class Problem(Exception):
    def __init__(self, status: int, title: str, detail: str = "", code: str | None = None, errors: dict | None = None):
        super().__init__(title)
        self.status, self.title, self.detail, self.code, self.errors = status, title, detail, code, errors

    def to_json(self) -> dict:
        d = {"status": self.status, "title": self.title}
        if self.detail: d["detail"] = self.detail
        if self.code: d["code"] = self.code
        if self.errors: d["errors"] = self.errors
        return d


class Stream:
    """An SSE response: `events` yields dicts; `done(views)` is called with what was sent, for the record."""

    def __init__(self, events, done=None):
        self.events, self.done = events, done


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class HubApi:
    def __init__(self, settings, store: Store, catalog: Catalog, auth, assistant):
        self.s, self.store, self.catalog, self.auth, self.assistant = settings, store, catalog, auth, assistant
        self.routes: list[tuple[str, re.Pattern, list, callable, bool]] = []
        self.seq_lock = threading.Lock(); self.seq = 100
        self._register()

    def route(self, method: str, path: str, handler, anonymous: bool = False):
        keys: list[str] = []
        pattern = re.compile("^" + re.sub(r":(\w+)", lambda m: (keys.append(m.group(1)), "([^/]+)")[1], path) + "$")
        self.routes.append((method, pattern, keys, handler, anonymous))

    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    # ---------------- dispatch ----------------
    def handle(self, method: str, path: str, headers, body: bytes):
        """Returns (status, headers, body_bytes) or a Stream. Raises nothing: every error is a problem."""
        query = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
        path = urllib.parse.urlparse(path).path
        match = next(((p, k, h, a) for m, p, k, h, a in self.routes if m == method and p.match(path)), None)
        if not match:
            return self.problem(Problem(404, "Not found", f"No route {method} {path}"))
        pattern, keys, handler, anonymous = match
        principal = None
        if not anonymous:
            token = bearer(headers)
            if not token:
                return self.problem(Problem(401, "Unauthenticated", code="unauthenticated"), {"WWW-Authenticate": "Bearer"})
            try:
                principal = self.auth.principal(token)
            except AuthError as e:
                return self.problem(Problem(e.status, e.title, e.detail, e.code), {"WWW-Authenticate": "Bearer"})
        key = headers.get("Idempotency-Key")
        if key and principal:
            hit = self.store.replay(key, principal.id)
            if hit:
                return hit[0], {"Content-Type": hit[1], "Idempotent-Replayed": "true"}, hit[2]
        m = pattern.match(path)
        params = {k: urllib.parse.unquote(m.group(i + 1)) for i, k in enumerate(keys)}
        try:
            data = json.loads(body.decode("utf-8")) if body else None
        except ValueError:
            return self.problem(Problem(400, "Bad request", "the body is not JSON"))
        ctx = {"principal": principal, "params": params, "query": {k: v[0] for k, v in query.items()}, "body": data, "headers": headers}
        try:
            res = handler(ctx)
        except Problem as p:
            return self.problem(p)
        if isinstance(res, Stream):
            return res
        status, payload = res if isinstance(res, tuple) else (200, res)
        raw = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        ctype = "application/json"
        if key and principal and status < 500:
            self.store.remember(key, principal.id, status, ctype, raw)
        return status, {"Content-Type": ctype}, raw

    @staticmethod
    def problem(p: Problem, extra: dict | None = None):
        return p.status, {"Content-Type": "application/problem+json", **(extra or {})}, json.dumps(p.to_json()).encode("utf-8")

    # ---------------- routes ----------------
    def _register(self):
        r = self.route
        r("GET", "/health", self.health, anonymous=True)
        r("GET", "/me", lambda c: {**c["principal"].to_json(), "preferences": self.store.get("prefs", c["principal"].id) or c["principal"].preferences})
        r("PUT", "/me/preferences", self.put_prefs)
        r("GET", "/catalog", lambda c: self.catalog.catalog_for(c["principal"]))
        r("GET", "/catalog/search", lambda c: self.catalog.search(c["principal"], c["query"].get("q", "")))
        r("GET", "/consumers/:slug", self.consumer)
        r("GET", "/me/requests", lambda c: self.store.list("request", c["principal"].id))
        r("POST", "/me/requests", self.create_request)
        r("GET", "/me/workspace", self.workspace)
        r("POST", "/me/playground/rotate", lambda c: {"keyMasked": "crai_pg_…" + uuid.uuid4().hex[:4]})
        r("GET", "/registry/systems", lambda c: self.catalog.c.get("registrySystems", []))
        r("GET", "/registry/tools", lambda c: self.catalog.c.get("registryTools", []))
        r("GET", "/briefs", self.list_briefs)
        r("POST", "/briefs", lambda c: (201, self.store.put("brief", *self._new_brief(c["principal"]))))
        r("GET", "/briefs/:id", lambda c: self.load_brief(c))
        r("PATCH", "/briefs/:id", self.patch_brief)
        r("POST", "/briefs/:id/estimate", lambda c: B.estimate(self.catalog.c.get("estimate", {}), c["body"] or {}))
        r("POST", "/briefs/:id/road", lambda c: B.road(self.catalog.c.get("roadR2Read", {}), c["body"] or {}))
        r("POST", "/briefs/:id/file", self.file_brief)
        r("GET", "/conversations", self.list_conversations)
        r("GET", "/conversations/:id", lambda c: self.load_conversation(c))
        r("POST", "/conversations", self.create_conversation)
        r("POST", "/conversations/:id/turns", self.turn)
        r("POST", "/conversations/:id/feedback", self.feedback)
        r("POST", "/conversations/:id/handoff", lambda c: {"route": "human", "expected_wait_s": 240})
        r("GET", "/shelf", lambda c: [self.catalog.shelf_entry(x, c["principal"], self.store.list("signoff")) for x in self.catalog.shelf])
        r("GET", "/shelf/signoffs/export", lambda c: {"generatedAt": now_iso(), "apply": "python3 tools/shelf.py --apply-signoffs shelf-signoffs.json", "signoffs": self.store.list("signoff")})
        r("GET", "/shelf/:name", self.shelf_get)
        r("POST", "/shelf/:name/signoffs", self.sign)

    def health(self, c):
        return {"status": "ok", "build": self.s.build_sha, "env": self.s.env, "auth": self.s.auth, "assistant": self.assistant.name, "components": len(self.catalog.shelf), "record": "file" if self.s.db_path != ":memory:" else "memory"}

    def put_prefs(self, c):
        p = c["body"]
        if not isinstance(p, dict): raise Problem(422, "Not valid", "preferences must be an object", "validation")
        self.store.put("prefs", c["principal"].id, p, c["principal"].id)
        return {**c["principal"].to_json(), "preferences": p}

    def consumer(self, c):
        d = self.catalog.consumer(c["params"]["slug"], c["principal"])
        if not d: raise Problem(404, "Not found", "No listing with that name.")
        return d

    def create_request(self, c):
        b, p = c["body"] or {}, c["principal"]
        kind = b.get("kind")
        if kind not in ("access", "ladder", "role"): raise Problem(422, "Not valid", "kind must be access, ladder or role", "validation")
        listing = next((l for l in self.catalog.all if l["id"] == b.get("consumerId")), None)
        ladders = ["L0", "L1", "L2", "L3"]
        if kind == "ladder" and b.get("ladder") in ladders and ladders.index(b["ladder"]) > ladders.index(p.ladder):
            raise Problem(403, "Above your ceiling", f"Your own ladder is {p.ladder}; ask your lead to raise it first.", "ladder.above")
        name = listing["name"] if listing else b.get("consumerId", "")
        req = {"id": "req_" + uuid.uuid4().hex[:8], "kind": kind, "consumerId": b.get("consumerId"), "status": "pending", "createdAt": now_iso(),
               "title": f"Ladder {b.get('ladder')} on {name}" if kind == "ladder" else f"{name} · {'reviewer role' if kind == 'role' else 'access'}", "note": "with your lead"}
        self.store.put("request", req["id"], req, p.id)
        return 201, req

    def workspace(self, c):
        ws = self.catalog.workspace_for(c["principal"], self.store.list("brief"))
        ws["requests"] = self.store.list("request", c["principal"].id)
        return ws

    # ---------------- briefs ----------------
    def _new_brief(self, p):
        b = B.new_brief(p)
        return b["id"], b, p.id

    def list_briefs(self, c):
        p = c["principal"]
        return [b for b in self.store.list("brief") if b["createdBy"] == p.id or "platform.lead" in p.roles]

    def load_brief(self, c):
        b = self.store.get("brief", c["params"]["id"]); p = c["principal"]
        if not b or (b["createdBy"] != p.id and "platform.lead" not in p.roles): raise Problem(404, "Not found", "No brief with that id, or you cannot see it.")
        return b

    def patch_brief(self, c):
        b = self.load_brief(c)
        if b["status"] not in ("draft", "needs_info"): raise Problem(409, "Not editable", "A filed brief cannot be edited.")
        if_match = c["headers"].get("If-Match")
        if if_match and if_match != b["etag"]: raise Problem(409, "Changed elsewhere", "This draft was saved from another tab. Reload to see the latest version.")
        patch = c["body"] or {}
        if isinstance(patch.get("content"), dict): b["content"] = {**b["content"], **patch["content"]}
        if patch.get("currentStep") in B.STEPS: b["currentStep"] = patch["currentStep"]
        if isinstance(patch.get("completed"), list): b["completed"] = [s for s in patch["completed"] if s in B.STEPS]
        b["updatedAt"] = now_iso(); b["etag"] = B.bump(b["etag"])
        return self.store.put("brief", b["id"], b, b["createdBy"])

    def file_brief(self, c):
        b = self.load_brief(c); p = c["principal"]
        if_match = c["headers"].get("If-Match")
        if if_match and if_match != b["etag"]: raise Problem(409, "Changed elsewhere", "Reload before filing.")
        errors = B.validate(b["content"])
        if errors: raise Problem(422, "The brief is not complete", "Some sections need attention before it can be filed.", errors=errors)
        write = b["content"]["dataAndTools"]["tierCeiling"] != "R"
        if write and not any(r in ("ops.lead", "platform.lead") for r in p.roles):
            raise Problem(403, "Lead confirmation needed", "A write profile is filed by your team lead. Save the draft and ask them to file it.", "brief.lead_required")
        b.update({"status": "filed", "road": "R2", "etag": B.bump(b["etag"]), "updatedAt": now_iso()})
        return self.store.put("brief", b["id"], b, b["createdBy"])

    # ---------------- conversations ----------------
    def list_conversations(self, c):
        p = c["principal"]
        return [{"id": x["id"], "title": x["title"], "when": x.get("when", "just now"), "assistantId": x["assistantId"]} for x in self.store.list("conversation", p.id) if x["assistantId"] in p.entitlements]

    def load_conversation(self, c):
        x = self.store.get("conversation", c["params"]["id"])
        if not x or x.get("owner") != c["principal"].id: raise Problem(404, "Not found")
        return x

    def create_conversation(self, c):
        p = c["principal"]; aid = (c["body"] or {}).get("assistantId")
        meta = self.catalog.c.get("assistantMeta", {}).get(aid)
        if not meta: raise Problem(404, "Not found", "No assistant with that id.")
        if aid not in p.entitlements: raise Problem(403, "Not entitled", "Your role does not open this assistant.", "entitlement.missing")
        x = {"id": "cnv_" + uuid.uuid4().hex[:6], "title": "New conversation", "assistantId": aid, "assistant": meta, "turns": [], "owner": p.id, "when": "just now"}
        return 201, self.store.put("conversation", x["id"], x, p.id)

    def turn(self, c):
        x = self.load_conversation(c); text = str((c["body"] or {}).get("text", "")).strip()
        if not text: raise Problem(422, "Not valid", "text is required", "validation")
        at = time.strftime("%H:%M")
        x["turns"].append({"id": f"t{self.next_seq()}", "role": "user", "at": at, "views": [{"kind": "text", "text": text, "provenance": "system"}]})
        if x["title"] == "New conversation": x["title"] = text[:45] + "…" if len(text) > 48 else text
        assistant_turn = {"id": f"t{self.next_seq()}", "role": "assistant", "at": at, "views": []}
        x["turns"].append(assistant_turn)
        api = self

        def events():
            for view in api.assistant.stream(x, text, c["principal"]):
                seq = api.next_seq()
                if view.get("kind") == "feedback": view = {**view, "seq": seq}
                assistant_turn["views"].append(view)
                yield {"seq": seq, "view": view}

        def done(aborted: bool):
            if aborted: assistant_turn["views"].append({"kind": "stop", "reason": "human.interrupt", "message": "Stopped."})
            api.store.put("conversation", x["id"], x, x["owner"])
        return Stream(events(), done)

    def feedback(self, c):
        x = self.load_conversation(c); b = c["body"] or {}
        self.store.feedback(x["id"], int(b.get("seq", 0)), bool(b.get("answered")), c["principal"].id)
        return 204, None

    # ---------------- the shelf ----------------
    def shelf_get(self, c):
        r = self.catalog.shelf_record(c["params"]["name"])
        if not r: raise Problem(404, "Not found", "No component with that name is on the shelf.")
        return self.catalog.shelf_entry(r, c["principal"], self.store.list("signoff"))

    def sign(self, c):
        r = self.catalog.shelf_record(c["params"]["name"]); p = c["principal"]; b = c["body"] or {}
        if not r: raise Problem(404, "Not found", "No component with that name is on the shelf.")
        role = b.get("role")
        if role not in ("owner", "ai_security"): raise Problem(422, "Not valid", "role must be owner or ai_security.", "validation")
        if not self.catalog.may_sign(r, p, role):
            raise Problem(403, "Not the owner" if role == "owner" else "Not an AI security engineer",
                          f"The manifest names {r['owner']} as the owner; you are {p.handle}." if role == "owner" else "The ai.security role is granted by the security team lead on your platform principal.", "shelf.role")
        if r["status"] != "ready": raise Problem(409, "Not ready", f"The component is {r['status']}; a sign-off needs a ready component.", "shelf.status")
        attest = b.get("attest") or {}
        missing = [k for k in ("testsGreen", "exampleRun", "walkthroughRead", "rulesRead") if attest.get(k) is not True]
        if missing: raise Problem(422, "Every attestation is required", f"Not ticked: {', '.join(missing)}.", "validation", {f"attest.{k}": ["required"] for k in missing})
        used_in = str(b.get("usedIn") or "").strip()
        if role == "owner" and not r.get("usedIn") and not used_in: raise Problem(422, "Where was it used?", "The owner signs after one real use; name the project.", "validation", {"usedIn": ["required"]})
        recorded = self.store.list("signoff")
        if (r["signoff"].get(role) or {}).get("version") == r["version"] or any(s["component"] == r["name"] and s["role"] == role and s["version"] == r["version"] for s in recorded):
            raise Problem(409, "Already signed", f"The {'owner' if role == 'owner' else 'AI security'} sign-off at {r['version']} is already recorded.", "shelf.signed")
        rec = {"id": "so_" + uuid.uuid4().hex[:8], "component": r["name"], "role": role, "by": f"{p.name} <{p.email}>", "email": p.email, "date": now_iso()[:10], "version": r["version"],
               "usedIn": used_in or None, "note": str(b.get("note") or "").strip() or None, "attest": {k: True for k in ("testsGreen", "exampleRun", "walkthroughRead", "rulesRead")}, "recordedAt": now_iso()}
        rec = {k: v for k, v in rec.items() if v is not None}
        self.store.put("signoff", rec["id"], rec, p.id)
        log.info("shelf.signed component=%s role=%s by=%s version=%s", r["name"], role, p.id, r["version"])
        return 201, rec


# ---------------- the server ----------------

def make_handler(api: HubApi, static_dir: str = "", api_prefix: str = "/api"):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "hub-api/1.0"

        def log_message(self, fmt, *args):  # ids only, structured
            pass

        def _send(self, status: int, headers: dict, body: bytes):
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _dispatch(self):
            t0 = time.time()
            path = self.path
            if urllib.parse.urlparse(path).path == "/config.js":
                raw = ("// Runtime configuration from hub-api's settings; public values only.\nwindow.__HUB_CONFIG__ = " + json.dumps(api.s.web_config()) + ";\n").encode("utf-8")
                self.send_response(200); self.send_header("Content-Type", "application/javascript"); self.send_header("Content-Length", str(len(raw))); self.send_header("Cache-Control", "no-cache"); self.end_headers()
                return self.wfile.write(raw)
            if not path.startswith(api_prefix + "/") and path != api_prefix:
                return self._static(path)
            length = int(self.headers.get("Content-Length") or 0)
            if length > api.s.max_body_bytes:
                return self._send(413, {"Content-Type": "application/problem+json"}, json.dumps({"status": 413, "title": "Body too large", "detail": f"at most {api.s.max_body_bytes} bytes"}).encode())
            body = self.rfile.read(length) if length else b""
            res = api.handle(self.command, path[len(api_prefix):] or "/", self.headers, body)
            if isinstance(res, Stream):
                self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-cache"); self.send_header("Connection", "close"); self.end_headers()
                aborted = False
                try:
                    for ev in res.events:
                        self.wfile.write(f"event: view\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n".encode("utf-8")); self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    aborted = True
                finally:
                    if res.done: res.done(aborted)
                    self.close_connection = True
                log.info("%s %s 200 stream %dms", self.command, path, int((time.time() - t0) * 1000))
                return
            status, headers, out = res
            self._send(status, headers, out)
            log.info("%s %s %d %dms", self.command, urllib.parse.urlparse(path).path, status, int((time.time() - t0) * 1000))

        def _static(self, path: str):
            if not static_dir:
                return self._send(404, {"Content-Type": "application/json"}, b'{"status":404,"title":"Not found"}')
            rel = urllib.parse.unquote(urllib.parse.urlparse(path).path).lstrip("/")
            full = os.path.normpath(os.path.join(static_dir, rel))
            if not full.startswith(os.path.normpath(static_dir)) or not os.path.isfile(full):
                full = os.path.join(static_dir, "index.html")  # the SPA's routes
            if not os.path.isfile(full):
                return self._send(404, {"Content-Type": "text/plain"}, b"not found")
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            data = open(full, "rb").read()
            cache = "public, max-age=31536000, immutable" if "/assets/" in full else "no-cache"
            self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff"); self.send_header("X-Frame-Options", "DENY"); self.send_header("Referrer-Policy", "no-referrer"); self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = _dispatch

    return Handler


def serve(api: HubApi, host: str, port: int, static_dir: str = "") -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), make_handler(api, static_dir))
    httpd.daemon_threads = True
    return httpd
