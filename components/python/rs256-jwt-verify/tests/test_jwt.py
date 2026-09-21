import hashlib, hmac, json, time, unittest
import jwt_rs256 as J
from tests._rsa import keypair


def mint(n, e, d, payload, kid="k1", alg="RS256"):
    header = {"alg": alg, "kid": kid, "typ": "JWT"}
    h = J.b64url_encode(json.dumps(header).encode()); p = J.b64url_encode(json.dumps(payload).encode())
    return h + "." + p + "." + J.b64url_encode(J.rsa_sign_pkcs1_sha256(n, d, (h + "." + p).encode()))


class Jwt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.n, cls.e, cls.d = keypair()
        cls.fetches = 0
        def fetch(url):
            cls.fetches += 1
            return {"keys": [{"kty": "RSA", "kid": "k1", "use": "sig", "n": J.b64url_encode(cls.n.to_bytes((cls.n.bit_length() + 7) // 8, "big")), "e": J.b64url_encode(cls.e.to_bytes(3, "big"))}]}
        cls.jwks = J.Jwks(fetch, "https://issuer.example/jwks")

    def test_good_token(self):
        now = int(time.time()); tok = mint(self.n, self.e, self.d, {"iss": "https://issuer.example", "aud": "app", "exp": now + 300, "nbf": now - 10, "sub": "u1"})
        c = J.verify(tok, self.jwks, ("https://issuer.example",), ("app",)); self.assertEqual(c["sub"], "u1")
        tok2 = mint(self.n, self.e, self.d, {"iss": "https://issuer.example", "aud": ["other", "app"], "exp": now + 300})
        J.verify(tok2, self.jwks, ("https://issuer.example",), ("app",))

    def test_bad_tokens_refused(self):
        now = int(time.time()); base = {"iss": "https://issuer.example", "aud": "app", "exp": now + 300}
        good = mint(self.n, self.e, self.d, base)
        for bad, why in [(good[:-6] + "AAAAAA", "signature"), (mint(self.n, self.e, self.d, base | {"exp": now - 100}), "expired"),
                         (mint(self.n, self.e, self.d, base | {"nbf": now + 500}), "not yet valid"), (mint(self.n, self.e, self.d, base | {"iss": "https://evil"}), "issuer"),
                         (mint(self.n, self.e, self.d, base | {"aud": "other"}), "audience"), (mint(self.n, self.e, self.d, base, alg="none"), "alg none"),
                         (mint(self.n, self.e, self.d, base, kid="k2"), "unknown kid"), ("abc", "malformed")]:
            with self.assertRaises(J.JwtError, msg=why):
                J.verify(bad, self.jwks, ("https://issuer.example",), ("app",))

    def test_hmac_confusion_refused(self):
        header = J.b64url_encode(json.dumps({"alg": "HS256", "kid": "k1"}).encode()); payload = J.b64url_encode(json.dumps({"iss": "https://issuer.example", "aud": "app", "exp": int(time.time()) + 100}).encode())
        sig = J.b64url_encode(hmac.new(b"public-key-as-secret", (header + "." + payload).encode(), hashlib.sha256).digest())
        with self.assertRaises(J.JwtError):
            J.verify(header + "." + payload + "." + sig, self.jwks, ("https://issuer.example",), ("app",))

    def test_openid_discovery(self):
        self.assertEqual(J.openid_jwks_url(lambda u: {"jwks_uri": "https://issuer.example/jwks"}, "https://issuer.example/.well-known/openid-configuration"), "https://issuer.example/jwks")


class JwksCache(unittest.TestCase):
    """Rotation, a stranger's invented kids, and a provider blip: what the cache does with each."""

    def setUp(self):
        self.n, self.e, self.d = keypair()
        self.calls = 0; self.fail = False
        def fetch(url):
            self.calls += 1
            if self.fail: raise OSError("provider unreachable")
            return {"keys": [{"kty": "RSA", "kid": "k1", "use": "sig", "n": J.b64url_encode(self.n.to_bytes((self.n.bit_length() + 7) // 8, "big")), "e": J.b64url_encode(self.e.to_bytes(3, "big"))}]}
        self.jwks = J.Jwks(fetch, "https://issuer.example/jwks", ttl_s=3600, min_refresh_s=60, max_age_s=86_400)

    def test_unknown_kids_refresh_at_most_once_a_minute(self):
        self.jwks.key("k1"); self.assertEqual(self.calls, 1)
        for _ in range(20):
            with self.assertRaises(J.JwtError): self.jwks.key("invented")
        self.assertEqual(self.calls, 1, "twenty invented kids inside a minute cost the provider nothing")
        self.jwks._tried -= 61
        with self.assertRaises(J.JwtError): self.jwks.key("invented")
        self.assertEqual(self.calls, 2, "after the minute one refresh is allowed again")

    def test_cached_keys_serve_through_a_provider_blip(self):
        self.jwks.key("k1"); self.fail = True
        self.jwks._at -= 3601; self.jwks._tried -= 61
        self.assertEqual(self.jwks.key("k1"), (self.n, self.e)); self.assertTrue(self.jwks.stale); self.assertEqual(self.jwks.last_error, "OSError")
        self.jwks._at -= 86_400; self.jwks._tried -= 61
        with self.assertRaises(OSError): self.jwks.key("k1")  # past the maximum age the failure is the answer


class Strictness(unittest.TestCase):
    def setUp(self):
        self.n, self.e, self.d = keypair()
        self.doc = {"keys": [{"kty": "RSA", "kid": "k1", "use": "sig", "n": J.b64url_encode(self.n.to_bytes((self.n.bit_length() + 7) // 8, "big")), "e": J.b64url_encode(self.e.to_bytes(3, "big"))}]}
        self.docs = [self.doc]; self.fetches = 0
        def fetch(url):
            self.fetches += 1; return self.docs[-1]
        self.jwks = J.Jwks(fetch, "https://issuer.example/jwks")
        self.now = int(time.time())

    def mint(self, payload, header_extra=None):
        header = {"alg": "RS256", "kid": "k1", **(header_extra or {})}
        h = J.b64url_encode(json.dumps(header).encode()); p = J.b64url_encode(json.dumps(payload).encode())
        return h + "." + p + "." + J.b64url_encode(J.rsa_sign_pkcs1_sha256(self.n, self.d, (h + "." + p).encode()))

    def test_crit_headers_and_non_numeric_times_are_refused(self):
        good = {"iss": "i", "aud": "a", "exp": self.now + 60, "sub": "s"}
        self.assertEqual(J.verify(self.mint(good), self.jwks, ("i",), ("a",))["sub"], "s")
        for bad in ({**good, "exp": "soon"}, {**good, "exp": float("nan")}, {**good, "exp": True}, {**good, "nbf": "x"}):
            with self.assertRaises(J.JwtError): J.verify(self.mint(bad), self.jwks, ("i",), ("a",))
        with self.assertRaises(J.JwtError): J.verify(self.mint(good, {"crit": ["b64"]}), self.jwks, ("i",), ("a",))

    def test_an_empty_or_malformed_jwks_never_replaces_the_keys_held(self):
        self.jwks.key("k1")
        self.docs.append({"keys": []}); self.jwks._at -= 3601; self.jwks._tried -= 61
        self.assertEqual(self.jwks.key("k1"), (self.n, self.e), "stale keys still serve when the provider answers with nothing usable")
        self.docs.append({"keys": [{"kty": "RSA", "n": "x", "e": "AQAB"}]}); self.jwks._at -= 3601; self.jwks._tried -= 61
        self.assertEqual(self.jwks.key("k1"), (self.n, self.e)); self.assertEqual(self.jwks.last_error, "JwtError")

    def test_a_refresh_in_progress_never_stalls_a_known_key(self):
        import threading
        self.jwks.key("k1")
        gate = threading.Event()
        def slow_fetch(url):
            gate.wait(2.0); return self.doc
        self.jwks.fetch = slow_fetch; self.jwks._tried -= 61
        t = threading.Thread(target=lambda: self.assertRaises(J.JwtError, self.jwks.key, "invented")); t.start()
        time.sleep(0.05); t0 = time.time(); self.jwks.key("k1"); took = time.time() - t0
        gate.set(); t.join()
        self.assertLess(took, 0.5, "a valid token is served from the cache while the stranger's refresh runs")
