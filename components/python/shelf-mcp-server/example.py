"""Live example: the server as a subprocess over stdio, driven like a coding assistant would.

    python3 example.py
"""
from __future__ import annotations
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "server.py")], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    n = 0

    def call(method, params=None):
        nonlocal n
        n += 1
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": n, "method": method, "params": params or {}}) + "\n"); p.stdin.flush()
        msg = json.loads(p.stdout.readline())
        if "error" in msg:
            raise RuntimeError(msg["error"])
        return msg["result"]

    init = call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "example", "version": "0"}})
    print("server:", init["serverInfo"], "| capabilities:", sorted(init["capabilities"]))
    p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"); p.stdin.flush()
    print("tools:", [t["name"] for t in call("tools/list")["tools"]], "| all read-only:", all(t["annotations"]["readOnlyHint"] for t in call("tools/list")["tools"]))
    items = call("tools/call", {"name": "shelf_list", "arguments": {"category": "agent"}})["structuredContent"]["items"]
    print("agents:", [(i["name"], i["version"], i["stage"]["label"]) for i in items])
    hits = call("tools/call", {"name": "shelf_search", "arguments": {"q": "mcp"}})["structuredContent"]["items"]
    print("search 'mcp':", [h["name"] for h in hits])
    g = call("tools/call", {"name": "shelf_get", "arguments": {"name": "governed-action-loop"}})["structuredContent"]
    print("get:", g["name"], g["category"], "| sign-offs:", g["signoff"], "| resources:", len(g["resources"]))
    res = call("resources/list")["resources"]
    print("resources:", len(res), "| first:", res[0]["uri"])
    text = call("resources/read", {"uri": f"shelf://{g['name']}/README.md"})["contents"][0]["text"]
    print("README starts:", text.splitlines()[0])
    try:
        call("tools/call", {"name": "shelf_sign", "arguments": {"name": g["name"]}})
    except RuntimeError as e:
        print("no write tools:", e.args[0]["message"])
    p.stdin.close(); p.wait(timeout=5)
    print("exit:", p.returncode)


if __name__ == "__main__":
    main()
