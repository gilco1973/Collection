"""The harness's gateway side for an external MCP server: a recorded contract, a signed allowlist, quarantine on drift."""
from .contract import Contract, ContractError
from .client import FakeMcpServer, HttpTransport, McpGateway, GatewayError

__all__ = ["Contract", "ContractError", "FakeMcpServer", "HttpTransport", "McpGateway", "GatewayError"]
