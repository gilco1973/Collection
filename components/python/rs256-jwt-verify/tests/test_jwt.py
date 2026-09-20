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
