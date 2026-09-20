"""Read-only, complete, and the same stage rule as the shelf tool."""
import io, json, os, tempfile, unittest
import protocol as P
from server import Shelf, ShelfServer, find_root, serve_stdio, stage_of

ROOT = find_root(os.path.dirname(__file__))


def call(server, method, params=None, mid=1):
    return server.handle({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})


class ReadOnlyShelf(unittest.TestCase):
    def setUp(self):
        self.server = ShelfServer(Shelf(ROOT))

    def test_lists_every_component_by_category_with_its_stage(self):
        r = call(self.server, "tools/call", {"name": "shelf_list"})["result"]["structuredContent"]["items"]
        self.assertGreaterEqual(len(r), 20)
        self.assertEqual([i["category"] for i in r], sorted([i["category"] for i in r], key=lambda c: ("agent", "harness", "tool", "integration", "pattern", "skill").index(c)))
        agents = call(self.server, "tools/call", {"name": "shelf_list", "arguments": {"category": "agent"}})["result"]["structuredContent"]["items"]
        self.assertTrue(agents and all(a["category"] == "agent" for a in agents))
        self.assertIn("error", call(self.server, "tools/call", {"name": "shelf_list", "arguments": {"category": "widget"}}))

    def test_get_search_and_stage(self):
        g = call(self.server, "tools/call", {"name": "shelf_get", "arguments": {"name": "governed-action-loop"}})["result"]["structuredContent"]
        self.assertEqual(g["category"], "harness"); self.assertIn("shelf://governed-action-loop/README.md", g["resources"])
        self.assertEqual(call(self.server, "tools/call", {"name": "shelf_get", "arguments": {"name": "nope"}})["error"]["code"], P.INVALID_PARAMS)
        hits = call(self.server, "tools/call", {"name": "shelf_search", "arguments": {"q": "audit chain"}})["result"]["structuredContent"]["items"]
        self.assertEqual(hits[0]["name"], "audit-chain")
        st = call(self.server, "tools/call", {"name": "shelf_stage", "arguments": {"name": "audit-chain"}})["result"]["structuredContent"]
        self.assertIn(st["stage"]["label"], ("built", "used once for real", "owner signed", "AI security signed", "on the shelf"))

    def test_resources_are_the_component_files_and_nothing_else(self):
        res = call(self.server, "resources/list")["result"]["resources"]
        self.assertTrue(all(r["uri"].startswith("shelf://") for r in res))
        t = call(self.server, "resources/read", {"uri": "shelf://audit-chain/WALKTHROUGH.md"})["result"]["contents"][0]
        self.assertTrue(t["text"].startswith("# Walkthrough"))
        self.assertEqual(call(self.server, "resources/read", {"uri": "shelf://audit-chain/../../tools/shelf.py"})["error"]["code"], P.INVALID_PARAMS)
        self.assertEqual(call(self.server, "resources/read", {"uri": "file:///etc/hostname"})["error"]["code"], P.INVALID_PARAMS)

    def test_no_write_no_run_no_sign(self):
        tools = call(self.server, "tools/list")["result"]["tools"]
        self.assertTrue(all(t["annotations"]["readOnlyHint"] and not t["annotations"]["destructiveHint"] for t in tools))
        for name in ("shelf_sign", "shelf_run", "shelf_write"):
            self.assertEqual(call(self.server, "tools/call", {"name": name, "arguments": {}})["error"]["code"], P.INVALID_PARAMS)
        self.assertEqual(call(self.server, "sampling/createMessage")["error"]["code"], P.METHOD_NOT_FOUND)

    def test_stage_rule_matches_the_shelf_tool(self):
        m = {"version": "1.0.0", "status": "ready", "signoff": {"owner": None, "ai_security": None}, "used_in": []}
        self.assertEqual(stage_of(m)["label"], "built")
        m["used_in"] = ["p"]; self.assertEqual(stage_of(m)["label"], "used once for real")
        m["signoff"]["owner"] = {"by": "a", "date": "2026-01-01", "version": "1.0.0"}; self.assertEqual(stage_of(m)["label"], "owner signed")
        m["signoff"]["ai_security"] = {"by": "b", "date": "2026-01-01", "version": "0.9.0"}; self.assertEqual(stage_of(m)["label"], "owner signed")
        m["signoff"]["ai_security"]["version"] = "1.0.0"; self.assertEqual(stage_of(m)["label"], "on the shelf")
        m["status"] = "deprecated"; self.assertEqual(stage_of(m)["label"], "deprecated")

    def test_stdio_loop_frames_json_rpc(self):
        inp = io.StringIO('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\nnot json\n{"jsonrpc":"2.0","method":"notifications/initialized"}\n{"jsonrpc":"2.0","id":2,"method":"ping"}\n')
        out = io.StringIO()
        serve_stdio(self.server, inp, out)
        lines = [json.loads(l) for l in out.getvalue().splitlines()]
        self.assertEqual(lines[0]["result"]["serverInfo"]["name"], "shelf")
        self.assertEqual(lines[1]["error"]["code"], P.PARSE_ERROR)
        self.assertEqual(lines[2], {"jsonrpc": "2.0", "id": 2, "result": {}})
