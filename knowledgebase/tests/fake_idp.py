"""A fake OpenID Connect provider behind ``httpx.MockTransport``: discovery, token and JWKS endpoints.

The token endpoint verifies what a real one would: grant type, redirect URI, client auth, and the
PKCE verifier against the challenge the login carried (the fake ``code`` is JSON holding the
challenge and the nonce, so a test can mint one from the login redirect).
"""

import base64
import hashlib
import json
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "https://idp.example.test"
CLIENT_ID = "kb-console"
REDIRECT_URI = "https://testserver/api/auth/callback"


def fake_code(nonce: str, challenge: str) -> str:
    return json.dumps({"nonce": nonce, "challenge": challenge})


@dataclass
class FakeIdp:
    key: rsa.RSAPrivateKey = field(
        default_factory=lambda: rsa.generate_private_key(public_exponent=65537, key_size=2048)
    )
    kid: str = "k1"
    requests: list[httpx.Request] = field(default_factory=list)
    nonce_override: str | None = None  # make the issued id_token carry a wrong nonce
    audience_override: object = None  # a wrong audience, or a list of audiences
    extra_claims: dict = field(default_factory=dict)
    token_status: int = 200
    token_body: str | None = None  # a raw (non-JSON) token response
    expired: bool = False
    unsigned: bool = False  # issue an alg=none token
    unreachable: bool = False  # every request raises a transport error
    sub: str = "u-123"
    claims: dict = field(default_factory=lambda: {"name": "Ada Lovelace", "email": "ada@example.com"})
    groups_claim: str = "groups"  # the claim the issued token carries `groups` under
    groups: object = None  # a list of group names, or a non-list value to test rejection; None = no claim

    def jwks(self) -> dict:
        public = jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key(), as_dict=True)
        return {"keys": [{**public, "kid": self.kid, "use": "sig", "alg": "RS256"}]}

    def id_token(self, nonce: str, *, kid: str | None = None) -> str:
        now = int(time.time())
        payload = {
            "iss": ISSUER,
            "aud": self.audience_override or CLIENT_ID,
            "sub": self.sub,
            "iat": now - 600 if self.expired else now,
            "exp": now - 300 if self.expired else now + 300,
            "nonce": self.nonce_override or nonce,
            **self.claims,
            **self.extra_claims,
        }
        if self.groups is not None:
            payload[self.groups_claim] = self.groups
        if self.unsigned:
            return jwt.encode(payload, None, algorithm="none", headers={"kid": kid or self.kid})
        pem = self.key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        return jwt.encode(payload, pem, algorithm="RS256", headers={"kid": kid or self.kid})

    def _token(self, request: httpx.Request) -> httpx.Response:
        if self.token_body is not None:
            return httpx.Response(self.token_status, text=self.token_body)
        if self.token_status != 200:
            return httpx.Response(self.token_status, json={"error": "invalid_grant"})
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        authorized = request.headers.get("authorization", "").startswith("Basic ") or form.get("client_id") == CLIENT_ID
        code = json.loads(form.get("code", "{}"))
        digest = hashlib.sha256(form.get("code_verifier", "").encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        if (
            form.get("grant_type") != "authorization_code"
            or form.get("redirect_uri") != REDIRECT_URI
            or not authorized
            or code.get("challenge") != challenge
        ):
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(200, json={"id_token": self.id_token(code["nonce"]), "token_type": "Bearer"})

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.unreachable:
            raise httpx.ConnectError("connection refused", request=request)
        path = request.url.path
        if path == "/.well-known/openid-configuration":
            return httpx.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/authorize",
                    "token_endpoint": f"{ISSUER}/token",
                    "jwks_uri": f"{ISSUER}/jwks",
                },
            )
        if path == "/jwks":
            return httpx.Response(200, json=self.jwks())
        if path == "/token":
            return self._token(request)
        return httpx.Response(404, json={})

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)
