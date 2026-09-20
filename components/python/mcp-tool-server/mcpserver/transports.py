"""Three ways to reach the server: in process (tests, examples), stdio (a local client), Streamable HTTP (the road).

Every transport builds a `Connection` for the server: `.session`, `.token` and `.request()`, the last one being how
the server asks the client something (only elicitation, never sampling). The HTTP transport answers a typed
forbidden error with 403 and `WWW-Authenticate: Bearer error="insufficient_scope", scope="..."` so a conformant
client can step up, and publishes RFC 9728 protected-resource metadata. A credential is never held: the bearer is
read from the request (HTTP) or from the environment variable named at start (stdio), each time.
"""
from __future__ import annotations
import json, os, sys, threading, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from . import protocol as P
from .server import ClientSession, McpToolServer


class ElicitationTimeout(Exception):
    pass


# ---------------- in process ----------------

class InProcessClient:
    """A client that talks to the server without a wire: `call(method, params)`; server->client requests go to `on_request`."""

    def __init__(self, server: McpToolServer, token: str | None, on_request=None):
        self.server, self.token, self.on_request = server, token, on_request or (lambda m, p: {"action": "decline"})
        self.session = ClientSession(id="ses_" + uuid.uuid4().hex[:8])
        self.n = 0

    def request(self, method: str, params: dict) -> dict:  # the server asking the client
        return self.on_request(method, params)

    def send(self, msg: dict) -> dict | None:
        return self.server.handle(msg, self)

    def call(self, method: str, params: dict | None = None) -> dict:
        self.n += 1
        res = self.send(P.request(self.n, method, params))
        if res is not None and "error" in res:
            raise P.RpcError(res["error"]["code"], res["error"]["message"], res["error"].get("data"))
        return res["result"]

    def notify(self, method: str, params: dict | None = None) -> None:
        self.send(P.notification(method, params))

    def initialize(self, elicitation: bool = True) -> dict:
        r = self.call("initialize", {"protocolVersion": P.PROTOCOL_VERSION, "capabilities": {"elicitation": {}} if elicitation else {}, "clientInfo": {"name": "in-process", "version": "0"}})
        self.notify("notifications/initialized")
        return r


# ---------------- stdio ----------------

class _StdioConnection:
    def __init__(self, token_env: str, inp, out):
        self.token_env, self.inp, self.out, self.session = token_env, inp, out, ClientSession(id="stdio")
        self.backlog: list[dict] = []
        self.n = 0

    @property
    def token(self) -> str | None:
        return os.environ.get(self.token_env)

    def write(self, msg: dict) -> None:
        self.out.write(P.dumps(msg) + "\n"); self.out.flush()

    def request(self, method: str, params: dict) -> dict:
        """Ask the client and read until its answer arrives; anything else that arrives meanwhile waits its turn."""
        self.n += 1; rid = f"srv_{self.n}"
        self.write(P.request(rid, method, params))
        while True:
            line = self.inp.readline()
            if not line:
                raise P.RpcError(P.CONFIRMATION_DECLINED, "the client went away before answering")
            try:
                msg = P.parse(line)
            except P.RpcError:
                continue
            if P.is_response(msg) and msg.get("id") == rid:
                if "error" in msg:
                    raise P.RpcError(P.CONFIRMATION_DECLINED, f"the client refused the request: {msg['error'].get('message')}")
                return msg.get("result") or {}
            self.backlog.append(msg)


def serve_stdio(server: McpToolServer, token_env: str = "MCP_BEARER_TOKEN", inp=None, out=None) -> None:
    """Newline-delimited JSON-RPC on stdin/stdout; the bearer is looked up in `token_env` at initialize, never stored."""
    inp, out = inp or sys.stdin, out or sys.stdout
    conn = _StdioConnection(token_env, inp, out)
    while True:
        if conn.backlog:
            msg = conn.backlog.pop(0)
        else:
            line = inp.readline()
            if not line:
                return
            if not line.strip():
                continue
            try:
                msg = P.parse(line)
            except P.RpcError as e:
                conn.write(P.error(None, e)); continue
        if P.is_response(msg):
            continue  # a late answer to nothing we are waiting for
        res = server.handle(msg, conn)
        if res is not None:
            conn.write(res)


# ---------------- Streamable HTTP ----------------

