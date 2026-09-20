"""The contract record for an external MCP server (PLT-CAT-7, PLT-CAT-10).

An external MCP server is a system of record: it enters the registry with a verified publisher and a key
fingerprint, and a signed allowlist of the tools a consumer may call, each pinned to the hash of its description.
Any change to a description, the publisher or the fingerprint quarantines the server until a person re-verifies.
Descriptions are corpus payload locations: they are scored for injection at load and a scoring one quarantines too.
"""
from __future__ import annotations
import hashlib, json, re
from dataclasses import dataclass, field

MARKERS = ("ignore previous", "ignore all previous", "disregard", "you are now", "system prompt", "run the following",
           "print the token", "print your", "reveal", "exfiltrate", "curl ", "wget ", "rm -rf", "| sh", "&& ")


def injection_score(text: str) -> float:
    t = text.lower()
    return min(1.0, sum(0.34 for m in MARKERS if m in t))


def sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


class ContractError(Exception):
    pass


@dataclass
class Contract:
    """What the registry recorded for one server: name, verified publisher, key fingerprint, and the allowlist
    `harness name -> {"mcp": remote tool name, "description": sha256 of the description as reviewed}`."""
    server: str
    publisher: str
    fingerprint: str
    allow: dict = field(default_factory=dict)
    threshold: float = 0.34

    @classmethod
    def record(cls, server: str, publisher: str, fingerprint: str, tools: list[dict], mapping: dict[str, str]) -> "Contract":
        """Pin the allowlist from a reviewed tools/list: `mapping` is harness name -> remote tool name."""
        by = {t["name"]: t for t in tools}
        allow = {}
        for harness_name, remote in mapping.items():
            if remote not in by:
                raise ContractError(f"{remote} is not on the server's tools/list")
            allow[harness_name] = {"mcp": remote, "description": sha256(by[remote].get("description", ""))}
        return cls(server, publisher, fingerprint, allow)

    def verify(self, tools: list[dict], publisher: str, fingerprint: str) -> list[str]:
        """Problems that quarantine the server; an empty list means every allowed tool is as reviewed."""
        p = []
        if publisher != self.publisher: p.append(f"publisher changed: {publisher!r} is not the verified {self.publisher!r}")
        if fingerprint != self.fingerprint: p.append("key fingerprint changed")
        by = {t["name"]: t for t in tools}
        for harness_name, a in self.allow.items():
            t = by.get(a["mcp"])
            if not t:
                p.append(f"{a['mcp']} is no longer on tools/list"); continue
            desc = t.get("description", "")
            if sha256(desc) != a["description"]: p.append(f"{a['mcp']}: description changed since it was reviewed")
            if injection_score(desc) >= self.threshold: p.append(f"{a['mcp']}: description scores as an injection ({injection_score(desc):.2f})")
        return p

    def remote(self, harness_name: str) -> str:
        if harness_name not in self.allow:
            raise ContractError(f"{harness_name} is not on the signed allowlist")
        return self.allow[harness_name]["mcp"]

    def to_json(self) -> dict:
        return {"server": self.server, "publisher": self.publisher, "fingerprint": self.fingerprint, "allow": self.allow}

    @classmethod
    def from_json(cls, d: dict) -> "Contract":
        return cls(d["server"], d["publisher"], d["fingerprint"], dict(d["allow"]))
