"""The server: MCP methods mapped onto the harness, and nothing decided here.

`initialize` admits the caller with the bearer token the transport hands over; `tools/list` is the signed catalog
rendered as MCP tools with annotations derived from it (PLT-CAT-5); `tools/call` goes through the harness's three
hooks, so a W1 call parks and is put to the client as an elicitation, a tainted or out-of-scope call is a typed
forbidden error the HTTP transport turns into 403 + WWW-Authenticate, and every call is on the chain. Sampling is
disabled: the server never asks the client for a completion, and a client asking for one gets method-not-found.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from actionloop.harness import Harness, HarnessError, Stop
from actionloop.catalog import CatalogError
from . import protocol as P

TYPE_MAP = {"str": "string", "int": "integer", "float": "number", "bool": "boolean", "list": "array", "dict": "object"}
FORBIDDEN_STOPS = ("taint.forbids_tier", "ladder.violation")


@dataclass
class ClientSession:
    """One MCP session: the harness session behind it and what the client said it can do."""
    id: str
    harness_session: object = None
    initialized: bool = False
    capabilities: dict = field(default_factory=dict)
    human: str = ""          # the person admitted at initialize; every later request must carry their bearer
    last_seen: float = 0.0   # idle sessions expire on the HTTP transport

    @property
    def can_elicit(self) -> bool:
        return "elicitation" in self.capabilities


class McpToolServer:
    def __init__(self, harness: Harness, admit, *, name: str, version: str, instructions: str = ""):
        """`admit(token) -> harness Session` is the consumer's: it chooses the board and budget; the token is the caller's."""
        self.harness, self.admit, self.name, self.version, self.instructions = harness, admit, name, version, instructions

    # ---------------- the catalog as MCP tools ----------------
    def entries(self) -> list[dict]:
        return list(self.harness.catalog.payload["tools"])

    def entry(self, name: str) -> dict | None:
        return next((e for e in self.entries() if e["name"] == name), None)

    @staticmethod
    def tool_of(e: dict) -> dict:
        props = {k: {"type": TYPE_MAP.get(v.get("type", "str"), "string")} for k, v in e["args"].items()}
        required = [k for k, v in e["args"].items() if v.get("required")]
        return {"name": e["name"], "title": f"{e['target']}.{e['tool']}",
                "description": f"{e['target']}.{e['tool']} · tier {e['tier']} · contract {e['contract_op']} · scope {e['permission']}",
                "inputSchema": {"type": "object", "properties": props, "required": required, "additionalProperties": False},
                "annotations": {"title": f"{e['target']}.{e['tool']}", "readOnlyHint": e["tier"] == "R", "destructiveHint": not e["reversible"],
                                "idempotentHint": bool(e["idempotent"]), "openWorldHint": e["egress_class"] == "external"}}

    def scopes(self) -> list[str]:
        return sorted({e["permission"] for e in self.entries()})

    # ---------------- dispatch ----------------
    def handle(self, msg: dict, conn) -> dict | None:
        """One incoming message; returns the response to send, or None for a notification. `conn` is the transport's
        connection: `.session` (a ClientSession), `.token` (the bearer, or None) and `.request(method, params)`."""
        method, params, mid = msg.get("method"), msg.get("params") or {}, msg.get("id")
        try:
            if P.is_notification(msg):
                if method == "notifications/initialized":
                    conn.session.initialized = True
                return None
            if method == "initialize":
                return P.result(mid, self.initialize(params, conn))
            if method == "ping":
                return P.result(mid, {})
            if not conn.session.harness_session:
                raise P.RpcError(P.INVALID_REQUEST, "initialize first")
            if method == "tools/list":
                return P.result(mid, {"tools": [self.tool_of(e) for e in self.entries()]})
            if method == "tools/call":
                return P.result(mid, self.call(params, conn))
            if method.startswith("sampling/"):
                raise P.RpcError(P.METHOD_NOT_FOUND, "sampling is disabled on this server")
            raise P.RpcError(P.METHOD_NOT_FOUND, f"method not found: {method}")
        except P.RpcError as e:
            return P.error(mid, e)
        except Exception as e:  # noqa: BLE001 - a defect answers as an error, by class; the server keeps serving
            return P.error(mid, P.RpcError(P.INTERNAL_ERROR, f"internal error: {type(e).__name__}"))

    def initialize(self, params: dict, conn) -> dict:
        if not conn.token:
            raise P.RpcError(P.INVALID_REQUEST, "a bearer token is required", {"www_authenticate": "Bearer"})
        try:
            conn.session.harness_session = self.admit(conn.token)
        except Stop as e:
            raise P.RpcError(P.FORBIDDEN, f"admission refused: {e.reason}", {"reason": e.reason})
        except Exception as e:  # the identity library's typed refusals
            raise P.RpcError(P.FORBIDDEN, f"admission refused: {type(e).__name__}", {"reason": "identity"})
        conn.session.capabilities = dict(params.get("capabilities") or {})
        return {"protocolVersion": P.PROTOCOL_VERSION, "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": self.name, "version": self.version}, "instructions": self.instructions}

    def call(self, params: dict, conn) -> dict:
        name, args = params.get("name"), params.get("arguments") or {}
        e = self.entry(name or "")
        if not e:
            raise P.RpcError(P.INVALID_PARAMS, f"unknown tool {name!r}")
        if not isinstance(args, dict):
            raise P.RpcError(P.INVALID_PARAMS, "arguments must be an object")
        s = conn.session.harness_session
        try:
            r = self.harness.call(s, name, args)
        except Stop as stop:
            if stop.reason != "needs.input":
                raise self.stopped(stop, e)
            r = self.confirm_and_call(s, name, args, e, conn)
        except (CatalogError, HarnessError) as err:
            raise P.RpcError(P.INVALID_PARAMS, str(err))
        if r.get("denied"):
            raise P.RpcError(P.FORBIDDEN, f"denied: {r.get('code')}", {"scope": e["permission"], "reason": r.get("code"), "policy_ids": r.get("policy_ids", [])})
        return {"content": [{"type": "text", "text": json.dumps(r["data"], ensure_ascii=False)}], "structuredContent": r["data"], "isError": False,
                "_meta": {"tier": e["tier"], "pii_classes": r.get("pii_classes", []), "tainted": r.get("tainted", False)}}

    def confirm_and_call(self, s, name: str, args: dict, e: dict, conn) -> dict:
        """W1: the harness parked the call; the person confirms the exact tool and arguments through elicitation."""
        pending = s.pending
        if not conn.session.can_elicit:
            raise P.RpcError(P.CONFIRMATION_DECLINED, "this call needs the person's confirmation and the client declared no elicitation capability",
                             {"tool": name, "arguments": args, "hash": pending["hash"]})
        answer = conn.request("elicitation/create", {
            "message": f"Confirm {e['target']}.{e['tool']} with {json.dumps(args, ensure_ascii=False)}? Tier {e['tier']}: it runs once, on your authority.",
            "requestedSchema": {"type": "object", "properties": {"confirm": {"type": "boolean", "title": "Confirm", "description": f"hash {pending['hash']}"}}, "required": ["confirm"]}})
        if answer.get("action") != "accept" or (answer.get("content") or {}).get("confirm") is not True:
            raise P.RpcError(P.CONFIRMATION_DECLINED, "not confirmed by the person; nothing ran", {"tool": name, "action": answer.get("action")})
        ref = self.harness.confirm(s, s.chain.human.id, pending["hash"])
        try:
            return self.harness.call(s, name, args, refs={"confirmation": ref})
        except Stop as stop:
            raise self.stopped(stop, e)

    @staticmethod
    def stopped(stop: Stop, e: dict) -> P.RpcError:
        if stop.reason in FORBIDDEN_STOPS or stop.reason.startswith("kill."):
            return P.RpcError(P.FORBIDDEN, f"forbidden: {stop.reason}", {"scope": e["permission"], "reason": stop.reason})
        return P.RpcError(P.STOPPED, f"stopped: {stop.reason}", {"reason": stop.reason, "detail": stop.detail})
