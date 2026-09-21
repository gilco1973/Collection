"""Policy library: in-process evaluation of the signed rule bundle.

A small Cedar-shaped language, deliberately: rules are data with permit/forbid, a principal match, an action
match (by name, tier or all), and `when` conditions over an environment that carries the principal tags,
the action, the tier, the resource, `context.input` (the arguments) and the session. Forbid overrides
permit; the default is deny; every decision names the policies that produced it and a typed deny code.
The same bundle is evaluated in process by the harness and by the (fake) Gateway's Policy engine, and a
disagreement counter compares the two (a zero-disagreement release gate).

Condition triples: [lhs_path, op, rhs] where a path is dotted into the env ("context.input.ticket_key",
"principal.jira_account_id", "session.tainted"); rhs is a literal, or a "$path" reference into the env.
Ops: eq, ne, in, not_in, lte, gte, exists, absent, startswith, is_true, is_false, contains, not_contains.
"""
from __future__ import annotations
from dataclasses import dataclass, field

LADDER_RANK = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}
TIER_MIN_LADDER = {"R": "L1", "W1": "L2", "W2": "L2", "MONEY": "L2"}
TIERS = ("R", "W1", "W2", "MONEY")


class PolicyError(Exception):
    pass


def action_id(target: str, tool: str) -> str:
    """The Cedar-shaped action id the catalog emits: Action::"target___tool"."""
    return f'Action::"{target}___{tool}"'


def _get(env: dict, path: str):
    cur = env
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _rhs(env: dict, v):
    return _get(env, v[1:]) if isinstance(v, str) and v.startswith("$") else v


def _members(v):
    """The collection an `in`/`contains` operand must be: a list, tuple or set. A string is not one (no substring
    test), a missing value is the empty collection, anything else is None and the condition is false."""
    if v is None:
        return ()
    return v if isinstance(v, (list, tuple, set, frozenset)) else None


def _cond(env: dict, c: list) -> bool:
    lhs, op, rhs = c[0], c[1], (c[2] if len(c) > 2 else None)
    a, b = _get(env, lhs), _rhs(env, rhs)
    if op == "eq": return a == b
    if op == "ne": return a != b
    if op == "in": return _members(b) is not None and a in _members(b)
    if op == "not_in": return _members(b) is not None and a not in _members(b)
    if op == "lte": return a is not None and b is not None and a <= b
    if op == "gte": return a is not None and b is not None and a >= b
    if op == "exists": return a is not None
    if op == "absent": return a is None
    if op == "startswith": return isinstance(a, str) and isinstance(b, str) and a.startswith(b)
    if op == "is_true": return a is True
    if op == "is_false": return a is False
    if op == "contains": return isinstance(a, (list, tuple, set, frozenset)) and b is not None and b in a
    if op == "not_contains": return isinstance(a, (list, tuple, set, frozenset)) and b is not None and b not in a
    raise PolicyError(f"unknown op {op}")


@dataclass(frozen=True)
class Decision:
    allow: bool
    policy_ids: tuple
    deny_code: str | None = None
    tier: str | None = None

    def to_json(self) -> dict:
        return {"allow": self.allow, "policy_ids": list(self.policy_ids), "deny_code": self.deny_code, "tier": self.tier}


class Bundle:
    """A signed bundle's payload: {"name","version","rules":[...]}. Rule shape:
    {"id","effect":"permit"|"forbid","principal":{"agent": "..."}|"any","action":{"tier":"R"}|{"names":[...]}|"any","when":[cond,...]}"""

    def __init__(self, payload: dict):
        self.name, self.version, self.rules = payload["name"], payload["version"], payload["rules"]
        for r in self.rules:
            if r["effect"] not in ("permit", "forbid"):
                raise PolicyError(f"rule {r['id']}: bad effect")

    def _matches(self, r: dict, env: dict) -> bool:
        p = r.get("principal", "any")
        if p != "any" and any(_get(env, "principal." + k) != v for k, v in p.items()):
            return False
        a = r.get("action", "any")
        if a != "any":
            if "tier" in a and env["tier"] != a["tier"]: return False
            if "tiers" in a and env["tier"] not in a["tiers"]: return False
            if "names" in a and env["action"] not in a["names"]: return False
        return all(_cond(env, c) for c in r.get("when", []))

    def decide(self, env: dict) -> Decision:
        permits, forbids = [], []
        for r in self.rules:
            try:
                matched = self._matches(r, env)
            except Exception:  # noqa: BLE001 - a condition that cannot be evaluated (a type mismatch, an unknown op) is a deny that names the rule, never a raise into the loop
                return Decision(False, (r.get("id"),), "condition_error", env.get("tier"))
            if matched:
                (permits if r["effect"] == "permit" else forbids).append(r["id"])
        if forbids:
            return Decision(False, tuple(forbids), "forbidden", env["tier"])
        if permits:
            return Decision(True, tuple(permits), None, env["tier"])
        return Decision(False, (), "no_permit", env["tier"])


def structural_checks(env: dict) -> Decision | None:
    """The invariants no bundle can waive: ladder ceilings, the taint ceiling, W tiers need a reference."""
    tier, ladder = env["tier"], env["session"]["ladder"]
    effective = ladder
    if env["session"].get("tainted") and LADDER_RANK[ladder] > 1:
        effective = "L1"  # a tainted session is capped at propose
    if LADDER_RANK[effective] < LADDER_RANK[TIER_MIN_LADDER[tier]]:
        code = "taint_ceiling" if effective != ladder else "ladder_ceiling"
        return Decision(False, ("structural.ladder",), code, tier)
    if tier == "W1" and not env.get("refs", {}).get("confirmation"):
        return Decision(False, ("structural.w1_reference",), "confirmation_required", tier)
    if tier in ("W2", "MONEY") and not env.get("refs", {}).get("approval"):
        return Decision(False, ("structural.w2_reference",), "approval_required", tier)
    return None


def decide(bundle: Bundle, env: dict) -> Decision:
    s = structural_checks(env)
    return s if s else bundle.decide(env)


class DisagreementCounter:
    """Compares the harness's decision with the gateway's on every call."""

    def __init__(self):
        self.total = 0
        self.disagreements: list[dict] = []

    def record(self, action: str, harness: Decision, gateway: Decision) -> None:
        self.total += 1
        if harness.allow != gateway.allow:
            self.disagreements.append({"action": action, "harness": harness.to_json(), "gateway": gateway.to_json()})
