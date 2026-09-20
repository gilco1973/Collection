"""The protocol is the wire, the harness is the control: every rule below is one the transport cannot bypass."""
import json, threading, unittest, urllib.request
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
