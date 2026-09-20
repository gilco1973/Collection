"""Live example, second half: the same template served over MCP, so a client that holds the model can drive it.

    python3 example_mcp.py

tools/list is the template's three tools with annotations from their tiers; a read runs through the hooks; the
W1 comment reaches the client as an elicitation and runs once on accept. Nothing in the agent changed: the
transport sits in front of the same harness `example.build()` wires.
"""
from __future__ import annotations
from actionloop.harness import Budget
from mcpserver import InProcessClient, McpToolServer
from mcpserver import protocol as P
import example as X


def serve(w: X.Wired) -> McpToolServer:
    tpl = w.template
    admit = lambda token: w.harness.admit(token, board="checkout", ticket_key="INC-7", budget=X.budget_from(tpl))
    return McpToolServer(w.harness, admit, name=tpl["name"], version="1.0.0", instructions=tpl["role"])


def main():
    w = X.build()
    server = serve(w)
    asked = []
    accept = lambda m, p: (asked.append(p["message"]), {"action": "accept", "content": {"confirm": True}})[1]
    c = InProcessClient(server, w.token("u_dana"), on_request=accept)
    init = c.initialize()
    print("server:", init["serverInfo"]["name"], "| instructions:", init["instructions"][:70], "...")
    tools = c.call("tools/list")["tools"]
    print("tools/list from the template:", [(t["title"], "read-only" if t["annotations"]["readOnlyHint"] else "write") for t in tools])
    r = c.call("tools/call", {"name": "tickets___get", "arguments": {"key": "INC-7"}})
    print("read:", r["structuredContent"]["title"], "| tainted:", r["_meta"]["tainted"])
    r = c.call("tools/call", {"name": "tickets___comment", "arguments": {"key": "INC-7", "body": "First read posted over MCP."}})
    print("W1 after the person accepted the elicitation:", r["structuredContent"], "| asked:", asked[-1][:48], "...")
    try:
        c.call("tools/call", {"name": "deploys___rollback", "arguments": {"run_id": 4822}})
    except P.RpcError as e:
        print("not in the template, not callable:", e.code, e.message)
    print("chain verified:", w.audit.verify(), "records | comments on record:", len(w.tickets.comments))


if __name__ == "__main__":
    main()
