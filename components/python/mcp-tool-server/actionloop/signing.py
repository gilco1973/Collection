"""Signing with a local key (the interim before a KMS-backed signer).

Two-approver signing of catalogs and rule bundles. A signature is an HMAC over the canonical JSON of
the payload; a signed object carries the payload, the hash and one signature per approver. Verification
requires two distinct approvers and refuses any tampering. Standard library only.
"""
from __future__ import annotations
import hashlib, hmac, json
from dataclasses import dataclass, field


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


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


def sign(payload: dict, key: LocalKey, approvers: list[str]) -> Signed:
    if len(set(approvers)) < 2:
        raise SigningError("two distinct approvers are required")
    h = sha256(payload)
    return Signed(payload, h, key.key_id, {a: key.sign(h, a) for a in approvers})


def verify(signed: Signed, key: LocalKey) -> None:
    """Raises SigningError unless the payload matches its hash and carries two valid, distinct signatures."""
    if signed.key_id != key.key_id:
        raise SigningError("unknown key")
    if sha256(signed.payload) != signed.hash:
        raise SigningError("payload does not match its hash")
    valid = [a for a, s in signed.signatures.items() if key.verify(signed.hash, a, s)]
    if len(set(valid)) < 2:
        raise SigningError("fewer than two valid signatures")
