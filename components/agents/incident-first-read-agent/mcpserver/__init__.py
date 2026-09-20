"""An MCP server in front of the governed action loop: the protocol is the wire, the harness is the control."""
from .protocol import PROTOCOL_VERSION, RpcError
from .server import McpToolServer
from .transports import InProcessClient, serve_http, serve_stdio

__all__ = ["PROTOCOL_VERSION", "RpcError", "McpToolServer", "InProcessClient", "serve_http", "serve_stdio"]
