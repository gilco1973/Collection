"""The HTTP application: the hub's contract on the standard library's server.

Every route is authenticated (bearer -> principal) except /health. Errors are RFC 9457 problems. Mutations with
an Idempotency-Key replay the first response for the same person. Writes to a brief carry If-Match. Turns stream
as `event: view` server-sent events. Logs carry ids only. The built hub is served from `static_dir` with an SPA
fallback so one process is the whole deployable.
"""
from __future__ import annotations
import json, logging, mimetypes, os, re, socket, threading, time, urllib.parse, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from . import briefs as B
from .auth import DEFAULT_PREFS, AuthError, bearer
from .catalog import Catalog
from .ops import RateLimiter, current_request_id, readiness, request_id
from .store import Store

log = logging.getLogger("hubapi")

ROUTE_BODY_LIMIT = 64 * 1024      # briefs, preferences and turns: a form or a message, never a megabyte
MAX_TURNS = 200                   # turns (both sides) in one conversation; past it the person starts a new one
MAX_USED_IN, MAX_NOTE = 200, 2000
GONE = (BrokenPipeError, ConnectionResetError, TimeoutError, socket.timeout)   # the client is no longer there to read


def _no_constant(name: str):
    raise ValueError(f"{name} is not JSON")


def loads_strict(raw: bytes):
    """JSON as other readers parse it: NaN and Infinity are refused rather than stored and re-emitted as invalid JSON."""
    return json.loads(raw.decode("utf-8"), parse_constant=_no_constant)


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
    def __init__(self, settings, store: Store, catalog: Catalog, auth, assistant, guide=None):
        self.s, self.store, self.catalog, self.auth, self.assistant, self.guide = settings, store, catalog, auth, assistant, guide
        self.catalog.owner_domain = getattr(settings, "owner_domain", "") or ""   # the owner signs from the bank's own directory, never a look-alike domain
        self.routes: list[tuple[str, re.Pattern, list, callable, bool, int]] = []
        self._busy: set[str] = set()   # conversations with a turn streaming (guarded by store.lock): a second turn at once is 409, never a lost update
        self.limiter = RateLimiter(getattr(settings, "rate_per_minute", 0))
        self._register()

    def route(self, method: str, path: str, handler, anonymous: bool = False, max_body: int = 0):
        keys: list[str] = []
        pattern = re.compile("^" + re.sub(r":(\w+)", lambda m: (keys.append(m.group(1)), "([^/]+)")[1], path) + "$")
        self.routes.append((method, pattern, keys, handler, anonymous, max_body))

    # ---------------- dispatch ----------------
    def handle(self, method: str, path: str, headers, body: bytes):
        """Returns (status, headers, body_bytes) or a Stream. Raises nothing: every error is a problem."""
        query = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
        path = urllib.parse.urlparse(path).path
        match = next(((p, k, h, a, mb) for m, p, k, h, a, mb in self.routes if m == method and p.match(path)), None)
        if not match:
            return self.problem(Problem(404, "Not found", f"No route {method} {path}"))
        pattern, keys, handler, anonymous, max_body = match
        principal = None
        if not anonymous:
            token = bearer(headers)
            if not token:
                return self.problem(Problem(401, "Unauthenticated", code="unauthenticated"), {"WWW-Authenticate": "Bearer"})
            try:
                principal = self.auth.principal(token)
            except AuthError as e:
                return self.problem(Problem(e.status, e.title, e.detail, e.code), {"WWW-Authenticate": "Bearer"})
        if principal:
            wait = self.limiter.check(principal.id)
            if wait:
                return self.problem(Problem(429, "Too many requests", "Slow down; the limit is per person and per minute.", "rate.limited"), {"Retry-After": str(int(wait))})
        key = headers.get("Idempotency-Key")
        route = f"{method} {path}"
        reserved = False
        if key and principal:
            with self.store.lock:   # the lookup and the reservation are one section: two calls with one key cannot both run
                hit = self.store.replay(key, principal.id)
                if hit and hit[3] and hit[3] != route:   # a row migrated from before routes were recorded has route '': it still replays
                    return self.problem(Problem(422, "Key reused", "This Idempotency-Key was used for another call; a key belongs to one request.", "idempotency.reused"))
                if hit and hit[0] == 0:   # the placeholder: the first call with this key is still running
                    return self.problem(Problem(409, "Request in progress", "A call with this Idempotency-Key is still being answered; wait for it rather than repeating it.", "idempotency.in_progress"))
                if hit:
                    return hit[0], {"Content-Type": hit[1], "Idempotent-Replayed": "true"}, hit[2]
                reserved = self.store.reserve(key, principal.id, route)
        kept = False
        try:
            res = self._execute(method, path, headers, body, principal, pattern, keys, query, handler, max_body)
            if reserved and not isinstance(res, Stream) and res[0] < 500 and res[1].get("Content-Type") == "application/json":
                self.store.remember(key, principal.id, res[0], res[1]["Content-Type"], res[2], route); kept = True
            return res
        finally:
            if reserved and not kept:   # a problem, a defect or a stream: nothing to replay, the key is free again
                self.store.forget(key, principal.id)

    def _execute(self, method, path, headers, body, principal, pattern, keys, query, handler, max_body):
        m = pattern.match(path)
        params = {k: urllib.parse.unquote(m.group(i + 1)) for i, k in enumerate(keys)}
        if max_body and len(body) > max_body:
            return self.problem(Problem(413, "Body too large", f"This call takes at most {max_body} bytes.", "body.too_large"))
        try:
            data = loads_strict(body) if body else None
        except (ValueError, RecursionError):
            return self.problem(Problem(400, "Bad request", "the body is not JSON"))
        if data is not None and not isinstance(data, dict):
            return self.problem(Problem(400, "Bad request", "the body must be a JSON object"))
        ctx = {"principal": principal, "params": params, "query": {k: v[0] for k, v in query.items()}, "body": data, "headers": headers}
        try:
            res = handler(ctx)
        except Problem as p:
            return self.problem(p)
        except Exception:  # noqa: BLE001 - a defect, never a dropped connection: the person gets a problem, the log the traceback
            log.exception("%s %s failed", method, path)
            return self.problem(Problem(500, "Internal error", "Something went wrong on the platform; the request id identifies it in the log.", "internal"))
        if isinstance(res, Stream):
            return res
        status, payload = res if isinstance(res, tuple) else (200, res)
        try:
            raw = b"" if payload is None else json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except ValueError:  # a number the record holds that JSON cannot carry: a problem, never half a document
            log.exception("%s %s produced a payload that is not JSON", method, path)
            return self.problem(Problem(500, "Internal error", "The answer could not be encoded; the request id identifies it in the log.", "internal"))
        return status, {"Content-Type": "application/json"}, raw

    @staticmethod
    def problem(p: Problem, extra: dict | None = None):
        return p.status, {"Content-Type": "application/problem+json", **(extra or {})}, json.dumps(p.to_json()).encode("utf-8")

    # ---------------- routes ----------------
    def _register(self):
        r = self.route
        r("GET", "/health", self.health, anonymous=True)
        r("GET", "/ready", self.ready, anonymous=True)
        r("GET", "/me", lambda c: {**c["principal"].to_json(), "preferences": self.store.get("prefs", c["principal"].id) or c["principal"].preferences})
        r("PUT", "/me/preferences", self.put_prefs, max_body=ROUTE_BODY_LIMIT)
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
        r("POST", "/briefs", lambda c: (201, self.store.put("brief", *self._new_brief(c["principal"]))), max_body=ROUTE_BODY_LIMIT)
        r("GET", "/briefs/:id", lambda c: self.load_brief(c))
        r("PATCH", "/briefs/:id", self.patch_brief, max_body=ROUTE_BODY_LIMIT)
        r("POST", "/briefs/:id/estimate", lambda c: B.estimate(self.catalog.c.get("estimate", {}), c["body"] or {}), max_body=ROUTE_BODY_LIMIT)
        r("POST", "/briefs/:id/road", lambda c: B.road(self.catalog.c.get("roadR2Read", {}), c["body"] or {}), max_body=ROUTE_BODY_LIMIT)
        r("POST", "/briefs/:id/file", self.file_brief, max_body=ROUTE_BODY_LIMIT)
        r("GET", "/conversations", self.list_conversations)
        r("GET", "/conversations/:id", lambda c: self.load_conversation(c))
        r("POST", "/conversations", self.create_conversation)
        r("POST", "/conversations/:id/turns", self.turn, max_body=ROUTE_BODY_LIMIT)
        r("POST", "/conversations/:id/feedback", self.feedback)
        r("POST", "/conversations/:id/handoff", self.handoff)
        r("POST", "/guide/ask", self.guide_ask)
        r("GET", "/shelf", lambda c: [self.catalog.shelf_entry(x, c["principal"], self.store.list("signoff")) for x in self.catalog.shelf])
        r("GET", "/shelf/signoffs/export", lambda c: {"generatedAt": now_iso(), "apply": "python3 tools/shelf.py --apply-signoffs shelf-signoffs.json", "signoffs": self.store.list("signoff")})
        r("GET", "/shelf/:name", self.shelf_get)
        r("POST", "/shelf/:name/signoffs", self.sign)

    def guide_ask(self, c):
        if not self.guide: raise Problem(404, "Not found", "The guide is not configured.")
        b = c["body"] or {}
        audience = b.get("audience") if b.get("audience") in ("engineer", "leadership", "employee") else ("leadership" if "platform.lead" in c["principal"].roles and not c["principal"].teams else "engineer")
        out = self.guide.ask(str(b.get("question") or ""), audience, b.get("page"))
        log.info("guide.ask audience=%s mode=%s sources=%d refused=%s", audience, out.get("mode"), len(out.get("sources", [])), out.get("refused", ""))
        return out

    def health(self, c):
        return {"status": "ok", "build": self.s.build_sha, "env": self.s.env, "auth": self.s.auth, "assistant": self.assistant.name, "components": len(self.catalog.shelf), "record": "file" if self.s.db_path != ":memory:" else "memory"}

    def ready(self, c):
        """Whether this process should receive traffic: the record answers a write, the identity provider's keys are reachable, the guide is loaded."""
        checks = {"record": self.store.ping, "identity": getattr(self.auth, "ready", lambda: None), "catalog": lambda: None if self.catalog.shelf else "no components loaded",
                  "guide": lambda: None if self.guide else "not configured"}
        ok, detail = readiness(checks)
        if not ok:
            raise Problem(503, "Not ready", json.dumps(detail), "not.ready")
        return {"status": "ready", "checks": detail, "schema": self.store.version()}

    def put_prefs(self, c):
        p = c["body"]
        if not isinstance(p, dict): raise Problem(422, "Not valid", "preferences must be an object", "validation")
        errors = {}
        for k, v in p.items():
            d = DEFAULT_PREFS.get(k)
            if k not in DEFAULT_PREFS: errors[k] = ["not a preference"]
            elif isinstance(d, dict):
                if not isinstance(v, dict) or any(kk not in d or not isinstance(vv, bool) for kk, vv in v.items()): errors[k] = ["must be an object of " + ", ".join(d) + " as true or false"]
            elif isinstance(d, bool):
                if not isinstance(v, bool): errors[k] = ["must be true or false"]
            elif not isinstance(v, str) or len(v) > 64: errors[k] = ["must be a short string"]
        if errors: raise Problem(422, "Not valid", "Some preferences are not ones the hub keeps, or have the wrong type.", "validation", errors)
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
        cid = b.get("consumerId")
        listing = next((l for l in self.catalog.all if l["id"] == cid), None) if isinstance(cid, str) else None
        if not listing: raise Problem(422, "Not valid", "consumerId must name a listing in the catalog.", "validation", {"consumerId": ["unknown listing"]})
        ladders = ["L0", "L1", "L2", "L3"]
        if kind == "ladder":
            if b.get("ladder") not in ladders: raise Problem(422, "Not valid", "ladder must be L0, L1, L2 or L3.", "validation", {"ladder": ["unknown ladder"]})
            if ladders.index(b["ladder"]) > ladders.index(p.ladder):
                raise Problem(403, "Above your ceiling", f"Your own ladder is {p.ladder}; ask your lead to raise it first.", "ladder.above")
        name = listing["name"]
        req = {"id": "req_" + uuid.uuid4().hex[:8], "kind": kind, "consumerId": b.get("consumerId"), "status": "pending", "createdAt": now_iso(),
               "title": f"Ladder {b.get('ladder')} on {name}" if kind == "ladder" else f"{name} · {'reviewer role' if kind == 'role' else 'access'}", "note": "with your lead"}
        self.store.put("request", req["id"], req, p.id)
        return 201, req

    def workspace(self, c):
        ws = self.catalog.workspace_for(c["principal"], self.store.list("brief", c["principal"].id))   # only this person's briefs, never the whole record
        ws["requests"] = self.store.list("request", c["principal"].id)
        return ws

    # ---------------- briefs ----------------
    def _new_brief(self, p):
        b = B.new_brief(p)
        return b["id"], b, p.id

    def list_briefs(self, c):
        p = c["principal"]
        return self.store.list("brief") if "platform.lead" in p.roles else self.store.list("brief", p.id)

    def load_brief(self, c):
        b = self.store.get("brief", c["params"]["id"]); p = c["principal"]
        if not b or (b["createdBy"] != p.id and "platform.lead" not in p.roles): raise Problem(404, "Not found", "No brief with that id, or you cannot see it.")
        return b

    def patch_brief(self, c):
        with self.store.lock:  # read, compare If-Match, write: one section, so two tabs saving at once cannot both win
            b = self.load_brief(c)
            if b["status"] not in ("draft", "needs_info"): raise Problem(409, "Not editable", "A filed brief cannot be edited.")
            if_match = c["headers"].get("If-Match")
            if if_match and if_match != b["etag"]: raise Problem(409, "Changed elsewhere", "This draft was saved from another tab. Reload to see the latest version.")
            patch = c["body"] or {}
            if isinstance(patch.get("content"), dict): b["content"] = {**b["content"], **{k: v for k, v in patch["content"].items() if k in B.STEPS and isinstance(v, dict)}}
            if patch.get("currentStep") in B.STEPS: b["currentStep"] = patch["currentStep"]
            if isinstance(patch.get("completed"), list): b["completed"] = [s for s in patch["completed"] if s in B.STEPS]
            b["updatedAt"] = now_iso(); b["etag"] = B.bump(b["etag"])
            return self.store.put("brief", b["id"], b, b["createdBy"])

    def file_brief(self, c):
        with self.store.lock:
            b = self.load_brief(c); p = c["principal"]
            if_match = c["headers"].get("If-Match")
            if if_match and if_match != b["etag"]: raise Problem(409, "Changed elsewhere", "Reload before filing.")
            errors = B.validate(b["content"])
            if errors: raise Problem(422, "The brief is not complete", "Some sections need attention before it can be filed.", errors=errors)
            write = b["content"]["dataAndTools"]["tierCeiling"] != "R"
            if write and not any(r in ("ops.lead", "platform.lead") for r in p.roles):
                raise Problem(403, "Lead confirmation needed", "A write profile is filed by your team lead. Save the draft and ask them to file it.", "brief.lead_required")
            b["content"] = B.with_baseline(b["content"])  # the harness baseline is the record's, not the form's
            b.update({"status": "filed", "road": "R2", "etag": B.bump(b["etag"]), "updatedAt": now_iso()})
            return self.store.put("brief", b["id"], b, b["createdBy"])

    # ---------------- conversations ----------------
    def list_conversations(self, c):
        p = c["principal"]
        return [{"id": x["id"], "title": x["title"], "when": x.get("when", "just now"), "assistantId": x["assistantId"]} for x in self.store.list("conversation", p.id) if x["assistantId"] in p.entitlements]

    def load_conversation(self, c):
        x = self.store.get("conversation", c["params"]["id"])
        if not x or x.get("owner") != c["principal"].id: raise Problem(404, "Not found")
        if x.get("assistantId") not in c["principal"].entitlements:  # a revoked entitlement bites on old conversations too
            raise Problem(403, "Not entitled", "Your role no longer opens this assistant.", "entitlement.missing")
        return x

    def handoff(self, c):
        self.load_conversation(c)
        return {"route": "human", "expected_wait_s": 240}

    def create_conversation(self, c):
        p = c["principal"]; aid = (c["body"] or {}).get("assistantId")
        if not isinstance(aid, str): raise Problem(422, "Not valid", "assistantId must be a string.", "validation")
        meta = self.catalog.c.get("assistantMeta", {}).get(aid)
        if not meta: raise Problem(404, "Not found", "No assistant with that id.")
        if aid not in p.entitlements: raise Problem(403, "Not entitled", "Your role does not open this assistant.", "entitlement.missing")
        x = {"id": "cnv_" + uuid.uuid4().hex[:6], "title": "New conversation", "assistantId": aid, "assistant": meta, "turns": [], "owner": p.id, "when": "just now"}
        return 201, self.store.put("conversation", x["id"], x, p.id)

    @staticmethod
    def view_count(x: dict) -> int:
        """Views stored in a conversation so far: a view's `seq` is its position in this order, the same after a restart."""
        return sum(len(t.get("views", [])) for t in x.get("turns", []))

    def turn(self, c):
        text = str((c["body"] or {}).get("text", "")).strip()
        if not text: raise Problem(422, "Not valid", "text is required", "validation")
        with self.store.lock:   # the read, the ceiling, the busy check and the claim are one section
            x = self.load_conversation(c)
            if len(x["turns"]) + 2 > MAX_TURNS:   # a turn adds two records (the person's and the assistant's); the ceiling is a ceiling
                raise Problem(409, "Conversation full", f"This conversation has reached {MAX_TURNS} turns; start a new conversation.", "conversation.full")
            if x["id"] in self._busy:
                raise Problem(409, "Answer in progress", "The assistant is still answering the previous message in this conversation; wait for it to finish.", "conversation.busy")
            self._busy.add(x["id"])
        at = time.strftime("%H:%M"); n = len(x["turns"]); base = self.view_count(x)
        user_turn = {"id": f"t{n + 1}", "role": "user", "at": at, "views": [{"kind": "text", "text": text, "provenance": "system"}]}
        assistant_turn = {"id": f"t{n + 2}", "role": "assistant", "at": at, "views": []}
        x["turns"] += [user_turn, assistant_turn]   # the assistant sees the conversation with this exchange; the record is written by done()
        title = (text[:45] + "…" if len(text) > 48 else text) if x["title"] == "New conversation" else None
        if title: x["title"] = title
        api = self

        def events():
            seq = base + 1   # the person's view
            for view in api.assistant.stream(x, text, c["principal"]):
                seq += 1
                if view.get("kind") == "feedback": view = {**view, "seq": seq}
                assistant_turn["views"].append(view)
                yield {"seq": seq, "view": view}

        def done(aborted: bool):
            if aborted: assistant_turn["views"].append({"kind": "stop", "reason": "human.interrupt", "message": "Stopped."})
            try:
                with api.store.lock:   # append to the record as it is now, never to the copy read before the stream
                    fresh = api.store.get("conversation", x["id"]) or {**x, "turns": x["turns"][:n]}
                    if len(fresh["turns"]) + 2 <= MAX_TURNS:
                        fresh["turns"] = list(fresh["turns"]) + [user_turn, assistant_turn]
                    else:
                        log.warning("conversation.full at write conversation=%s turns=%d", x["id"], len(fresh["turns"]))
                    if title and fresh.get("title") == "New conversation": fresh["title"] = title
                    api.store.put("conversation", fresh["id"], fresh, fresh["owner"])
            finally:
                with api.store.lock:
                    api._busy.discard(x["id"])
        return Stream(events(), done)

    def feedback(self, c):
        x = self.load_conversation(c); b = c["body"] or {}
        seq = b.get("seq", 0)
        if not isinstance(seq, int) or isinstance(seq, bool) or not 0 <= seq < 2**63: raise Problem(422, "Not valid", "seq must be an integer.", "validation")
        if not 1 <= seq <= self.view_count(x): raise Problem(422, "Not valid", "seq does not name a view of this conversation.", "validation", {"seq": ["unknown view"]})
        self.store.feedback(x["id"], seq, bool(b.get("answered")), c["principal"].id)
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
        attest = b.get("attest")
        if attest is not None and not isinstance(attest, dict): raise Problem(422, "Not valid", "attest must be an object of the four attestations.", "validation", {"attest": ["must be an object"]})
        attest = attest or {}
        missing = [k for k in ("testsGreen", "exampleRun", "walkthroughRead", "rulesRead") if attest.get(k) is not True]
        if missing: raise Problem(422, "Every attestation is required", f"Not ticked: {', '.join(missing)}.", "validation", {f"attest.{k}": ["required"] for k in missing})
        used_in, note = str(b.get("usedIn") or "").strip(), str(b.get("note") or "").strip()
        if role == "owner" and not r.get("usedIn") and not used_in: raise Problem(422, "Where was it used?", "The owner signs after one real use; name the project.", "validation", {"usedIn": ["required"]})
        if len(used_in) > MAX_USED_IN: raise Problem(422, "Not valid", f"usedIn is at most {MAX_USED_IN} characters.", "validation", {"usedIn": ["too long"]})
        if len(note) > MAX_NOTE: raise Problem(422, "Not valid", f"note is at most {MAX_NOTE} characters.", "validation", {"note": ["too long"]})
        rec = {"id": "so_" + uuid.uuid4().hex[:8], "component": r["name"], "role": role, "by": f"{p.name} <{p.email}>", "email": p.email, "date": now_iso()[:10], "version": r["version"],
               "usedIn": used_in or None, "note": note or None, "attest": {k: True for k in ("testsGreen", "exampleRun", "walkthroughRead", "rulesRead")}, "recordedAt": now_iso()}
        rec = {k: v for k, v in rec.items() if v is not None}
        with self.store.lock:  # the duplicate check and the write are one section: one sign-off per (component, role, version)
            recorded = self.store.list("signoff")
            if (r["signoff"].get(role) or {}).get("version") == r["version"] or any(s["component"] == r["name"] and s["role"] == role and s["version"] == r["version"] for s in recorded):
                raise Problem(409, "Already signed", f"The {'owner' if role == 'owner' else 'AI security'} sign-off at {r['version']} is already recorded.", "shelf.signed")
            other = "ai_security" if role == "owner" else "owner"   # separation of duties: two sign-offs are two people
            if any(s["component"] == r["name"] and s["role"] == other and s["version"] == r["version"] and s.get("email", "").lower() == p.email.lower() for s in recorded):
                raise Problem(409, "Two sign-offs are two people", f"You already recorded the {'AI security' if other == 'ai_security' else 'owner'} sign-off at {r['version']}; the other one is someone else's.", "shelf.duties")
            self.store.put("signoff", rec["id"], rec, p.id)
        log.info("shelf.signed component=%s role=%s by=%s version=%s", r["name"], role, p.id, r["version"])
        return 201, rec


