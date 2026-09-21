"""JSON-RPC 2.0 framing for the Model Context Protocol, standard library only.

Only the shapes: requests, notifications, responses, the standard error codes and the three this server adds.
Nothing here knows about tools or tiers.
"""
from __future__ import annotations
import json

PROTOCOL_VERSION = "2025-06-18"

PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR = -32700, -32600, -32601, -32602, -32603
FORBIDDEN = -32003            # a deny for taint, ladder, scope or a kill switch; the HTTP transport answers 403 + WWW-Authenticate
CONFIRMATION_DECLINED = -32004  # a W1 call the person did not confirm
STOPPED = -32005              # a budget or handler stop: typed reason in data


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.data = code, message, data

    def to_json(self) -> dict:
        e = {"code": self.code, "message": self.message}
        if self.data is not None:
            e["data"] = self.data
        return e


def request(id, method: str, params: dict | None = None) -> dict:
    return {"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}}


def notification(method: str, params: dict | None = None) -> dict:
    return {"jsonrpc": "2.0", "method": method, "params": params or {}}


def result(id, r: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id, "result": r}


def error(id, err: RpcError) -> dict:
    return {"jsonrpc": "2.0", "id": id, "error": err.to_json()}


def parse(text: str) -> dict:
    try:
        msg = json.loads(text)
    except (ValueError, RecursionError):
        raise RpcError(PARSE_ERROR, "parse error")
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        raise RpcError(INVALID_REQUEST, "invalid request: not a JSON-RPC 2.0 message")
    if "params" in msg and msg["params"] is not None and not isinstance(msg["params"], dict):
        raise RpcError(INVALID_REQUEST, "invalid request: params must be an object")
    if "method" in msg and not isinstance(msg["method"], str):
        raise RpcError(INVALID_REQUEST, "invalid request: method must be a string")
    if "method" not in msg and "result" not in msg and "error" not in msg:
        raise RpcError(INVALID_REQUEST, "invalid request: neither a request nor a response")
    return msg


def is_request(msg: dict) -> bool:
    return "method" in msg and "id" in msg


def is_notification(msg: dict) -> bool:
    return "method" in msg and "id" not in msg


def is_response(msg: dict) -> bool:
    return "method" not in msg and "id" in msg


def dumps(msg: dict) -> str:
    return json.dumps(msg, separators=(",", ":"), ensure_ascii=False)
