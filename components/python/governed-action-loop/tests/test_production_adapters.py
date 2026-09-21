"""The bank's identity provider and KMS behind the same interfaces the fakes offer; the loop does not change."""
import json, time, unittest
from actionloop import catalog as C, signing
from actionloop.identity import Agent, AgentRegistry, AuthorizerConfig, IdentityError, IdentityLibrary, JwksIdP
from actionloop import jwt_rs256 as J
from tests._rsa import keypair

N, E, D = keypair(1024, seed=5)
ISSUER, AUD, JWKS = "https://idp.bank.example/tenant/v2.0", "agent-client", "https://idp.bank.example/keys"


def mint(claims, kid="k1"):
    h = J.b64url_encode(json.dumps({"alg": "RS256", "kid": kid}).encode()); p = J.b64url_encode(json.dumps(claims).encode())
    return h + "." + p + "." + J.b64url_encode(J.rsa_sign_pkcs1_sha256(N, D, (h + "." + p).encode()))


def fetch(url):
    assert url == JWKS
    return {"keys": [{"kty": "RSA", "kid": "k1", "n": J.b64url_encode(N.to_bytes(128, "big")), "e": J.b64url_encode(E.to_bytes(3, "big"))}]}


class BankIdentity(unittest.TestCase):
    def setUp(self):
        self.idp = JwksIdP(ISSUER, (AUD,), fetch, jwks_url=JWKS, roles_map={"GROUP_OPERATORS": "operator", "GROUP_LEADS": "lead"})
        reg = AgentRegistry(); reg.register(Agent("agent:x", owner="t", road="R2", ladder="L2", channel="operator"))
        self.lib = IdentityLibrary(self.idp, AuthorizerConfig(ISSUER, (AUD,)), reg)
        now = int(time.time())
        self.claims = {"iss": ISSUER, "aud": AUD, "sub": "oid-123", "name": "Dana R", "groups": ["GROUP_OPERATORS", "GROUP_OTHER"], "exp": now + 300, "nbf": now - 10, "iat": now}

    def test_a_bank_token_resolves_to_the_principal_chain_with_roles_from_groups(self):
        chain = self.lib.resolve(mint(self.claims), "agent:x")
        self.assertEqual(chain.human.id, "oid-123"); self.assertEqual(chain.human.display, "Dana R"); self.assertEqual(chain.human.roles, ("operator",))
        self.assertEqual(chain.tags()["roles"], ["operator"])

    def test_bad_tokens_are_identity_errors(self):
        for bad in (mint({**self.claims, "exp": int(time.time()) - 120}), mint({**self.claims, "iss": "https://other"}), mint({**self.claims, "aud": "other"}), "garbage", mint(self.claims, kid="zz")):
            with self.assertRaises(IdentityError):
                self.lib.resolve(bad, "agent:x")

    def test_the_fake_still_works_beside_it(self):
        from actionloop.identity import FakeIdP
        fake = FakeIdP(ISSUER, b"s", [AUD]); lib = IdentityLibrary(fake, AuthorizerConfig(ISSUER, (AUD,)), self.lib.registry)
        self.assertEqual(lib.resolve(fake.issue("u", {"roles": ["operator"]}, AUD), "agent:x").human.roles, ("operator",))


class KmsSigning(unittest.TestCase):
    def test_kms_signs_and_verifies_catalogs_like_the_local_key(self):
        kms = signing.FakeKms("arn:aws:kms:us-east-1:000000000000:key/k")
        key = signing.KmsKey(kms, kms.key_id)
        payload = C.build("c", [C.ToolDecl("t", "get", "R", "t.get", "t:read", {})], {"t.get"})
        signed = signing.sign(payload, key, ["approver-a", "approver-b"])
        signing.verify(signed, key)
        self.assertEqual(kms.calls.count("TrentService.Sign"), 2)
        tampered = signing.Signed({**signed.payload, "consumer": "x"}, signed.hash, signed.key_id, signed.signatures)
        with self.assertRaises(signing.SigningError):
            signing.verify(tampered, key)
        forged = signing.Signed(signed.payload, signed.hash, signed.key_id, {**signed.signatures, "approver-b": "0000"})
        with self.assertRaises(signing.SigningError):
            signing.verify(forged, key)
        other = signing.KmsKey(kms, "arn:aws:kms:us-east-1:000000000000:key/other")
        with self.assertRaises(signing.SigningError):
            signing.verify(signed, other)


class BankTokensAsIssued(unittest.TestCase):
    def setUp(self):
        self.idp = JwksIdP(ISSUER, (AUD,), fetch, jwks_url=JWKS, roles_map={"GROUP_OPERATORS": "operator", "GROUP_APPROVERS": "approver"})
        reg = AgentRegistry(); reg.register(Agent("agent:x", owner="t", road="R2", ladder="L2", channel="operator"))
        self.lib = IdentityLibrary(self.idp, AuthorizerConfig(ISSUER, (AUD,)), reg)
        now = int(time.time())
        self.claims = {"iss": ISSUER, "aud": AUD, "sub": "oid-123", "name": "Dana R", "groups": ["GROUP_OPERATORS"], "exp": now + 300, "nbf": now - 10, "iat": now}

    def test_a_token_naming_several_audiences_is_accepted_when_ours_is_among_them(self):
        chain = self.lib.resolve(mint({**self.claims, "aud": [AUD, "api://other-app"]}), "agent:x")
        self.assertEqual(chain.human.roles, ("operator",))
        with self.assertRaises(IdentityError): self.lib.resolve(mint({**self.claims, "aud": ["api://other-app", "api://third"]}), "agent:x")

    def test_roles_come_from_the_directory_groups_and_never_from_a_roles_claim(self):
        chain = self.lib.resolve(mint({**self.claims, "groups": [], "roles": ["approver", "operator"]}), "agent:x")
        self.assertEqual(chain.human.roles, ())

    def test_references_are_single_use_and_forgotten_past_their_deadline(self):
        chain = self.lib.resolve(mint(self.claims), "agent:x")
        ref = self.lib.mint_reference(chain, "tickets", "run-1", ttl_s=300)
        self.lib.redeem(ref, "tickets", "run-1")
        with self.assertRaises(IdentityError): self.lib.redeem(ref, "tickets", "run-1")
        for _ in range(300): self.lib.mint_reference(chain, "tickets", "run-2", ttl_s=-1)
        self.lib.mint_reference(chain, "tickets", "run-3")
        self.assertLess(len(self.lib._references), 300, "expired references are swept")