# ---------------- the server ----------------

def make_handler(api: HubApi, static_dir: str = "", api_prefix: str = "/api"):
    csp = csp_for(api.s)
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "hub-api/1.0"
        timeout = 30  # seconds a socket may sit idle (a stalled body, a keep-alive nobody uses) before its thread is released

        def log_message(self, fmt, *args):  # ids only, structured
            pass

        def _stopping(self) -> bool:
            """The server loop has been asked to stop, or has stopped: keep-alive connections close after their response."""
            srv = self.server
            done = getattr(srv, "_BaseServer__is_shut_down", None)
            return bool(getattr(srv, "_BaseServer__shutdown_request", False) or (done is not None and done.is_set()))

        def _send(self, status: int, headers: dict, body: bytes):
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            if "Connection" not in headers and self._stopping():
                self.send_header("Connection", "close")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Request-Id", current_request_id())
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _dispatch(self):
            """One parsed request to the end of its response, counted in and out so a stop can wait for the requests
            still being answered (see `drain`); an idle keep-alive connection is not in flight."""
            lock = getattr(self.server, "inflight_lock", None)
            if lock is not None:
                with lock:
                    self.server.inflight += 1
            try:
                self._dispatch_one()
            except (BrokenPipeError, ConnectionResetError):
                pass  # the browser navigated away mid-response; nothing to log and nothing to answer
            except (TimeoutError, socket.timeout):
                self.close_connection = True  # the client stopped sending; the thread goes back to the pool
            except Exception:  # noqa: BLE001 - a defect outside the API's own handling: answer 500 when nothing was sent yet
                log.exception("%s %s failed", self.command, self.path.split("?")[0])
                try:
                    self.close_connection = True
                    self._send(500, {"Content-Type": "application/problem+json", "Connection": "close"}, json.dumps({"status": 500, "title": "Internal error", "code": "internal"}).encode())
                except Exception:  # noqa: BLE001 - headers already sent or the socket gone
                    pass
            finally:
                if lock is not None:
                    with lock:
                        self.server.inflight -= 1
                if self._stopping():
                    self.close_connection = True

        def _dispatch_one(self):
            t0 = time.time()
            path = self.path
            request_id(self.headers.get("X-Request-Id"))
            if self._stopping():   # a request that arrived on a kept-alive connection after the stop began: not started here
                self.close_connection = True
                return self._send(503, {"Content-Type": "application/problem+json", "Connection": "close", "Retry-After": "1"}, json.dumps({"status": 503, "title": "Shutting down", "code": "not.ready"}).encode())
            # The body's framing is checked before any branch answers: a body sent to a page, an asset or /config.js
            # that nobody reads would be parsed as the next request on the connection (request smuggling).
            if self.headers.get("Transfer-Encoding"):
                # Bodies arrive with a length here; a chunked body would otherwise be read as the next request.
                self.close_connection = True
                return self._send(411, {"Content-Type": "application/problem+json", "Connection": "close"}, json.dumps({"status": 411, "title": "Length required", "detail": "send Content-Length, not Transfer-Encoding"}).encode())
            lengths = {v.strip() for v in (self.headers.get_all("Content-Length") or [])}
            if len(lengths) > 1 or any(not re.fullmatch(r"[0-9]{1,18}", v) for v in lengths):   # ASCII digits only: no sign, no underscore, no other script's digits, no second value
                self.close_connection = True
                return self._send(400, {"Content-Type": "application/problem+json", "Connection": "close"}, json.dumps({"status": 400, "title": "Bad request", "detail": "Content-Length must be one non-negative integer"}).encode())
            length = int(lengths.pop()) if lengths else 0
            if not path.startswith(api_prefix + "/") and path != api_prefix:
                if length:
                    # Pages and assets take no body. A small one is drained so the refusal reaches the client; the connection closes either way.
                    remaining = length if length <= 65536 else 0
                    while remaining > 0:
                        chunk = self.rfile.read(min(65536, remaining))
                        if not chunk: break
                        remaining -= len(chunk)
                    self.close_connection = True
                    return self._send(405, {"Content-Type": "application/problem+json", "Connection": "close", "Allow": "GET, HEAD"}, json.dumps({"status": 405, "title": "Method not allowed", "detail": "pages and assets take no request body"}).encode())
                if urllib.parse.urlparse(path).path == "/config.js":
                    raw = ("// Runtime configuration from hub-api's settings; public values only.\nwindow.__HUB_CONFIG__ = " + json.dumps(api.s.web_config()) + ";\n").encode("utf-8")
                    self.send_response(200); self.send_header("Content-Type", "application/javascript"); self.send_header("Content-Length", str(len(raw))); self.send_header("Cache-Control", "no-cache"); self.end_headers()
                    return self.wfile.write(raw) if self.command != "HEAD" else None
                return self._static(path)
            if length > api.s.max_body_bytes:
                # Drain what the client is sending (bounded) so the refusal reaches it instead of a broken pipe, then close.
                remaining = min(length, 8 * api.s.max_body_bytes)
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk: break
                    remaining -= len(chunk)
                self.close_connection = True
                return self._send(413, {"Content-Type": "application/problem+json", "Connection": "close"}, json.dumps({"status": 413, "title": "Body too large", "detail": f"at most {api.s.max_body_bytes} bytes"}).encode())
            body = self.rfile.read(length) if length else b""
            res = api.handle(self.command, path[len(api_prefix):] or "/", self.headers, body)
            if isinstance(res, Stream):
                aborted = False
                try:
                    self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-cache"); self.send_header("Connection", "close"); self.send_header("X-Request-Id", current_request_id()); self.end_headers()
                    for ev in res.events:
                        self.wfile.write(f"event: view\ndata: {json.dumps(ev, ensure_ascii=False, allow_nan=False)}\n\n".encode("utf-8")); self.wfile.flush()
                except GONE:   # the browser navigated away, or stopped reading (a write that times out): the answer stops here
                    aborted = True
                except Exception:  # noqa: BLE001 - the adapter failed mid-stream: the person sees why the answer stopped
                    log.exception("stream failed")
                    try:
                        stop = {"kind": "stop", "reason": "upstream.error", "message": "The assistant stopped answering; try again in a moment."}
                        self.wfile.write(f"event: view\ndata: {json.dumps(stop)}\n\n".encode("utf-8")); self.wfile.flush()
                    except GONE:
                        aborted = True
                finally:
                    getattr(res.events, "close", lambda: None)()   # the adapter's generator releases whatever it holds upstream
                    if res.done: res.done(aborted)
                    self.close_connection = True
                log.info("%s %s 200 stream%s %dms", self.command, urllib.parse.urlparse(path).path, " aborted" if aborted else "", int((time.time() - t0) * 1000))
                return
            status, headers, out = res
            self._send(status, headers, out)
            log.info("%s %s %d %dms", self.command, urllib.parse.urlparse(path).path, status, int((time.time() - t0) * 1000))

        def _static(self, path: str):
            if not static_dir:
                return self._send(404, {"Content-Type": "application/json"}, b'{"status":404,"title":"Not found"}')
            rel = urllib.parse.unquote(urllib.parse.urlparse(path).path).lstrip("/")
            root = os.path.realpath(static_dir)
            try:
                full = os.path.realpath(os.path.join(root, rel))
            except ValueError:  # a null byte in the path: not a file, so the SPA's route
                full = root
            if os.path.commonpath([root, full]) != root or not os.path.isfile(full):
                full = os.path.join(root, "index.html")  # the SPA's routes
            if not os.path.isfile(full):
                return self._send(404, {"Content-Type": "text/plain"}, b"not found")
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            data = open(full, "rb").read()
            cache = "public, max-age=31536000, immutable" if "/assets/" in full else "no-cache"
            self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff"); self.send_header("X-Frame-Options", "SAMEORIGIN"); self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", csp)
            if api.s.public_url.startswith("https://"):
                self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = _dispatch

    return Handler


