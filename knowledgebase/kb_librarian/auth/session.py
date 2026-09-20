"""Stateless, HMAC-signed session and login-transaction cookies.

A cookie is ``base64url(json) . hex(hmac_sha256(secret, base64url(json)))``. The server keeps no
session table: the signature proves the payload was issued here, ``kind`` says what for (a login
transaction can never pass as a session), ``iat``/``exp`` bound its life. Nothing in the payload is
secret (name, e-mail, subject, issuer, operator flag, session epoch), so it is signed, not encrypted.
Any malformed input — wrong MAC, bad base64, non-ASCII bytes, wrong kind, expired — reads as "no
cookie", never as an error.
"""

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

SESSION_COOKIE = "kb_session"
LOGIN_COOKIE = "kb_login"  # the in-flight authorization request: state, nonce, PKCE verifier, return path
LOGIN_TTL_S = 10 * 60
MAX_NEXT_CHARS = 2048
MAX_CLAIM_CHARS = 200  # name / e-mail as stored in the cookie (browsers drop cookies over ~4 KB)
MAX_SUB_CHARS = 255


@dataclass(frozen=True)
class User:
    sub: str
    iss: str
    name: str
    email: str | None = None
    operator: bool = False  # granted at sign-in from the IdP's group claim; re-evaluated at the next sign-in
    epoch: int = 0  # the reader's session epoch when the cookie was issued; a bump revokes every earlier cookie

    @property
    def storage_key(self) -> str:
        """Issuer-qualified identity: ``sub`` is unique only within one issuer."""
        return f"{self.iss}\0{self.sub}"

    def as_dict(self) -> dict[str, str | bool | None]:
        return {"sub": self.sub, "name": self.name, "email": self.email, "operator": self.operator}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(secret: str, body: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest().encode("ascii")


def sign(payload: dict[str, Any], secret: str, ttl_s: int, kind: str, now: float | None = None) -> str:
    """Serialise ``payload`` tagged ``kind`` with an expiry ``ttl_s`` seconds from now, and sign it."""
    stamp = time.time() if now is None else now
    record = {**payload, "kind": kind, "iat": int(stamp), "exp": int(stamp + ttl_s)}
    body = _b64(json.dumps(record, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_mac(secret, body).decode('ascii')}"


def verify(token: str | None, secret: str, kind: str, now: float | None = None) -> dict[str, Any] | None:
    """The payload of a ``kind`` cookie this server signed and that has not expired; ``None`` otherwise."""
    if not token or "." not in token:
        return None
    body, _, mac = token.rpartition(".")
    try:
        if not hmac.compare_digest(mac.encode("ascii"), _mac(secret, body)):
            return None
        payload = json.loads(_unb64(body))
    except (ValueError, UnicodeError):  # binascii.Error is a ValueError; non-ASCII bytes are UnicodeError
        return None
    if not isinstance(payload, dict) or payload.get("kind") != kind or not isinstance(payload.get("exp"), int):
        return None
    if payload["exp"] <= (time.time() if now is None else now):
        return None
    return payload


def user_from_session(token: str | None, secret: str) -> User | None:
    payload = verify(token, secret, "session")
    if payload is None:
        return None
    sub, iss = payload.get("sub"), payload.get("iss")
    if not isinstance(sub, str) or not sub or len(sub) > MAX_SUB_CHARS or not isinstance(iss, str) or not iss:
        return None
    email, epoch = payload.get("email"), payload.get("epoch")
    return User(
        sub=sub,
        iss=iss,
        name=str(payload.get("name") or sub)[:MAX_CLAIM_CHARS],
        email=email[:MAX_CLAIM_CHARS] if isinstance(email, str) else None,
        operator=payload.get("operator") is True,  # a bool only: "true", 1 and the like grant nothing
        epoch=epoch if isinstance(epoch, int) and not isinstance(epoch, bool) else 0,
    )


def safe_return_path(candidate: str | None) -> str:
    """Only a bounded, same-origin absolute path may be a post-login destination (no open redirect)."""
    if not candidate or len(candidate) > MAX_NEXT_CHARS or not candidate.startswith("/"):
        return "/"
    if candidate.startswith("//") or "\\" in candidate or any(c in candidate for c in "\r\n\t"):
        return "/"
    return candidate
