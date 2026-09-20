"""Operations: readiness, request ids, the per-person run limit, the in-task export loop, the settings' new refusals."""
import json, threading, unittest, urllib.error, urllib.request
from agentrt import vendor  # noqa: F401
from agentrt.__main__ import export_loop
from agentrt.app import serve
from agentrt.export import S3Put
from agentrt.settings import Settings
from agentrt.wiring import build


class Ops(unittest.TestCase):
    def setUp(self):
        self.w = build(Settings(runs_per_minute=2))
        self.httpd = serve(self.w, "127.0.0.1", 0, "https://agents.example/mcp"); threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()

    def req(self, method, path, body=None, token="x", headers=None):
        h = {"Content-Type": "application/json", **(headers or {})}
        if token: h["Authorization"] = f"Bearer {self.w.token('u_dana') if token == 'x' else token}"
        try:
            r = urllib.request.urlopen(urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None, headers=h, method=method), timeout=10)
            return r.status, json.loads(r.read() or b"{}"), r.headers
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}"), e.headers

    def test_ready_verifies_the_record_and_names_each_check(self):
        s, body, _ = self.req("GET", "/ready", token=None)
        self.assertEqual((s, body["status"], body["checks"]), (200, "ready", {"record": "ok", "identity": "ok", "catalog": "ok"}))
        self.assertEqual(self.req("POST", "/runs", {"ticket_key": "INC-7", "service": "checkout"})[0], 200)   # something on the chain to tamper with
        self.w.conn.execute("UPDATE audit SET body = '{\"tampered\": true}' WHERE seq = (SELECT MAX(seq) FROM audit)"); self.w.conn.commit()
        s, body, _ = self.req("GET", "/ready", token=None)
        self.assertEqual((s, body["status"], body["checks"]["record"]), (503, "not ready", "AuditError"))

    def test_request_ids_come_back_and_runs_are_limited_per_person(self):
        s, _, h = self.req("GET", "/health", token=None, headers={"X-Request-Id": "hub_7"})
        self.assertEqual((s, h["X-Request-Id"]), (200, "hub_7"))
        s, _, h = self.req("GET", "/health", token=None)
        self.assertEqual(len(h["X-Request-Id"]), 16)
        run = lambda: self.req("POST", "/runs", {"ticket_key": "INC-7", "service": "checkout"})
        self.assertEqual([run()[0] for _ in range(2)], [200, 200])
        s, body, h = run()
        self.assertEqual((s, body["title"]), (429, "Too many requests")); self.assertGreaterEqual(int(h["Retry-After"]), 1)
        # The MCP transport shares the bucket: a tool call from the same person is refused the same way.
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}
        self.assertEqual(self.req("POST", "/mcp", init)[0], 429)
        # Another person has their own bucket; an anonymous caller is refused before any bucket is touched.
        self.assertEqual(self.req("POST", "/runs", {"ticket_key": "INC-7", "service": "checkout"}, token=self.w.token("u_ana"))[0], 200)
        self.assertEqual(self.req("POST", "/runs", {"ticket_key": "INC-7", "service": "checkout"}, token=None)[0], 401)


class ExportLoop(unittest.TestCase):
    def test_the_loop_exports_every_interval_and_survives_a_failure(self):
        w = build(Settings()); s = Settings(audit_export="s3://bucket/agents/", audit_export_interval_s=1)
        puts, stop, ticks = [], threading.Event(), []
        class Http:
            def request(self, method, url, headers, body):
                if len(puts) == 0: puts.append(("fail", url)); raise OSError("bucket unreachable")
                puts.append((method, url)); return 200, {}, b""
        put = S3Put(Http(), "us-east-1", creds_loader=lambda: __import__("sigv4").Credentials("AKIAEXAMPLE", "secret", None))
        def sleep(n):
            ticks.append(n)
            if len(ticks) == 3: stop.set()
        export_loop(w, s, stop=stop, sleep=sleep, put=put)
        self.assertEqual(ticks, [1, 1, 1])
        self.assertEqual(puts[0][0], "fail")                                     # first interval: the export failed and was logged
        self.assertTrue(any(u.endswith("/latest.json") for _, u in puts[1:]))    # second interval: the chain and its pointer landed

    def test_settings_tie_the_interval_to_a_destination_and_refuse_no_limit_live(self):
        p = " ".join(Settings(audit_export_interval_s=60).validate())
        self.assertIn("AGENT_AUDIT_EXPORT_INTERVAL_S needs AGENT_AUDIT_EXPORT", p)
        self.assertIn("AGENT_RUNS_PER_MINUTE must be above 0", " ".join(Settings(env="staging", runs_per_minute=0).validate()))
