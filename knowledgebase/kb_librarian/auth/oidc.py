"""OpenID Connect relying party: discovery, authorization-code + PKCE, ID-token verification.

Everything network-facing goes through one ``httpx.Client`` whose transport is injectable, so the
whole flow is tested against a fake IdP without a socket. Every transport or shape failure becomes
``OidcError`` (the routes map it to a fixed 401/502), so a broken IdP can never surface as a 500.
Signing keys come from the provider's JWKS and are verified with PyJWT; an unknown ``kid`` triggers
one refetch (rate-limited), never a bypass.
"""

import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import quote, urlencode

import httpx
import jwt

from kb_librarian.config import is_secure_url

ALLOWED_ALGS = ("RS256", "RS384", "RS512", "ES256", "ES384", "PS256")
_TIMEOUT_S = 10.0
_JWKS_REFETCH_S = 60.0  # an unknown kid may refetch the key set at most this often


class OidcError(Exception):
    """A step of the flow failed for a reason the caller should treat as 'not signed in'."""


def pkce_pair() -> tuple[str, str]:
    """``(code_verifier, code_challenge)`` per RFC 7636 (S256)."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _basic(client_id: str, client_secret: str) -> str:
    """RFC 6749 §2.3.1: form-urlencode both halves before base64 (httpx's BasicAuth does not)."""
    raw = f"{quote(client_id, safe='')}:{quote(client_secret, safe='')}".encode()
    return "Basic " + base64.b64encode(raw).decode("ascii")


class OidcProvider:
    def __init__(
        self,
        issuer: str,
        client_id: str,
        redirect_uri: str,
        *,
        client_secret: str | None = None,
        scopes: str = "openid profile email",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.issuer = issuer.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes
        self._http = httpx.Client(timeout=_TIMEOUT_S, transport=transport, headers={"Accept": "application/json"})
        self._config: dict[str, Any] | None = None
        self._keys: dict[str, jwt.PyJWK] = {}
        self._keys_fetched_at = 0.0

    def _json(self, method: str, url: str, **kwargs) -> dict[str, Any]:
        try:
            response = self._http.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise OidcError(f"identity provider unreachable ({type(exc).__name__})") from exc
        if response.status_code != 200:
            raise OidcError(f"identity provider returned {response.status_code} for {url.rsplit('/', 1)[-1]}")
        try:
            data = response.json()
        except ValueError as exc:
            raise OidcError("identity provider returned a non-JSON body") from exc
        if not isinstance(data, dict):
            raise OidcError("identity provider returned an unexpected body")
        return data

    def configuration(self) -> dict[str, Any]:
        """The provider metadata, fetched once. Its ``issuer`` must equal the configured one and
        every endpoint the flow uses must be https (plaintext metadata would let an on-path attacker
        redirect the code and the token exchange)."""
        if self._config is None:
            config = self._json("GET", f"{self.issuer}/.well-known/openid-configuration")
            if str(config.get("issuer", "")).rstrip("/") != self.issuer:
                raise OidcError("discovery document issuer does not match KB_OIDC_ISSUER")
            for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
                if not isinstance(config.get(key), str) or not is_secure_url(config[key]):
                    raise OidcError(f"discovery document has no https {key}")
            self._config = config
        return self._config

    def authorization_url(self, state: str, nonce: str, code_challenge: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{self.configuration()['authorization_endpoint']}?{urlencode(params)}"

    def exchange_code(self, code: str, code_verifier: str) -> dict[str, Any]:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "code_verifier": code_verifier,
        }
        headers = {}
        if self.client_secret:
            headers["Authorization"] = _basic(self.client_id, self.client_secret)  # one auth method, not two
        else:
            data["client_id"] = self.client_id  # a public client identifies itself in the body
        tokens = self._json("POST", self.configuration()["token_endpoint"], data=data, headers=headers)
        if not isinstance(tokens.get("id_token"), str):
            raise OidcError("token response has no id_token")
        return tokens

    def _key_for(self, kid: str | None) -> jwt.PyJWK:
        if not isinstance(kid, str) or not kid:
            raise OidcError("id_token has no kid")
        if kid not in self._keys and time.monotonic() - self._keys_fetched_at >= _JWKS_REFETCH_S:
            self._keys_fetched_at = time.monotonic()
            keys = self._json("GET", self.configuration()["jwks_uri"]).get("keys", [])
            self._keys = {k["kid"]: jwt.PyJWK(k) for k in keys if isinstance(k, dict) and k.get("kid")}
        if kid not in self._keys:
            raise OidcError("id_token signed with an unknown key")
        return self._keys[kid]

    def verify_id_token(self, id_token: str, nonce: str) -> dict[str, Any]:
        """Claims of a token signed by the provider for this client, carrying the expected nonce."""
        try:
            header = jwt.get_unverified_header(id_token)
            key = self._key_for(header.get("kid"))
            claims = jwt.decode(
                id_token,
                key=key.key,
                algorithms=list(ALLOWED_ALGS),
                audience=self.client_id,
                issuer=self.issuer,
                options={"require": ["exp", "iat", "sub"]},
                leeway=30,
            )
        except jwt.PyJWTError as exc:
            raise OidcError(f"id_token rejected: {type(exc).__name__}") from exc
        if claims.get("nonce") != nonce:
            raise OidcError("id_token nonce mismatch")
        aud = claims.get("aud")
        if isinstance(aud, list) and len(aud) > 1 and claims.get("azp") != self.client_id:
            raise OidcError("id_token has several audiences but no matching azp")  # OIDC Core 3.1.3.7
        return claims

    def close(self) -> None:
        self._http.close()