class _HttpConnection:
    """One request being handled: writes an SSE stream lazily the first time the server needs the client."""

    def __init__(self, session: ClientSession, token: str | None, handler, pending: dict, lock: threading.Lock, timeout: float):
        self.session, self.token, self.handler, self.pending, self.lock, self.timeout = session, token, handler, pending, lock, timeout
        self.streaming = False
        self.n = 0

    def start_stream(self) -> None:
        if self.streaming:
            return
        self.streaming = True
        h = self.handler
        h.send_response(200); h.send_header("Content-Type", "text/event-stream"); h.send_header("Cache-Control", "no-cache")
        h.send_header("Mcp-Session-Id", self.session.id); h.end_headers()

    def event(self, msg: dict) -> None:
        self.start_stream()
        self.handler.wfile.write(f"event: message\ndata: {P.dumps(msg)}\n\n".encode("utf-8")); self.handler.wfile.flush()

    def request(self, method: str, params: dict) -> dict:
        self.n += 1; rid = f"{self.session.id}:{uuid.uuid4().hex[:8]}"
        ev = threading.Event(); slot = {"event": ev, "response": None}
        with self.lock:
            self.pending[rid] = slot
        self.event(P.request(rid, method, params))
        if not ev.wait(self.timeout):
            with self.lock:
                self.pending.pop(rid, None)
            raise P.RpcError(P.CONFIRMATION_DECLINED, "no answer from the person in time; nothing ran", {"timeout_s": self.timeout})
        msg = slot["response"]
        if "error" in msg:
            raise P.RpcError(P.CONFIRMATION_DECLINED, f"the client refused the request: {msg['error'].get('message')}")
        return msg.get("result") or {}


def make_http_handler(server: McpToolServer, *, path: str = "/mcp", resource: str = "https://mcp.example.internal/mcp",
                      authorization_servers: list[str] | None = None, elicitation_timeout_s: float = 120.0):
    sessions: dict[str, ClientSession] = {}
    pending: dict[str, dict] = {}
    lock = threading.Lock()
    metadata = {"resource": resource, "authorization_servers": authorization_servers or ["https://idp.example.internal"],
                "bearer_methods_supported": ["header"], "scopes_supported": server.scopes(), "resource_name": server.name}

    class Handler(BaseHTTPRequestHandler):
        server_version = f"{server.name}/{server.version}"

        def log_message(self, *a):  # ids only; the chain is the record
            pass

        def _json(self, status: int, body: dict, headers: dict | None = None) -> None:
            raw = json.dumps(body).encode("utf-8")
            self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers(); self.wfile.write(raw)

        def _bearer(self) -> str | None:
            auth = self.headers.get("Authorization", "")
            return auth[7:].strip() if auth.startswith("Bearer ") else None

        def do_GET(self):
            if self.path == "/.well-known/oauth-protected-resource":
                return self._json(200, metadata)
            if self.path == path:
                return self._json(405, {"error": "no server-initiated stream; POST JSON-RPC to this path"}, {"Allow": "POST, DELETE"})
            self._json(404, {"error": "not found"})

        def do_DELETE(self):
            sid = self.headers.get("Mcp-Session-Id")
            with lock:
                s = sessions.pop(sid, None)
            if s and s.harness_session:
                server.harness.end(s.harness_session, "turn.complete", "session deleted by the client")
            self.send_response(204 if s else 404); self.end_headers()

        def do_POST(self):
            if self.path != path:
                return self._json(404, {"error": "not found"})
            token = self._bearer()
            if not token:
                return self._json(401, {"error": "unauthenticated"}, {"WWW-Authenticate": f'Bearer resource_metadata="{resource.rsplit("/", 1)[0]}/.well-known/oauth-protected-resource"'})
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8")
            try:
                msg = P.parse(raw)
            except P.RpcError as e:
                return self._json(400, P.error(None, e))
            if P.is_response(msg):  # the client answering an elicitation
                with lock:
                    slot = pending.pop(str(msg.get("id")), None)
                if not slot:
                    return self._json(404, {"error": "no request is waiting for that answer"})
                slot["response"] = msg; slot["event"].set()
                self.send_response(202); self.end_headers(); return
            sid = self.headers.get("Mcp-Session-Id")
            with lock:
                if msg.get("method") == "initialize":
                    session = ClientSession(id="mcp_" + uuid.uuid4().hex[:12]); sessions[session.id] = session
                else:
                    session = sessions.get(sid or "")
            if session is None:
                return self._json(404, {"error": "unknown session; initialize first"})
            conn = _HttpConnection(session, token, self, pending, lock, elicitation_timeout_s)
            res = server.handle(msg, conn)
            if res is None:
                self.send_response(202); self.send_header("Mcp-Session-Id", session.id); self.end_headers(); return
            if conn.streaming:
                conn.event(res); return
            err = res.get("error")
            if err and err["code"] == P.FORBIDDEN:
                scope = (err.get("data") or {}).get("scope", "")
                return self._json(403, res, {"WWW-Authenticate": f'Bearer error="insufficient_scope", scope="{scope}"', "Mcp-Session-Id": session.id})
            if err and err["code"] == P.INVALID_REQUEST and (err.get("data") or {}).get("www_authenticate"):
                return self._json(401, res, {"WWW-Authenticate": "Bearer"})
            self._json(200, res, {"Mcp-Session-Id": session.id})

    return Handler


def serve_http(server: McpToolServer, host: str = "127.0.0.1", port: int = 0, **kw) -> ThreadingHTTPServer:
    """Start the Streamable HTTP transport on a thread; returns the server (its `.server_address` has the port)."""
    httpd = ThreadingHTTPServer((host, port), make_http_handler(server, **kw))
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
