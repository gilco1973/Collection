"""`McpGateway`: the harness calls it exactly as it calls the fake gateway, and it speaks MCP to a server.

The harness decides (its hooks ran before this is reached); the gateway only carries the call: it maps the harness
name to the allowlisted remote tool, sends `tools/call`, and hands the result back projected by the harness's
data guard afterwards. A forbidden answer from the server is a deny with a typed code, an error result is a handler
error (the harness turns it into a typed stop), and a quarantined server answers nothing at all. The credential for
the server is a name looked up at call time from the reference the harness minted, never held here.
"""
from __future__ import annotations
import json, os, urllib.error, urllib.request, uuid
from dataclasses import dataclass
from actionloop.policy import Decision
from . import protocol as P
from .contract import Contract


class GatewayError(Exception):
    pass


@dataclass
class GatewayResult:
    decision: Decision
    result: dict | None
    span_id: str
    mode: str


class FakeMcpServer:
    """An in-memory MCP server behind the same `rpc(method, params)` the HTTP transport offers: tools with
    descriptions and handlers, and a `forbid` set for tools it answers with the forbidden error."""

    def __init__(self, tools: list[dict], handlers: dict, publisher: str = "example-publisher", fingerprint: str = "fp:example"):
        self.tools, self.handlers, self.publisher, self.fingerprint, self.forbid = tools, handlers, publisher, fingerprint, set()
        self.calls: list[dict] = []

    def rpc(self, method: str, params: dict, token: str | None = None) -> dict:
        if method == "initialize":
            return {"protocolVersion": P.PROTOCOL_VERSION, "capabilities": {"tools": {}}, "serverInfo": {"name": "fake", "version": "0", "publisher": self.publisher, "fingerprint": self.fingerprint}}
        if method == "tools/list":
            return {"tools": list(self.tools)}
        if method == "tools/call":
            name, args = params["name"], params.get("arguments") or {}
            self.calls.append({"name": name, "arguments": args, "token": token})
            if name in self.forbid:
                raise P.RpcError(P.FORBIDDEN, "forbidden", {"scope": name})
            if name not in self.handlers:
                raise P.RpcError(P.INVALID_PARAMS, f"unknown tool {name}")
            try:
                out = self.handlers[name](args)
            except Exception as e:
                return {"content": [{"type": "text", "text": str(e)}], "isError": True}
            return {"content": [{"type": "text", "text": json.dumps(out)}], "structuredContent": out, "isError": False}
        raise P.RpcError(P.METHOD_NOT_FOUND, method)


class HttpTransport:
    """Streamable HTTP, JSON answers only (a gateway never elicits: the harness already confirmed with the person)."""

    def __init__(self, base: str, timeout: float = 10.0):
        self.base, self.timeout, self.sid, self.n = base.rstrip("/"), timeout, None, 0

    def rpc(self, method: str, params: dict, token: str | None = None) -> dict:
        self.n += 1
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if token: headers["Authorization"] = f"Bearer {token}"
        if self.sid: headers["Mcp-Session-Id"] = self.sid
        req = urllib.request.Request(self.base, data=P.dumps(P.request(self.n, method, params)).encode(), headers=headers, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            resp = e
        self.sid = resp.headers.get("Mcp-Session-Id") or self.sid
        body = json.loads(resp.read().decode() or "{}")
        if "error" in body:
            err = body["error"]
            raise P.RpcError(err["code"], err.get("message", ""), {**(err.get("data") or {}), "http_status": getattr(resp, "status", None)})
        return body.get("result") or {}


class McpGateway:
    """The harness's gateway for one external MCP server under one contract."""

    def __init__(self, name: str, contract: Contract, transport, token_env: str | None = None, mode: str = "ENFORCE"):
        self.name, self.contract, self.transport, self.token_env, self.mode = name, contract, transport, token_env, mode
        self.quarantined: list[str] | None = None
        self.log: list[dict] = []
        self._names: list[str] | None = None

    # ---------------- the contract, checked before anything is called ----------------
    def token(self) -> str | None:
        return os.environ.get(self.token_env) if self.token_env else None

    def verify(self) -> list[str]:
        """initialize + tools/list against the contract; a problem quarantines the server until `release()`."""
        info = self.transport.rpc("initialize", {"protocolVersion": P.PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": self.name, "version": "1"}}, self.token())
        si = info.get("serverInfo") or {}
        tools = self.transport.rpc("tools/list", {}, self.token()).get("tools", [])
        problems = self.contract.verify(tools, si.get("publisher", ""), si.get("fingerprint", ""))
        self.quarantined = problems or None
        self._names = list(self.contract.allow) if not problems else []
        return problems

    def release(self, by: str) -> None:
        """A person re-verified the server (a new contract version is the honest way); recorded, not silent."""
        self.log.append({"event": "quarantine.released", "by": by, "problems": self.quarantined})
        self.quarantined = None

    def tools_list(self) -> list[str]:
        if self._names is None:
            self.verify()
        return list(self._names or [])

    # ---------------- the call ----------------
    def tools_call(self, name: str, args: dict, env: dict, harness_decision: Decision, reference: str, run_id: str) -> GatewayResult:
        span = "span_" + uuid.uuid4().hex[:12]
        if self._names is None:
            self.verify()  # a server nobody verified is a server whose descriptions may have drifted since review
        if self.quarantined:
            raise GatewayError(f"{self.name} is quarantined: {'; '.join(self.quarantined)}")
        if not harness_decision.allow:
            return GatewayResult(Decision(False, ("mcp.gateway",), "harness_denied"), None, span, self.mode)
        remote = self.contract.remote(name)
        try:
            out = self.transport.rpc("tools/call", {"name": remote, "arguments": args, "_meta": {"reference": reference, "run_id": run_id}}, self.token())
        except P.RpcError as e:
            self.log.append({"tool": name, "remote": remote, "span": span, "error": e.to_json()})
            if e.code == P.FORBIDDEN:
                return GatewayResult(Decision(False, ("mcp.remote",), "remote.forbidden"), None, span, self.mode)
            raise GatewayError(f"{remote}: {e.message}")
        self.log.append({"tool": name, "remote": remote, "span": span, "isError": bool(out.get("isError"))})
        if out.get("isError"):
            raise GatewayError(f"{remote} returned an error result")
        data = out.get("structuredContent")
        if data is None:
            text = "".join(c.get("text", "") for c in out.get("content", []) if c.get("type") == "text")
            try:
                data = json.loads(text)
            except ValueError:
                data = {"text": text}
        if not isinstance(data, dict):
            data = {"value": data}
        return GatewayResult(Decision(True, ("mcp.remote",)), data, span, self.mode)
