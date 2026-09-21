"""RS256 JSON Web Tokens with the standard library: verification against a JWKS (Entra ID, Bot Framework, any OpenID Connect issuer).

RSA PKCS#1 v1.5 signature verification is integer arithmetic: sig^e mod n must equal the padded DigestInfo of
SHA-256 over the signing input. Keys are fetched from the issuer's OpenID configuration and cached by `kid`;
an unknown `kid` refreshes once. Every claim the standards require is checked: signature, `exp`, `nbf`, `iss`,
`aud`, and the algorithm is pinned to RS256 (no `none`, no HMAC confusion).
"""
from __future__ import annotations
import base64, binascii, hashlib, json, threading, time

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


def _no_constants(name: str):
    raise ValueError(f"{name} is not a number")


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and v not in (float("inf"), float("-inf"))


def decode_unverified(token: str) -> tuple[dict, dict, bytes, bytes]:
    try:
        h, p, s = token.split(".")
    except ValueError:
        raise JwtError("malformed token")
    try:
        header = json.loads(b64url_decode(h), parse_constant=_no_constants); payload = json.loads(b64url_decode(p), parse_constant=_no_constants); sig = b64url_decode(s)
    except (ValueError, UnicodeDecodeError, binascii.Error, RecursionError):
        raise JwtError("malformed token")
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise JwtError("malformed token")
    if "crit" in header:
        raise JwtError("crit extensions are not supported")  # RFC 7515 §4.1.11: an extension we do not understand means refuse
    return header, payload, (h + "." + p).encode(), sig


class Jwks:
    """Keys by kid from a JWKS document; `fetch` returns the JSON of the JWKS URL (injected for tests).

    The cache is refreshed after `ttl_s`, or when a token names a kid it does not hold (key rotation), but never
    more often than `min_refresh_s`: a stranger sending tokens with invented kids cannot make the service hammer
    the provider. When a refresh fails, keys fetched within `max_age_s` keep serving (the provider being unreachable
    for a moment must not sign everyone out); `stale` tells the readiness check the difference."""

    def __init__(self, fetch, jwks_url: str, ttl_s: int = 3600, min_refresh_s: int = 60, max_age_s: int = 86_400):
        self.fetch, self.url, self.ttl, self.min_refresh, self.max_age = fetch, jwks_url, ttl_s, min_refresh_s, max_age_s
        self._keys: dict[str, tuple[int, int]] = {}; self._at = 0.0; self._tried = 0.0; self._lock = threading.Lock()
        self.last_error: str | None = None

    def _refresh(self):
        """Fetches the document and swaps the keys in atomically. A document with no usable RSA signing key, or a
        key without kid, n or e, never replaces the keys already held: the cache is only ever replaced by a better one."""
        doc = self.fetch(self.url)
        keys = {}
        for k in (doc.get("keys") if isinstance(doc, dict) else None) or []:
            if not isinstance(k, dict) or k.get("kty") != "RSA" or k.get("use", "sig") != "sig":
                continue
            if not all(isinstance(k.get(x), str) and k.get(x) for x in ("kid", "n", "e")):
                continue
            try:
                keys[k["kid"]] = (_int(b64url_decode(k["n"])), _int(b64url_decode(k["e"])))
            except (ValueError, binascii.Error):
                continue
        if not keys:
            raise JwtError("JWKS has no signing keys")
        self._keys, self._at, self.last_error = keys, time.time(), None

    @property
    def stale(self) -> bool:
        return time.time() - self._at > self.ttl

    def key(self, kid: str) -> tuple[int, int]:
        """A known key within its refresh time is served from the cache without waiting on anything. Otherwise one
        thread at a time refreshes (never more often than `min_refresh`); the others read the cache meanwhile, so a
        stranger's invented kid never stalls a valid token behind the provider's round trip."""
        now = time.time()
        keys = self._keys
        if kid in keys and now - self._at <= self.ttl:
            return keys[kid]
        failure = None
        if now - self._tried >= self.min_refresh and self._lock.acquire(blocking=False):
            try:
                self._tried = now
                try:
                    self._refresh()
                except Exception as e:  # noqa: BLE001 - the provider or the network; the cache decides what happens next
                    self.last_error = type(e).__name__; failure = e
            finally:
                self._lock.release()
        keys = self._keys
        if kid in keys and now - self._at <= self.max_age:
            return keys[kid]
        if failure is not None:
            raise failure
        raise JwtError("unknown signing key" if kid not in keys else "signing keys too old")

    def refresh_if_due(self) -> bool:
        """For a readiness check: one refresh when the keys are stale and the throttle allows; True when a refresh
        ran (successfully or not: `last_error` says). Never a fetch per call."""
        now = time.time()
        if not self.stale or now - self._tried < self.min_refresh or not self._lock.acquire(blocking=False):
            return False
        try:
            self._tried = now
            try:
                self._refresh()
            except Exception as e:  # noqa: BLE001
                self.last_error = type(e).__name__
            return True
        finally:
            self._lock.release()

    @property
    def usable(self) -> bool:
        """Keys are held and not past their maximum age."""
        return bool(self._keys) and time.time() - self._at <= self.max_age


def verify(token: str, jwks: Jwks, issuers: tuple, audiences: tuple, now: float | None = None, leeway_s: int = 60) -> dict:
    header, payload, signing_input, sig = decode_unverified(token)
    if header.get("alg") != "RS256":
        raise JwtError("algorithm must be RS256")
    n, e = jwks.key(header.get("kid", ""))
    if not rsa_verify_pkcs1_sha256(n, e, signing_input, sig):
        raise JwtError("bad signature")
    now = now or time.time()
    exp, nbf = payload.get("exp"), payload.get("nbf", 0)
    if not _number(exp) or not _number(nbf):
        raise JwtError("exp and nbf must be numbers")
    if exp + leeway_s < now:
        raise JwtError("expired")
    if nbf - leeway_s > now:
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
