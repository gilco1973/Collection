"""What a hostile network and a misconfigured deployment do to the service: every answer is a response, never a
dropped connection, a traceback or a downgraded person."""
import http.client, json, os, socket, tempfile, time, unittest
from hubapi.auth import IdentityMap, OidcAuth
from hubapi.settings import SERVICE, Settings
from hubapi.store import Store
from tests._rsa import keypair
from tests.support import Client, HttpServer, make_api
from tests.test_oidc import AUD, ISSUER, JWKS_URL, fetch, mint


def raw(srv: HttpServer, request: bytes, wait: float = 1.0) -> bytes:
    host, port = srv.base.replace("http://", "").split(":")
    s = socket.create_connection((host, int(port)), timeout=wait)
    s.sendall(request); out = b""
    try:
        while True:
            chunk = s.recv(65536)
            if not chunk: break
            out += chunk
    except socket.timeout:
        pass
    s.close(); return out


class WireHardening(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        open(os.path.join(self.d.name, "index.html"), "w").write("<!doctype html><title>hub</title>")
        os.mkdir(os.path.join(self.d.name, "assets")); open(os.path.join(self.d.name, "assets", "a.js"), "w").write("console.log(1)")
        self.srv = HttpServer(make_api(), static_dir=self.d.name)

    def tearDown(self):
        self.srv.close(); self.d.cleanup()

    def test_head_sends_headers_only_on_the_page_the_assets_and_config_js(self):
        for path in ("/discover", "/assets/a.js", "/config.js"):
            c = http.client.HTTPConnection(*self.srv.base.replace("http://", "").split(":"))
            c.request("HEAD", path); r = c.getresponse(); body = r.read()
            self.assertEqual((r.status, body), (200, b""), path)
            # The connection is still in step: the next request on it gets its own answer, not the HEAD's body.
            c.request("GET", "/api/health"); r2 = c.getresponse(); self.assertEqual(json.loads(r2.read())["status"], "ok"); c.close()

    def test_content_length_that_is_not_a_length_is_400_and_the_connection_closes(self):
        for value in (b"abc", b"-1"):
            out = raw(self.srv, b"GET /api/health HTTP/1.1\r\nHost: x\r\nContent-Length: " + value + b"\r\n\r\n")
            self.assertIn(b"HTTP/1.1 400", out); self.assertIn(b"Connection: close", out)

    def test_a_chunked_body_is_refused_rather_than_read_as_the_next_request(self):
        out = raw(self.srv, b"POST /api/me/requests HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer mock.gk\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n0\r\n\r\n")
        self.assertIn(b"HTTP/1.1 411", out); self.assertEqual(out.count(b"HTTP/1.1 "), 1, "one response, the chunk bytes never became a request")

    def test_a_sibling_directory_and_a_null_byte_never_leave_the_dist(self):
        sibling = self.d.name + "-secrets"; os.mkdir(sibling); open(os.path.join(sibling, "secret.txt"), "w").write("TOP SECRET")
        try:
            for path in ("/../" + os.path.basename(sibling) + "/secret.txt", "/a%00b", "/%2e%2e/%2e%2e/etc/passwd"):
                r = self.srv.request("GET", path, token=None)
                self.assertEqual(r.status, 200); self.assertIn(b"<title>hub</title>", r.read(), path)
        finally:
            os.remove(os.path.join(sibling, "secret.txt")); os.rmdir(sibling)

    def test_bodies_that_are_not_objects_and_handler_defects_are_answered(self):
        for body in (b"[1]", b'"x"', b"[" * 100_000):
            r = self.srv.request("POST", "/api/me/requests", headers={"Content-Type": "application/json"}) if False else None
            out = raw(self.srv, b"POST /api/me/requests HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer mock.gk\r\nContent-Type: application/json\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
            self.assertIn(b"HTTP/1.1 400", out, body[:10])
        self.assertEqual(self.srv.request("POST", "/api/conversations", {"assistantId": {}}).status, 422)
        c = json.loads(self.srv.request("POST", "/api/conversations", {"assistantId": "employee-assistant"}).read())
        self.assertEqual(self.srv.request("POST", f"/api/conversations/{c['id']}/feedback", {"seq": "x"}).status, 422)


class ApiHardening(unittest.TestCase):
    def setUp(self):
        self.api = make_api(); self.gk = Client(self.api, "mock.gk"); self.mc = Client(self.api, "mock.investigator")

    def test_replays_belong_to_one_person_and_one_call(self):
        body = {"kind": "access", "consumerId": "compliance-narration"}
        s1, a = self.gk.call("POST", "/me/requests", body, {"Idempotency-Key": "shared"})
        s2, b = self.mc.call("POST", "/me/requests", body, {"Idempotency-Key": "shared"})
        s3, again = self.gk.call("POST", "/me/requests", body, {"Idempotency-Key": "shared"})
        self.assertEqual((s1, s2, s3), (201, 201, 201)); self.assertNotEqual(a["id"], b["id"]); self.assertEqual(again["id"], a["id"], "another person's key never evicts yours")
        s4, other = self.gk.call("POST", "/briefs", {}, {"Idempotency-Key": "shared"})
        self.assertEqual((s4, other["code"]), (422, "idempotency.reused"))

    def test_a_broken_section_in_a_draft_is_ignored_and_the_workspace_still_renders(self):
        _, b = self.gk.call("POST", "/briefs", {})
        s, patched = self.gk.call("PATCH", f"/briefs/{b['id']}", {"content": {"useCase": "oops", "bogus": {"x": 1}}})
        self.assertEqual(s, 200); self.assertIsInstance(patched["content"]["useCase"], dict); self.assertNotIn("bogus", patched["content"])
        self.assertEqual(self.gk.call("GET", "/me/workspace")[0], 200)

    def test_a_relay_that_cannot_be_reached_ends_the_stream_with_a_stop_view(self):
        from hubapi.assistant import HttpRelayAssistant
        class Secrets:
            def get(self, name): return "t"
        api = make_api(assistant=HttpRelayAssistant("http://127.0.0.1:9", Secrets(), "token", timeout=1)); gk = Client(api, "mock.gk")
        _, c = gk.call("POST", "/conversations", {"assistantId": "employee-assistant"})
        _, events = gk.call("POST", f"/conversations/{c['id']}/turns", {"text": "hello"})
        self.assertEqual([e["view"]["kind"] for e in events][-1], "stop"); self.assertEqual(events[-1]["view"]["reason"], "upstream.error")


class ConfigHardening(unittest.TestCase):
    def test_staging_refuses_the_mocks_like_production(self):
        p = Settings(env="staging", auth="mock", assistant="fake", db_path="/var/hub/hub.db", public_url="https://hub.bank.example", secrets="aws").validate()
        self.assertTrue(any("mock identity" in x for x in p)); self.assertTrue(any("fake assistant" in x for x in p))

    def test_a_number_that_is_not_a_number_is_a_listed_problem_not_a_traceback(self):
        os.environ["HUB_RATE_PER_MINUTE"] = "3OO"
        try:
            self.assertIn("HUB_RATE_PER_MINUTE must be an integer", Settings.from_env().validate())
        finally:
            del os.environ["HUB_RATE_PER_MINUTE"]

    def test_the_files_the_service_will_open_are_checked_before_it_listens(self):
        self.assertTrue(any("SECRETS names a file" in x for x in Settings(secrets="file:/nonexistent/secrets.json").validate()))
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{not json"); bad = f.name
        try:
            self.assertTrue(any("IDENTITY_MAP is not readable JSON" in x for x in Settings(identity_map=bad).validate()))
        finally:
            os.remove(bad)


class IdentityHardening(unittest.TestCase):
    def test_the_issuer_may_be_spelled_with_or_without_the_trailing_slash(self):
        m = IdentityMap.load(os.path.join(SERVICE, "data", "identity-map.example.json")); now = int(time.time())
        for configured in (ISSUER, ISSUER + "/"):
            auth = OidcAuth(configured, AUD, JWKS_URL, fetch, m, "G")
            for iss in (ISSUER, ISSUER + "/"):
                p = auth.principal(mint({"iss": iss, "aud": AUD, "sub": "s-1", "exp": now + 600, "nbf": now - 10, "name": "A B", "email": "a.b@bank.example"}))
                self.assertEqual(p.email, "a.b@bank.example")

    def test_readiness_is_degraded_not_down_while_cached_keys_still_serve(self):
        m = IdentityMap.load(os.path.join(SERVICE, "data", "identity-map.example.json"))
        state = {"fail": False}
        def flaky(url):
            if state["fail"]: raise OSError("blip")
            return fetch(url)
        auth = OidcAuth(ISSUER, AUD, JWKS_URL, flaky, m, "G")
        self.assertIsNone(auth.ready()); state["fail"] = True; auth.jwks._at -= 3601; auth.jwks._tried -= 61
        self.assertIsNone(auth.ready(), "stale keys within their maximum age keep the task ready")
        auth.jwks._at -= 86_400; auth.jwks._tried -= 61
        not_ready = auth.ready()
        self.assertIsNotNone(not_ready); self.assertIn("OSError", not_ready, "keys past their maximum age and a provider that cannot be reached: not ready, with the failure named")