# The hub is one origin: its scripts, styles, fonts and API all come from here. Inline styles are React's style
# attributes; inline scripts are not allowed, so an injected page cannot run code even if it got into a response.
CSP = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'; object-src 'none'"


def csp_for(settings) -> str:
    """The base policy, plus the identity provider's origin where the browser must reach it: its discovery document,
    keys, token and userinfo endpoints (connect-src) and the silent-renew and session frames (frame-src). The frame
    also comes back to the hub's own callback, so frame-src names the hub too and frame-ancestors is 'self' (the hub
    may frame itself, nobody else may frame the hub); without both the browser refuses the renew and every reload
    signs the person out."""
    authority = getattr(settings, "web_oidc_authority", "") if getattr(settings, "auth", "") == "oidc" else ""
    if not authority:
        return CSP
    u = urllib.parse.urlsplit(authority); origin = f"{u.scheme}://{u.netloc}"
    return CSP.replace("connect-src 'self'", f"connect-src 'self' {origin}") + f"; frame-src 'self' {origin}"


def serve(api: HubApi, host: str, port: int, static_dir: str = "") -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), make_handler(api, static_dir))
    httpd.daemon_threads = True
    httpd.inflight, httpd.inflight_lock = 0, threading.Lock()
    return httpd


def drain(httpd, timeout_s: float = 25.0, sleep=time.sleep) -> bool:
    """After `shutdown()`: waits for the requests still being answered (a turn mid-stream finishes and is written to
    the record); True when none remain, False when the timeout passed first."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        with httpd.inflight_lock:
            if httpd.inflight == 0: return True
        sleep(0.05)
    with httpd.inflight_lock:
        return httpd.inflight == 0
