"""The protocol is the wire, the harness is the control: every rule below is one the transport cannot bypass."""
import json, threading, unittest, urllib.error, urllib.request
from mcpserver import InProcessClient, protocol as P, serve_http
import example as X

ACCEPT = lambda m, p: {"action": "accept", "content": {"confirm": True}}
DECLINE = lambda m, p: {"action": "decline"}


class InProcess(unittest.TestCase):
    def setUp(self):
        self.w = X.build()

    def client(self, on_request=ACCEPT, user="u_dana", roles=("operator",), elicitation=True):
        c = InProcessClient(self.w.server, self.w.token(user, roles), on_request=on_request)
        c.initialize(elicitation=elicitation)
        return c

    def test_initialize_needs_a_bearer_and_admits_through_the_harness(self):
        c = InProcessClient(self.w.server, None)
        with self.assertRaises(P.RpcError) as e:
            c.initialize()
        self.assertEqual(e.exception.code, P.INVALID_REQUEST)
        c = InProcessClient(self.w.server, "not-a-token")
        with self.assertRaises(P.RpcError) as e:
            c.initialize()
        self.assertEqual(e.exception.code, P.FORBIDDEN)
        r = self.client().call("ping")
        self.assertEqual(r, {})

    def test_tools_list_is_the_signed_catalog_with_annotations_from_it(self):
        tools = self.client().call("tools/list")["tools"]
        by = {t["name"]: t for t in tools}
        self.assertEqual(set(by), {"tickets___get", "tickets___comment", "deploy___rollback"})
        self.assertTrue(by["tickets___get"]["annotations"]["readOnlyHint"])
        self.assertFalse(by["tickets___comment"]["annotations"]["readOnlyHint"])
        self.assertEqual(by["tickets___comment"]["inputSchema"]["required"], ["key", "body"])
        self.assertEqual(by["deploy___rollback"]["inputSchema"]["properties"]["run_id"], {"type": "integer"})

    def test_a_read_goes_through_the_hooks_and_comes_back_projected(self):
        r = self.client().call("tools/call", {"name": "tickets___get", "arguments": {"key": "T-1"}})
        self.assertEqual(r["structuredContent"]["title"], "Checkout slow")
        self.assertEqual(r["_meta"]["tier"], "R"); self.assertFalse(r["_meta"]["tainted"])
        self.assertEqual(json.loads(r["content"][0]["text"])["key"], "T-1")

    def test_a_w1_call_runs_once_only_after_the_person_accepts_the_elicitation(self):
        asked = []
        c = self.client(lambda m, p: (asked.append((m, p)), {"action": "accept", "content": {"confirm": True}})[1])
        r = c.call("tools/call", {"name": "tickets___comment", "arguments": {"key": "T-1", "body": "hi"}})
        self.assertEqual(r["structuredContent"], {"id": "c1"})
        self.assertEqual(asked[0][0], "elicitation/create"); self.assertIn("tickets.comment", asked[0][1]["message"])
        self.assertEqual(len(self.w.tickets.comments), 1)

    def test_declined_or_no_elicitation_capability_means_nothing_runs(self):
        with self.assertRaises(P.RpcError) as e:
            self.client(DECLINE).call("tools/call", {"name": "tickets___comment", "arguments": {"key": "T-1", "body": "hi"}})
        self.assertEqual(e.exception.code, P.CONFIRMATION_DECLINED)
        with self.assertRaises(P.RpcError) as e:
            self.client(ACCEPT, elicitation=False).call("tools/call", {"name": "tickets___comment", "arguments": {"key": "T-1", "body": "hi"}})
        self.assertEqual(e.exception.code, P.CONFIRMATION_DECLINED)
        self.assertEqual(self.w.tickets.comments, [])

    def test_taint_scope_and_unknown_tools_are_typed_errors(self):
        c = self.client()
        c.call("tools/call", {"name": "tickets___get", "arguments": {"key": "T-9"}})  # poisoned: the session is tainted
        with self.assertRaises(P.RpcError) as e:
            c.call("tools/call", {"name": "tickets___comment", "arguments": {"key": "T-1", "body": "hi"}})
        self.assertEqual(e.exception.code, P.FORBIDDEN); self.assertEqual(e.exception.data["scope"], "tickets:write")
        with self.assertRaises(P.RpcError) as e:
            self.client().call("tools/call", {"name": "deploy___rollback", "arguments": {"service": "x", "run_id": 1}})
        self.assertEqual(e.exception.code, P.FORBIDDEN); self.assertEqual(e.exception.data["scope"], "deploy:execute")
        with self.assertRaises(P.RpcError) as e:
            self.client().call("tools/call", {"name": "tickets___delete", "arguments": {}})
        self.assertEqual(e.exception.code, P.INVALID_PARAMS)
        with self.assertRaises(P.RpcError) as e:
            self.client().call("tools/call", {"name": "tickets___get", "arguments": {"nope": 1}})
        self.assertEqual(e.exception.code, P.INVALID_PARAMS)

    def test_sampling_is_disabled_and_the_chain_records_it_all(self):
        c = self.client()
        with self.assertRaises(P.RpcError) as e:
            c.call("sampling/createMessage", {})
        self.assertEqual(e.exception.code, P.METHOD_NOT_FOUND)
        c.call("tools/call", {"name": "tickets___get", "arguments": {"key": "T-1"}})
        self.assertGreaterEqual(self.w.audit.verify(), 2)


