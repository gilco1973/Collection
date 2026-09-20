"""The bank's identity provider: RS256 through the JWKS, claims mapped by the identity map, mock refused in production."""
import json, os, time, unittest
from hubapi.auth import AuthError, IdentityMap, OidcAuth
from hubapi.settings import SERVICE, Settings
from hubapi.vendor import jwt_rs256 as J
from tests._rsa import keypair
from tests.support import Client, make_api

N, E, D = keypair(1024, seed=11)
ISSUER, AUD, JWKS_URL = "https://idp.bank.example", "hub-web", "https://idp.bank.example/keys"


def mint(claims: dict, kid: str = "k1") -> str:
    h = J.b64url_encode(json.dumps({"alg": "RS256", "kid": kid, "typ": "JWT"}).encode())
    p = J.b64url_encode(json.dumps(claims).encode())
    return h + "." + p + "." + J.b64url_encode(J.rsa_sign_pkcs1_sha256(N, D, (h + "." + p).encode()))


def fetch(url: str) -> dict:
    assert url == JWKS_URL, url
    return {"keys": [{"kty": "RSA", "kid": "k1", "n": J.b64url_encode(N.to_bytes((N.bit_length() + 7) // 8, "big")), "e": J.b64url_encode(E.to_bytes(3, "big"))}]}


class Oidc(unittest.TestCase):
    def setUp(self):
        self.map = IdentityMap.load(os.path.join(SERVICE, "data", "identity-map.example.json"))
        self.auth = OidcAuth(ISSUER, AUD, JWKS_URL, fetch, self.map, "GROUP_ID_AI_SECURITY")
        self.now = int(time.time())

    def claims(self, **extra):
        return {"iss": ISSUER, "aud": AUD, "sub": "abc123", "oid": "0000-1111", "name": "Ana Petrov", "email": "Ana.Petrov@bank.example", "exp": self.now + 600, "nbf": self.now - 10, "iat": self.now, **extra}

    def test_a_valid_token_becomes_a_principal_through_the_map(self):
        p = self.auth.principal(mint(self.claims(groups=["GROUP_ID_PAYMENTS_OPS_LEADS", "GROUP_ID_AI_SECURITY", "unknown-group"])))
        self.assertEqual(p.email, "ana.petrov@bank.example"); self.assertEqual(p.handle, "ana.petrov"); self.assertEqual(p.initials, "AP")
        self.assertIn("ops.lead", p.roles); self.assertIn("ai.security", p.roles); self.assertEqual(p.ladder, "L2")
        self.assertIn("investigation-triage", p.entitlements); self.assertIn("employee-assistant", p.entitlements)
        self.assertEqual(p.teams[0]["id"], "team-payments-ops")
        plain = self.auth.principal(mint(self.claims()))
        self.assertEqual((plain.roles, plain.ladder), ([], "L0")); self.assertEqual(plain.entitlements, ["employee-assistant", "policy-and-procedures"])

    def test_bad_tokens_are_401(self):
        for bad in (mint(self.claims(exp=self.now - 120)), mint(self.claims(iss="https://other.example")), mint(self.claims(aud="other")), mint(self.claims(), kid="k9"), "not.a.jwt", mint(self.claims())[:-4] + "AAAA"):
            with self.assertRaises(AuthError) as e:
                self.auth.principal(bad)
            self.assertEqual(e.exception.status, 401)

    def test_the_api_uses_it_end_to_end(self):
        api = make_api(auth=self.auth)
        me = Client(api, mint(self.claims(groups=["GROUP_ID_PAYMENTS_OPS"]))).call("GET", "/me")[1]
        self.assertEqual(me["roles"], ["ops.investigator"])
        shelf = Client(api, mint(self.claims(groups=["GROUP_ID_AI_SECURITY"]))).call("GET", "/shelf")[1]
        self.assertTrue(all(e["youMaySign"] == ["ai_security"] for e in shelf))

    def test_settings_refuse_mock_identity_and_a_fake_assistant_in_production(self):
        s = Settings(env="production", auth="mock", assistant="fake", db_path="/var/hub/hub.db", public_url="https://hub.bank.example", secrets="aws")
        problems = s.validate()
        self.assertTrue(any("mock identity" in p for p in problems)); self.assertTrue(any("fake assistant" in p for p in problems))
        ok = Settings(env="production", auth="oidc", assistant="http", assistant_url="https://runtime.bank.example", db_path="/var/hub/hub.db", public_url="https://hub.bank.example",
                      secrets="aws", idp_issuer="https://idp.bank.example", idp_audience="hub-web", ai_security_group="GROUP")
        self.assertEqual(ok.validate(), [])
        served = Settings(**{**{f: getattr(ok, f) for f in ok.__dataclass_fields__ if f != "prefix"}, "static_dir": os.path.dirname(__file__)})
        self.assertTrue(any("WEB_OIDC_AUTHORITY" in p for p in served.validate()))
        served.web_oidc_authority, served.web_oidc_client_id = "https://idp.bank.example/t/v2.0", "HUB_WEB"
        self.assertEqual(served.validate(), [])
        cfg = served.web_config()
        self.assertEqual((cfg["VITE_AUTH_MODE"], cfg["VITE_OIDC_REDIRECT_URI"], cfg["VITE_OIDC_CLIENT_ID"]), ("oidc", "https://hub.bank.example/auth/callback", "HUB_WEB"))
        self.assertTrue(any("must be https" in p for p in Settings(env="staging", db_path="/x.db", secrets="aws", auth="oidc", idp_issuer="http://idp", idp_audience="a", ai_security_group="g").validate()))
        self.assertNotIn("secret", json.dumps(ok.diagnostics()).lower().replace("secrets", ""))
