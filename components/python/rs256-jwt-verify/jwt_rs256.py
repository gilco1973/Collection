"""RS256 JSON Web Tokens with the standard library: verification against a JWKS (Entra ID, Bot Framework, any OpenID Connect issuer).

RSA PKCS#1 v1.5 signature verification is integer arithmetic: sig^e mod n must equal the padded DigestInfo of
SHA-256 over the signing input. Keys are fetched from the issuer's OpenID configuration and cached by `kid`;
an unknown `kid` refreshes once. Every claim the standards require is checked: signature, `exp`, `nbf`, `iss`,
`aud`, and the algorithm is pinned to RS256 (no `none`, no HMAC confusion).
"""
from __future__ import annotations
import base64, hashlib, json, time

SHA256_DIGESTINFO = bytes.fromhex("3031300d060960864801650304020105000420")


class JwtError(Exception):
    pass


def b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _int(b: bytes) -> int:
    return int.from_bytes(b, "big")


def rsa_verify_pkcs1_sha256(n: int, e: int, signing_input: bytes, sig: bytes) -> bool:
    k = (n.bit_length() + 7) // 8
    if len(sig) != k:
        return False
    m = pow(_int(sig), e, n).to_bytes(k, "big")
    digest = hashlib.sha256(signing_input).digest()
    t = SHA256_DIGESTINFO + digest
    if len(t) + 11 > k:
        return False
    expected = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    return m == expected


def rsa_sign_pkcs1_sha256(n: int, d: int, signing_input: bytes) -> bytes:
    """Used by the tests to mint tokens with a generated key; production never signs RS256 here."""
    k = (n.bit_length() + 7) // 8
    t = SHA256_DIGESTINFO + hashlib.sha256(signing_input).digest()
    em = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    return pow(_int(em), d, n).to_bytes(k, "big")


def decode_unverified(token: str) -> tuple[dict, dict, bytes, bytes]:
    try:
        h, p, s = token.split(".")
    except ValueError:
        raise JwtError("malformed token")
    header = json.loads(b64url_decode(h)); payload = json.loads(b64url_decode(p))
    return header, payload, (h + "." + p).encode(), b64url_decode(s)


class Jwks:
    """Keys by kid from a JWKS document; `fetch` returns the JSON of the JWKS URL (injected for tests)."""

    def __init__(self, fetch, jwks_url: str, ttl_s: int = 3600):
        self.fetch, self.url, self.ttl = fetch, jwks_url, ttl_s
        self._keys: dict[str, tuple[int, int]] = {}; self._at = 0.0

    def _refresh(self):
        doc = self.fetch(self.url)
        keys = {}
        for k in doc.get("keys", []):
            if k.get("kty") != "RSA" or k.get("use", "sig") != "sig":
                continue
            keys[k["kid"]] = (_int(b64url_decode(k["n"])), _int(b64url_decode(k["e"])))
        self._keys, self._at = keys, time.time()

    def key(self, kid: str) -> tuple[int, int]:
        if kid not in self._keys or time.time() - self._at > self.ttl:
            self._refresh()
        if kid not in self._keys:
            raise JwtError("unknown signing key")
        return self._keys[kid]


def verify(token: str, jwks: Jwks, issuers: tuple, audiences: tuple, now: float | None = None, leeway_s: int = 60) -> dict:
    header, payload, signing_input, sig = decode_unverified(token)
    if header.get("alg") != "RS256":
        raise JwtError("algorithm must be RS256")
    n, e = jwks.key(header.get("kid", ""))
    if not rsa_verify_pkcs1_sha256(n, e, signing_input, sig):
        raise JwtError("bad signature")
    now = now or time.time()
    if payload.get("exp", 0) + leeway_s < now:
        raise JwtError("expired")
    if payload.get("nbf", 0) - leeway_s > now:
        raise JwtError("not yet valid")
    if payload.get("iss") not in issuers:
        raise JwtError("issuer not allowed")
    aud = payload.get("aud")
    auds = aud if isinstance(aud, list) else [aud]
    if not any(a in audiences for a in auds):
        raise JwtError("audience not allowed")
    return payload


def openid_jwks_url(fetch, issuer_config_url: str) -> str:
    return fetch(issuer_config_url)["jwks_uri"]
