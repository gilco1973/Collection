"""Signing: a local key for the sandbox, an asymmetric KMS key for staging and production, the same two methods.

Two-approver signing of catalogs and rule bundles. A signature is an HMAC over the canonical JSON of
the payload; a signed object carries the payload, the hash and one signature per approver. Verification
requires two distinct approvers and refuses any tampering. Standard library only.
"""
from __future__ import annotations
import hashlib, hmac, json
from dataclasses import dataclass, field


def canonical(obj) -> bytes:
    """The bytes a hash and a signature are over. A lone surrogate (valid JSON text that UTF-8 refuses) is passed
    through rather than raised on, so hashing is total; `catalog.validate_args` is where such text is refused."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8", "surrogatepass")


def sha256(obj) -> str:
    return "sha256:" + hashlib.sha256(canonical(obj)).hexdigest()


class LocalKey:
    """One signing key held under the privileged-access rule. Replace with KMS or an HSM in production."""

    def __init__(self, key_id: str, secret: bytes):
        self.key_id, self._secret = key_id, secret

    def sign(self, payload_hash: str, approver: str) -> str:
        return hmac.new(self._secret, f"{payload_hash}|{approver}".encode(), hashlib.sha256).hexdigest()

    def verify(self, payload_hash: str, approver: str, sig: str) -> bool:
        return hmac.compare_digest(self.sign(payload_hash, approver), sig)


class KmsKey:
    """The same two methods on an asymmetric KMS key: Sign and Verify through the JSON protocol, SigV4 from the
    task role. `aws` is an `AwsJson`-like object (`call(service, endpoint_prefix, target, payload) -> dict`, the
    aws-sigv4 component's). The private key never leaves KMS; a signature is base64 as KMS returns it."""

    def __init__(self, aws, key_id: str, algorithm: str = "RSASSA_PKCS1_V1_5_SHA_256"):
        self.aws, self.key_id, self.algorithm = aws, key_id, algorithm

    @staticmethod
    def _message(payload_hash: str, approver: str) -> str:
        import base64
        return base64.b64encode(f"{payload_hash}|{approver}".encode()).decode()

    def sign(self, payload_hash: str, approver: str) -> str:
        r = self.aws.call("kms", "kms", "TrentService.Sign", {"KeyId": self.key_id, "Message": self._message(payload_hash, approver), "MessageType": "RAW", "SigningAlgorithm": self.algorithm})
        if "Signature" not in r:
            raise SigningError("KMS returned no signature")
        return r["Signature"]

    def verify(self, payload_hash: str, approver: str, sig: str) -> bool:
        try:
            r = self.aws.call("kms", "kms", "TrentService.Verify", {"KeyId": self.key_id, "Message": self._message(payload_hash, approver), "MessageType": "RAW", "SigningAlgorithm": self.algorithm, "Signature": sig})
        except Exception:  # KMS answers an invalid signature with an error, which is a false, never a raise
            return False
        return bool(r.get("SignatureValid"))


class FakeKms:
    """KMS in memory behind the same `call`: one key, deterministic signatures, invalid ones refused with an error as KMS does."""

    def __init__(self, key_id: str, secret: bytes = b"fake-kms-key"):
        self.key_id, self._secret, self.calls = key_id, secret, []

    def call(self, service: str, endpoint_prefix: str, target: str, payload: dict, content_type: str = "") -> dict:
        self.calls.append(target)
        if payload.get("KeyId") != self.key_id:
            raise SigningError("NotFoundException: unknown key")
        sig = hmac.new(self._secret, payload["Message"].encode(), hashlib.sha256).hexdigest()
        if target == "TrentService.Sign":
            return {"KeyId": self.key_id, "Signature": sig, "SigningAlgorithm": payload["SigningAlgorithm"]}
        if target == "TrentService.Verify":
            if not hmac.compare_digest(sig, payload.get("Signature", "")):
                raise SigningError("KMSInvalidSignatureException")
            return {"KeyId": self.key_id, "SignatureValid": True}
        raise SigningError(f"unknown target {target}")


@dataclass
class Signed:
    payload: dict
    hash: str
    key_id: str
    signatures: dict = field(default_factory=dict)  # approver -> signature

    def to_json(self) -> dict:
        return {"payload": self.payload, "hash": self.hash, "key_id": self.key_id, "signatures": dict(self.signatures)}

    @staticmethod
    def from_json(d: dict) -> "Signed":
        return Signed(d["payload"], d["hash"], d["key_id"], dict(d["signatures"]))


class SigningError(Exception):
    pass


def sign(payload: dict, key, approvers: list[str]) -> Signed:
    if len(set(approvers)) < 2:
        raise SigningError("two distinct approvers are required")
    h = sha256(payload)
    return Signed(payload, h, key.key_id, {a: key.sign(h, a) for a in approvers})


def verify(signed: Signed, key) -> None:
    """Raises SigningError unless the payload matches its hash and carries two valid, distinct signatures."""
    if signed.key_id != key.key_id:
        raise SigningError("unknown key")
    if sha256(signed.payload) != signed.hash:
        raise SigningError("payload does not match its hash")
    valid = [a for a, s in signed.signatures.items() if key.verify(signed.hash, a, s)]
    if len(set(valid)) < 2:
        raise SigningError("fewer than two valid signatures")
