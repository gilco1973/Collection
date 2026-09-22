import json
import os
import threading
import time
import unittest
import urllib.error
import urllib.request

from tests.helpers import EXAMPLES, tempdir
from aiplayground import server


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempdir()
        cls.data = cls.tmp.__enter__()
        cls.httpd = server.make_server(cls.data, port=0, token="test-token", quiet=True)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.httpd.store.db.close()
        cls.tmp.__exit__(None, None, None)

    def call(self, method, path, body=None, token="test-token", host=None, ctype="application/json", raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method=method)
        if token:
            req.add_header("X-Playground-Token", token)
        if data is not None:
            req.add_header("Content-Type", ctype)
        if host:
            req.add_header("Host", host)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def js(self, *a, **k):
        code, body, _ = self.call(*a, **k)
        return code, json.loads(body)

    def test_page_and_its_policy(self):
        code, body, headers = self.call("GET", "/", token=None)
        self.assertEqual(code, 200)
        self.assertIn(b"AI Playground", body)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(self.call("GET", "/app.js", token=None)[0], 200)

    def test_the_api_needs_the_token_the_loopback_host_and_json(self):
        self.assertEqual(self.call("GET", "/api/meta", token=None)[0], 401)
        self.assertEqual(self.call("GET", "/api/meta", token="wrong")[0], 401)
        self.assertEqual(self.call("GET", "/api/meta", host="evil.example:80")[0], 421)
        self.assertEqual(self.call("POST", "/api/targets", body={}, ctype="text/plain")[0], 415)
        self.assertEqual(self.call("POST", "/api/targets", raw=b"x" * 1_100_000)[0], 413)
        self.assertEqual(self.js("GET", "/api/meta")[1]["roles"], ["engineer", "ai-security"])

    def test_targets_are_validated_saved_listed_and_deleted(self):
        code, out = self.js("POST", "/api/targets", body={"name": "prod", "kind": "demo", "demo": "safe", "environment": "production"})
        self.assertEqual(code, 422)
        self.assertIn("never probes production", out["error"])
        code, out = self.js("POST", "/api/targets", body={"name": "srv-demo", "kind": "demo", "demo": "safe", "environment": "sandbox"})
        self.assertEqual(code, 201)
        names = [t["target"]["name"] for t in self.js("GET", "/api/targets")[1] if t["target"]]
        self.assertIn("srv-demo", names)
        code, out = self.js("POST", "/api/targets/srv-demo/ask", body={"prompt": "What colour is the sky?"})
        self.assertEqual(out["text"], "Blue.")
        self.assertEqual(self.js("POST", "/api/targets/srv-demo/tools", body={})[0], 422)
        self.assertEqual(self.js("DELETE", "/api/targets/srv-demo")[1], {"deleted": True})
        self.assertEqual(self.js("GET", "/api/targets/../../etc")[0], 404)

    def test_a_tool_server_can_be_listed_and_called(self):
        with open(os.path.join(EXAMPLES, "mcp-stdio.json")) as f:
            raw = json.load(f)
        raw["command"] = ["python3", os.path.join(EXAMPLES, "demo_mcp.py")]
        raw["name"] = "srv-tools"
        self.assertEqual(self.js("POST", "/api/targets", body=raw)[0], 201)
        code, tools = self.js("POST", "/api/targets/srv-tools/tools", body={})
        self.assertEqual([t["name"] for t in tools], ["lookup_ticket", "add_comment"])
        code, out = self.js("POST", "/api/targets/srv-tools/call", body={"name": "lookup_ticket", "arguments": {"ticket_id": "INC-1042"}})
        self.assertIn("open", out["text"])

    def test_a_run_from_start_to_report_triage_and_downloads(self):
        self.js("POST", "/api/targets", body={"name": "srv-vuln", "kind": "demo", "demo": "vulnerable", "environment": "sandbox"})
        self.assertEqual(self.js("POST", "/api/runs", body={"target": "srv-vuln", "probes": ["nope"]})[0], 422)
        self.assertEqual(self.js("POST", "/api/runs", body={"target": "srv-vuln", "by": "not a person"})[0], 422)
        code, out = self.js("POST", "/api/runs", body={"target": "srv-vuln", "probes": ["pi-encoded", "pi-direct-override"], "by": "Ada Placeholder <ada@example.com>"})
        self.assertEqual(code, 202)
        for _ in range(100):
            job = self.js("GET", f"/api/jobs/{out['job']}")[1]
            if job["state"] != "running":
                break
            time.sleep(0.1)
        self.assertEqual(job["state"], "done", job)
        rid = job["report_id"]
        rep = self.js("GET", f"/api/runs/{rid}")[1]
        self.assertEqual(rep["verdict"], "blocked")
        code, rep = self.js("POST", f"/api/runs/{rid}/triage", body={"result_id": "pi-direct-override", "decision": "accepted-risk", "by": "Ada Placeholder <ada@example.com>", "reason": "Accepting my own finding."})
        self.assertEqual(code, 422)
        code, rep = self.js("POST", f"/api/runs/{rid}/triage", body={"result_id": "pi-direct-override", "decision": "accepted-risk", "by": "Bob Placeholder <bob@example.com>", "reason": "Sandbox only; the owner fixes it in 0.2."})
        self.assertEqual(code, 200)
        self.assertEqual(rep["verdict"], "needs-review")
        code, body, headers = self.call("GET", f"/api/runs/{rid}/report.html")
        self.assertEqual(code, 200)
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        self.assertIn(b"Triage log", body)
        self.assertIn("attachment", self.call("GET", f"/api/runs/{rid}/report.md")[2]["Content-Disposition"])
        runs = self.js("GET", "/api/runs")[1]
        self.assertEqual(runs[0]["id"], rid)
        cmp = self.js("GET", f"/api/compare?a={rid}&b={rid}")[1]
        self.assertEqual(cmp["changes"], [])
        self.assertEqual(self.js("GET", "/api/runs/pg-nope")[0], 404)

    def test_serve_refuses_a_non_loopback_address(self):
        self.assertEqual(server.main(0, self.data, "0.0.0.0"), 3)


if __name__ == "__main__":
    unittest.main()
