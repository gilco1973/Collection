"""The runtime in the sandbox with fakes, the production wiring with injected doubles, and the settings' refusals."""
import json, threading, time, unittest, urllib.error, urllib.request
from agentrt import vendor  # noqa: F401
from agentrt.app import serve
from agentrt.export import S3Put, export_chain
from agentrt.settings import Settings
from agentrt.wiring import build
from actionloop import signing
from actionloop.identity import FakeIdP, JwksIdP
from actionloop import jwt_rs256 as J
from tests._rsa import keypair
import ado as ADO, jira as JIRA


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.w = build(Settings())
        self.httpd = serve(self.w, "127.0.0.1", 0, "https://agents.example/mcp"); threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()

    def req(self, method, path, body=None, token="x"):
        h = {"Content-Type": "application/json"}
        if token: h["Authorization"] = f"Bearer {self.w.token('u_dana') if token == 'x' else token}"
        try:
            r = urllib.request.urlopen(urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None, headers=h, method=method), timeout=10)
            return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_health_names_the_wiring_without_secrets(self):
        s, h = self.req("GET", "/health", token=None)
        self.assertEqual((s, h["agent"], h["engine"], h["targets"]), (200, "incident-first-read", "rules", {"tickets": "FakeJira", "deploys": "FakeAdo"}))

    def test_a_run_reads_thinks_parks_and_posts_after_confirmation(self):
        self.assertEqual(self.req("POST", "/runs", {"ticket_key": "INC-7", "service": "checkout"}, token=None)[0], 401)
        s, r = self.req("POST", "/runs", {"ticket_key": "INC-7", "service": "checkout"})
        self.assertEqual(s, 200); self.assertIn("4822", r["first_read"]["hypothesis"]); self.assertEqual(r["proposal"]["kind"], "rollback"); self.assertTrue(r["parked"])
        self.assertEqual(self.w.targets["tickets"].comments, [])
        self.assertEqual(self.req("POST", f"/runs/{r['session']}/confirm", {"hash": "0" * 64})[0], 409)
        s, done = self.req("POST", f"/runs/{r['session']}/confirm", {"hash": r["parked"]["hash"]})
        self.assertEqual((s, done["posted"]), (200, {"id": "1"})); self.assertEqual(self.w.targets["tickets"].comments[0]["by"], "u_dana")
        s, r2 = self.req("POST", "/runs", {"ticket_key": "INC-8", "service": "checkout"})
        self.assertTrue(r2["tainted"]); self.assertEqual(r2["blocked"], "taint.forbids_tier")
        self.assertGreaterEqual(self.w.audit.verify(), 8)

    def test_mcp_and_metadata_are_served_beside_the_run_api(self):
        s, meta = self.req("GET", "/.well-known/oauth-protected-resource", token=None)
        self.assertEqual(sorted(meta["scopes_supported"]), ["deploys:read", "tickets:read", "tickets:write"])
        s, init = self.req("POST", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
        self.assertEqual(init["result"]["serverInfo"]["name"], "incident-first-read")


class ProductionWiring(unittest.TestCase):
    def test_the_bank_wiring_with_doubles(self):
        N, E, D = keypair(1024, seed=3)
        jwks = {"keys": [{"kty": "RSA", "kid": "k", "n": J.b64url_encode(N.to_bytes(128, "big")), "e": J.b64url_encode(E.to_bytes(3, "big"))}]}
        kms = signing.FakeKms("arn:aws:kms:us-east-1:000000000000:key/k")

        class Http:
            def __init__(self): self.calls = []
            def json(self, method, url, headers, payload=None):
                self.calls.append((method, url))
                if "/rest/api/2/issue/INC-7" in url: return {"key": "INC-7", "fields": {"summary": "Checkout errors", "description": "5xx since 14:05", "status": {"name": "Open"}}}
                if "/comment" in url: return {"id": 77}
                if "/pipelines/42/runs" in url: return {"value": [{"id": 4822, "name": "checkout 2.14.0", "state": "completed", "result": "succeeded", "finishedDate": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 300))}]}
                raise AssertionError(url)
        s = Settings(env="staging", identity="oidc", idp_issuer="https://idp.bank.example/t/v2.0", idp_audience="agent-client", idp_jwks_url="https://idp.bank.example/keys", operator_group_id="G_OPS",
                     signing="kms", kms_key_id=kms.key_id, engine="bedrock", bedrock_region="us-east-1", bedrock_endpoint="https://vpce.example", bedrock_model_id="m",
                     targets=("tickets", "deploys"), jira_url="https://jira.bank.example", jira_user="svc", deploys_url="https://dev.azure.com/org", deploys_project="p", deploys_pipelines={"checkout": "42"},
                     db_path="/tmp/agent-test.db", public_url="https://agents.bank.example/mcp", secrets="file:placeholder", audit_export="s3://bucket/agents/")
        import os, tempfile
        if os.path.exists("/tmp/agent-test.db"): os.remove("/tmp/agent-test.db")
        secrets_file = os.path.join(tempfile.mkdtemp(), "secrets.json"); open(secrets_file, "w").write("{}")
        s.secrets = "file:" + secrets_file
        http = Http()
        model = lambda system, user: json.dumps({"summary": "Errors since the deploy", "hypothesis": "Deploy 4822 is the likely cause", "claims": [{"text": "deploy #4822", "citations": ["s1"]}]}) if "first-read" in system else json.dumps({"kind": "none", "claims": []})
        w = build(s, aws=kms, fetch=lambda url: jwks, http=http, model_complete=model)
        self.assertIsInstance(w.idp, JwksIdP); self.assertIsInstance(w.key, signing.KmsKey); self.assertIsInstance(w.targets["tickets"], JIRA.JiraClient); self.assertIsInstance(w.targets["deploys"], ADO.AdoClient)
        self.assertIn("TrentService.Sign", kms.calls)
        # a bank token, a run against the doubles: the secrets provider is a file with no entries, so the connectors refuse before any call
        now = int(time.time()); h = J.b64url_encode(json.dumps({"alg": "RS256", "kid": "k"}).encode()); p = J.b64url_encode(json.dumps({"iss": s.idp_issuer, "aud": s.idp_audience, "sub": "oid-1", "name": "Dana", "groups": ["G_OPS"], "exp": now + 300, "nbf": now - 5, "iat": now}).encode())
        token = h + "." + p + "." + J.b64url_encode(J.rsa_sign_pkcs1_sha256(N, D, (h + "." + p).encode()))
        session = w.harness.admit(token, board="incidents", ticket_key=None, budget=__import__("agent").budget_from(w.template))
        self.assertEqual(session.chain.human.roles, ("operator",))
        with self.assertRaises(Exception):
            w.agent.run(session, "INC-7", "checkout")  # no secret named agents/jira-token in the file: refused, nothing called
        self.assertEqual(http.calls, [])

    def test_export_puts_the_chain_and_a_pointer(self):
        w = build(Settings()); s = w.harness.admit(w.token("u"), board="b", ticket_key=None, budget=__import__("agent").budget_from(w.template)); w.harness.end(s, "turn.complete")
        puts = []
        class Http:
            def request(self, method, url, headers, body): puts.append((method, url, headers.get("Authorization", "")[:8], len(body))); return 200, {}, b""
        put = S3Put(Http(), "us-east-1", creds_loader=lambda: __import__("sigv4").Credentials("AKIAEXAMPLE", "secret", None))
        out = export_chain(w.audit, "incident-first-read", "s3://bucket/agents/", put, now=0)
        self.assertEqual(out["records"], w.audit.verify()); self.assertTrue(out["object"].startswith("s3://bucket/agents/incident-first-read/1970-01-01/"))
        self.assertEqual([p[2] for p in puts], ["AWS4-HMA", "AWS4-HMA"]); self.assertTrue(puts[1][1].endswith("/agents/incident-first-read/latest.json"))


class Refusals(unittest.TestCase):
    def test_production_refuses_every_fake(self):
        p = Settings(env="production", public_url="https://a.example/mcp", db_path="/var/x.db", secrets="aws").validate()
        for word in ("fake identity", "local signing", "rules engine", "fakes are refused", "AUDIT_EXPORT"):
            self.assertTrue(any(word in x for x in p), word)
        ok = Settings(env="production", identity="oidc", idp_issuer="https://idp", idp_audience="a", operator_group_id="g", signing="kms", kms_key_id="k", engine="bedrock", bedrock_region="r", bedrock_endpoint="https://e", bedrock_model_id="m",
                      targets=("tickets", "deploys"), jira_url="https://j", deploys_url="https://d", deploys_project="p", deploys_pipelines={"checkout": "1"}, db_path="/var/x.db", public_url="https://a/mcp", secrets="aws", audit_export="s3://b/p/")
        self.assertEqual(ok.validate(), [])
        self.assertTrue(any("template does not" in x for x in Settings(targets=("flags",)).validate()))