class OverHttp(unittest.TestCase):
    def setUp(self):
        self.w = X.build()
        self.httpd = serve_http(self.w.server, elicitation_timeout_s=5)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()

    def test_metadata_401_403_and_elicitation_over_the_stream(self):
        meta = json.loads(urllib.request.urlopen(self.base + "/.well-known/oauth-protected-resource").read())
        self.assertEqual(meta["scopes_supported"], ["deploy:execute", "tickets:read", "tickets:write"])
        req = urllib.request.Request(self.base + "/mcp", data=b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}', headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        self.assertEqual(e.exception.code, 401); self.assertIn("resource_metadata", e.exception.headers["WWW-Authenticate"])
        h = X.HttpClient(self.base, self.w.token("u_dana"), on_request=ACCEPT)
        h.initialize()
        self.assertTrue(h.sid)
        r = h.call("tools/call", {"name": "tickets___comment", "arguments": {"key": "T-1", "body": "over http"}})
        self.assertEqual(r["structuredContent"], {"id": "c1"})
        h.call("tools/call", {"name": "tickets___get", "arguments": {"key": "T-9"}})
        with self.assertRaises(P.RpcError) as e:
            h.call("tools/call", {"name": "tickets___comment", "arguments": {"key": "T-1", "body": "again"}})
        self.assertEqual(e.exception.data["http_status"], 403)
        self.assertEqual(e.exception.data["www_authenticate"], 'Bearer error="insufficient_scope", scope="tickets:write"')
        self.assertEqual(len(self.w.tickets.comments), 1)


class HttpSessions(unittest.TestCase):
    """Over the HTTP transport: a session belongs to the person admitted, is kept only once admitted, and expires idle."""

    def setUp(self):
        self.w = X.build(); self.httpd = serve_http(self.w.server, session_idle_s=0.5, max_body_bytes=2000)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()

    def post(self, body, token, sid=None):
        h = {"Content-Type": "application/json"}
        if token: h["Authorization"] = f"Bearer {token}"
        if sid: h["Mcp-Session-Id"] = sid
        try:
            r = urllib.request.urlopen(urllib.request.Request(self.base + "/mcp", data=body if isinstance(body, bytes) else json.dumps(body).encode(), headers=h, method="POST"), timeout=5)
            return r.status, json.loads(r.read() or b"{}"), r.headers.get("Mcp-Session-Id")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}"), e.headers.get("Mcp-Session-Id")

    INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}
    LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}

    def test_the_session_is_bound_to_the_person_and_dies_idle(self):
        dana, sam = self.w.token("u_dana", ("operator",)), self.w.token("u_sam", ("operator",))
        s, body, sid = self.post(self.INIT, dana); self.assertEqual(s, 200); self.assertTrue(sid)
        self.assertEqual(self.post(self.LIST, "not-a-token", sid)[0], 401)
        self.assertEqual(self.post(self.LIST, sam, sid)[0], 401, "another person's bearer never drives this session")
        self.assertEqual(self.post(self.LIST, dana, sid)[0], 200)
        req = urllib.request.Request(self.base + "/mcp", headers={"Mcp-Session-Id": sid}, method="DELETE")
        with self.assertRaises(urllib.error.HTTPError) as cm: urllib.request.urlopen(req, timeout=5)
        self.assertEqual(cm.exception.code, 401, "ending a session needs its person's bearer")
        import time; time.sleep(0.7)
        self.assertEqual(self.post(self.LIST, dana, sid)[0], 404, "an idle session expires")

    def test_a_refused_initialize_keeps_no_session_and_big_bodies_are_refused(self):
        for _ in range(5):
            s, body, sid = self.post(self.INIT, "junk-bearer"); self.assertEqual(s, 403)
            self.assertEqual(self.post(self.LIST, "junk-bearer", sid)[0], 404, "nothing was kept for a refused initialize")
        s, body, _ = self.post(json.dumps({**self.INIT, "params": {"pad": "x" * 3000}}).encode(), self.w.token("u_dana", ("operator",)))
        self.assertEqual(s, 413)


