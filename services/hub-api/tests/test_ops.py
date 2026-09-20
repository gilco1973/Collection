"""Operations: readiness, request ids, the per-person rate limit, the record's versions, pruning and backup, the served hub's headers."""
import json, os, sqlite3, tempfile, unittest
from hubapi.auth import IdentityMap, OidcAuth
from hubapi.ops import RateLimiter, readiness, request_id
from hubapi.settings import SERVICE, Settings
from hubapi.store import SCHEMA_VERSION, Store, StoreError
from tests.support import Client, HttpServer, make_api


class Readiness(unittest.TestCase):
    def test_ready_answers_only_when_the_record_writes_and_the_keys_are_reachable(self):
        api = make_api()
        s, body = Client(api, None).call("GET", "/ready")
        self.assertEqual((s, body["status"], body["checks"]["record"], body["schema"]), (200, "ready", "ok", SCHEMA_VERSION))
        api.store.conn.close()
        s, body = Client(api, None).call("GET", "/ready")
        self.assertEqual((s, body["code"]), (503, "not.ready"))
        self.assertIn("ProgrammingError", body["detail"])

    def test_oidc_readiness_needs_the_jwks(self):
        calls = []
        def fetch(url):
            calls.append(url)
            if len(calls) == 1: raise OSError("unreachable")
            return {"keys": [{"kty": "RSA", "kid": "k", "n": "AQAB", "e": "AQAB"}]}
        auth = OidcAuth("https://idp.example", "aud", "https://idp.example/keys", fetch, IdentityMap.load(os.path.join(SERVICE, "data", "identity-map.example.json")), "GROUP_SEC")
        ok, detail = readiness({"identity": auth.ready})
        self.assertEqual((ok, detail["identity"]), (False, "OSError"))
        ok, detail = readiness({"identity": auth.ready})
        self.assertEqual((ok, detail["identity"]), (True, "ok"))
        self.assertEqual(len(calls), 2)
        readiness({"identity": auth.ready}); self.assertEqual(len(calls), 2)  # cached and fresh: no fetch


class RequestIds(unittest.TestCase):
    def test_a_plain_caller_id_is_kept_and_anything_else_is_replaced(self):
        self.assertEqual(request_id("req_abc-123"), "req_abc-123")
        self.assertNotEqual(request_id("<script>alert(1)</script>"), "<script>alert(1)</script>")
        self.assertEqual(len(request_id("x" * 65)), 16)
        self.assertEqual(len(request_id(None)), 16)

    def test_the_id_comes_back_on_every_response(self):
        srv = HttpServer(make_api())
        try:
            r = srv.request("GET", "/api/me", headers={"X-Request-Id": "hub_42"})
            self.assertEqual((r.status, r.headers["X-Request-Id"]), (200, "hub_42"))
            r = srv.request("GET", "/api/nope")
            self.assertEqual(r.status, 404); self.assertEqual(len(r.headers["X-Request-Id"]), 16)
        finally:
            srv.close()


class RateLimits(unittest.TestCase):
    def test_token_bucket_refills_and_zero_disables(self):
        clock = [0.0]
        lim = RateLimiter(60, now=lambda: clock[0])
        self.assertEqual([lim.check("a") for _ in range(60)], [0.0] * 60)
        self.assertGreaterEqual(lim.check("a"), 1.0)
        self.assertEqual(lim.check("b"), 0.0)                     # another person is not affected
        clock[0] += 2.0
        self.assertEqual(lim.check("a"), 0.0)                     # two tokens came back
        self.assertEqual(RateLimiter(0).check("a"), 0.0)

    def test_over_the_api_a_person_gets_429_with_retry_after(self):
        api = make_api(settings=Settings(rate_per_minute=3))
        c = Client(api, "mock.gk")
        self.assertEqual([c.call("GET", "/me")[0] for _ in range(3)], [200, 200, 200])
        status, body = c.call("GET", "/me")
        self.assertEqual((status, body["code"]), (429, "rate.limited"))
        self.assertEqual(Client(api, "mock.employee").call("GET", "/me")[0], 200)
        self.assertEqual(Client(api, None).call("GET", "/health")[0], 200)   # anonymous routes are not limited
        srv = HttpServer(api)
        try:
            self.assertTrue(int(srv.request("GET", "/api/me").headers["Retry-After"]) >= 1)
        finally:
            srv.close()

    def test_settings_refuse_no_limit_in_production(self):
        self.assertIn("HUB_RATE_PER_MINUTE must be above 0 in staging and production", " ".join(Settings(env="staging", rate_per_minute=0).validate()))


