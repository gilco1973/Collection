"""Catalog toolkit.

From a consumer's tool declarations: derive tiers, map permissions, validate the fixtures the pipeline runs
(no-entry handler, restricted argument, unbacked claim), sign with two approvers, and emit the gateway
target definitions and the action ids the bundle uses. Tool names are `target___tool`.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from . import signing
from .policy import action_id, TIERS


class CatalogError(Exception):
    pass


@dataclass
class ToolDecl:
    target: str                 # the gateway target (jira, ado, kb, ...)
    tool: str                   # the operation
    tier: str                   # R | W1 | W2 | MONEY
    contract_op: str            # the recorded contract operation it binds to
    permission: str             # the permission the policy maps it to
    args: dict                  # arg name -> {"type": "str"|"int"|"list", "required": bool, "restricted": bool}
    reversible: bool = True
    idempotent: bool = True
    egress_class: str = "internal"
    result_size: str = "small"

    @property
    def name(self) -> str:
        return f"{self.target}___{self.tool}"


def build(consumer: str, tools: list[ToolDecl], contract_ops: set[str], max_tools: int = 40) -> dict:
    """Returns the unsigned catalog payload or raises CatalogError with the fixture that failed."""
    if len(tools) > max_tools:
        raise CatalogError(f"tool count {len(tools)} above the declared maximum {max_tools} ")
    names = [t.name for t in tools]
    if len(set(names)) != len(names):
        raise CatalogError("duplicate tool name")
    entries = []
    for t in tools:
        if t.tier not in TIERS:
            raise CatalogError(f"{t.name}: unknown tier {t.tier}")
        if t.contract_op not in contract_ops:
            raise CatalogError(f"{t.name}: unbacked claim, contract operation {t.contract_op} is not recorded (fixture: unbacked-claim)")
        if t.tier == "W1" and not t.reversible:
            raise CatalogError(f"{t.name}: an irreversible W1 is refused")
        entries.append({"name": t.name, "target": t.target, "tool": t.tool, "tier": t.tier, "contract_op": t.contract_op,
                        "permission": t.permission, "args": t.args, "reversible": t.reversible, "idempotent": t.idempotent,
                        "egress_class": t.egress_class, "result_size": t.result_size, "action_id": action_id(t.target, t.tool)})
    return {"consumer": consumer, "tools": entries}


def check(catalog: dict, handlers: dict) -> None:
    """Every entry has a handler (fixture: no-entry handler) and no handler lacks an entry."""
    names = {e["name"] for e in catalog["tools"]}
    missing = names - set(handlers)
    if missing:
        raise CatalogError(f"no handler for {sorted(missing)} (fixture: no-entry handler)")
    extra = set(handlers) - names
    if extra:
        raise CatalogError(f"handler without a catalog entry: {sorted(extra)} (fixture: no-entry)")


def validate_args(entry: dict, args: dict) -> dict:
    """Schema validation before policy . Restricted arguments may not be supplied by the model (fixture: restricted-arg)."""
    out = {}
    for name, spec in entry["args"].items():
        if spec.get("required") and name not in args:
            raise CatalogError(f"{entry['name']}: missing argument {name}")
        if name in args:
            v = args[name]
            t = spec.get("type", "str")
            ok = (t == "str" and isinstance(v, str)) or (t == "int" and isinstance(v, int) and not isinstance(v, bool)) or (t == "list" and isinstance(v, list))
            if not ok:
                raise CatalogError(f"{entry['name']}: argument {name} is not {t}")
            if spec.get("restricted"):
                raise CatalogError(f"{entry['name']}: argument {name} is restricted and may not be supplied (fixture: restricted-arg)")
            out[name] = v
    unknown = set(args) - set(entry["args"])
    if unknown:
        raise CatalogError(f"{entry['name']}: unknown arguments {sorted(unknown)}")
    return out


def sign(catalog: dict, key: signing.LocalKey, approvers: list[str]) -> signing.Signed:
    return signing.sign(catalog, key, approvers)


def emit_targets(catalog: dict) -> dict:
    """What the toolkit hands the configuration standard: one Gateway target per upstream, its tools, and the action ids."""
    targets: dict[str, dict] = {}
    for e in catalog["tools"]:
        t = targets.setdefault(e["target"], {"target": e["target"], "tools": [], "action_ids": [], "credential": "reference-per-call"})
        t["tools"].append(e["tool"]); t["action_ids"].append(e["action_id"])
    return targets


def lookup(signed: signing.Signed, name: str) -> dict:
    for e in signed.payload["tools"]:
        if e["name"] == name:
            return e
    raise CatalogError(f"{name}: no catalog entry")