class HostileMessages(unittest.TestCase):
    def setUp(self):
        self.w = X.build(); self.httpd = serve_http(self.w.server, max_body_bytes=2_000_000)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()

    def post(self, raw: bytes, token, sid=None):
        h = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        if sid: h["Mcp-Session-Id"] = sid
        try:
            r = urllib.request.urlopen(urllib.request.Request(self.base + "/mcp", data=raw, headers=h, method="POST"), timeout=5)
            return r.status, json.loads(r.read() or b"{}"), r.headers.get("Mcp-Session-Id")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}"), e.headers.get("Mcp-Session-Id")

    def test_params_that_are_not_an_object_and_deep_nesting_are_answered_not_fatal(self):
        dana = self.w.token("u_dana", ("operator",))
        s, body, sid = self.post(json.dumps(HttpSessions.INIT).encode(), dana); self.assertEqual(s, 200)
        s, body, _ = self.post(json.dumps({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": [1, 2]}).encode(), dana, sid)
        self.assertEqual((s, body["error"]["code"]), (400, P.INVALID_REQUEST))
        s, body, _ = self.post(b"[" * 100_000, dana, sid)
        self.assertEqual((s, body["error"]["code"]), (400, P.PARSE_ERROR))
        s, body, _ = self.post(json.dumps({"jsonrpc": "2.0", "id": 6, "method": "ping"}).encode(), dana, sid)
        self.assertEqual((s, body["result"]), (200, {}), "the server is still serving")

    def test_only_the_person_asked_may_answer_an_elicitation(self):
        import http.client
        dana, sam = self.w.token("u_dana", ("operator",)), self.w.token("u_sam", ("operator",))
        init = {**HttpSessions.INIT, "params": {**HttpSessions.INIT["params"], "capabilities": {"elicitation": {}}}}
        s, body, sid = self.post(json.dumps(init).encode(), dana); self.assertEqual(s, 200)
        host, port = self.base.replace("http://", "").split(":")
        c = http.client.HTTPConnection(host, int(port), timeout=10)
        c.request("POST", "/mcp", body=json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "tickets___comment", "arguments": {"key": "T-1", "body": "hi"}}}),
                  headers={"Content-Type": "application/json", "Authorization": f"Bearer {dana}", "Mcp-Session-Id": sid})
        r = c.getresponse(); self.assertEqual(r.status, 200); self.assertIn("text/event-stream", r.getheader("Content-Type"))
        line = b""
        while not line.startswith(b"data:"):
            line = r.readline()
        rid = json.loads(line[5:])["id"]
        answer = {"jsonrpc": "2.0", "id": rid, "result": {"action": "accept", "content": {"confirm": True}}}
        self.assertEqual(self.post(json.dumps(answer).encode(), sam, sid)[0], 404, "another person's bearer cannot confirm for the person asked")
        self.assertEqual(self.post(json.dumps(answer).encode(), dana, sid)[0], 202)
        rest = r.read().decode()
        self.assertIn('"id": "c1"', rest.replace('"id":"c1"', '"id": "c1"')); self.assertEqual(len(self.w.tickets.comments), 1)