class Record(unittest.TestCase):
    def test_migrations_run_once_and_a_newer_record_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "hub.db")
            st = Store(path); self.assertEqual(st.version(), SCHEMA_VERSION); st.put("brief", "b1", {"id": "b1"}, "u"); st.close()
            st = Store(path); self.assertEqual(st.migrate(), 0); self.assertEqual(st.get("brief", "b1"), {"id": "b1"}); st.close()
            # A record from before versioning (tables present, user_version 0) migrates in place.
            legacy = sqlite3.connect(path); legacy.execute("PRAGMA user_version = 0"); legacy.commit(); legacy.close()
            st = Store(path); self.assertEqual(st.version(), SCHEMA_VERSION); self.assertEqual(st.get("brief", "b1"), {"id": "b1"}); st.close()
            newer = sqlite3.connect(path); newer.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}"); newer.commit(); newer.close()
            with self.assertRaises(StoreError):
                Store(path)

    def test_replays_are_pruned_after_the_ttl(self):
        st = Store(":memory:", idempotency_ttl_s=60)
        st.remember("k1", "u", 201, "application/json", b"{}")
        self.assertEqual(st.prune(now=1e12), 1)                    # long after: gone
        self.assertIsNone(st.replay("k1", "u"))
        st.remember("k2", "u", 201, "application/json", b"{}")
        self.assertEqual(st.prune(), 0)                            # now: kept
        self.assertEqual(st.replay("k2", "u")[0], 201)

    def test_conversations_past_the_retention_are_deleted_with_their_feedback(self):
        from hubapi.__main__ import retention, retention_loop
        st = Store(":memory:")
        st.put("conversation", "old", {"id": "old"}, "u"); st.feedback("old", 1, True, "u")
        st.conn.execute("UPDATE docs SET updated = updated - 100 * 86400 WHERE id = 'old'")
        st.put("conversation", "new", {"id": "new"}, "u"); st.put("brief", "b1", {"id": "b1"}, "u")
        self.assertEqual(retention(st, Settings(conversation_retention_days=0)), 0)          # 0 keeps everything
        self.assertEqual(retention(st, Settings(conversation_retention_days=90)), 1)
        self.assertEqual([x["id"] for x in st.list("conversation")], ["new"]); self.assertEqual(st.count("brief"), 1)
        self.assertEqual(st.conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0], 0)
        import threading
        stop, ticks = threading.Event(), []
        def sleep(n):
            ticks.append(n)
            if len(ticks) == 2: stop.set()
        retention_loop(st, Settings(conversation_retention_days=90), stop=stop, sleep=sleep)
        self.assertEqual(ticks, [86400, 86400])
        self.assertIn("HUB_CONVERSATION_RETENTION_DAYS must be set", " ".join(Settings(env="production", conversation_retention_days=0).validate()))

    def test_backup_is_a_consistent_copy(self):
        with tempfile.TemporaryDirectory() as d:
            st = Store(os.path.join(d, "hub.db")); st.put("brief", "b1", {"id": "b1", "n": 1}, "u")
            pages = st.backup(os.path.join(d, "copy.db")); self.assertGreater(pages, 0)
            copy = Store(os.path.join(d, "copy.db"))
            self.assertEqual(copy.get("brief", "b1"), {"id": "b1", "n": 1}); self.assertEqual(copy.version(), SCHEMA_VERSION)
            st.close(); copy.close()


class ServedHub(unittest.TestCase):
    def test_the_page_carries_a_content_security_policy_and_hsts_only_behind_https(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "index.html"), "w").write("<!doctype html><title>hub</title>")
            srv = HttpServer(make_api(settings=Settings(public_url="https://hub.example")), static_dir=d)
            try:
                r = srv.request("GET", "/discover", token=None)
                self.assertEqual(r.status, 200)
                self.assertIn("script-src 'self'", r.headers["Content-Security-Policy"]); self.assertIn("frame-ancestors 'none'", r.headers["Content-Security-Policy"])
                self.assertIn("max-age=31536000", r.headers["Strict-Transport-Security"])
            finally:
                srv.close()
            srv = HttpServer(make_api(), static_dir=d)
            try:
                self.assertIsNone(srv.request("GET", "/discover", token=None).headers.get("Strict-Transport-Security"))
            finally:
                srv.close()
