"""One governed agent, end to end, offline: build it, admit a person, read, propose a write, confirm once, verify.

    python3 example.py

Everything a consumer supplies is here: a principal (from the fake IdP), a signed catalog of tools by tier, a rule
bundle, handlers behind the gateway, and a result shape per tool. Everything the loop enforces is in `actionloop`.
"""
from __future__ import annotations
import sqlite3
from dataclasses import dataclass
from actionloop import catalog as C, policy as P, signing
from actionloop.audit import AuditChain
from actionloop.gateway import FakeGateway
from actionloop.harness import Budget, Harness, SessionStore, Stop
from actionloop.identity import Agent, AgentRegistry, AuthorizerConfig, FakeIdP, IdentityLibrary
from actionloop.kill import KillSwitches
from actionloop.telemetry import Telemetry

AGENT = "agent:example-helper"
ISSUER = "https://idp.example.internal"

TOOLS = [
    C.ToolDecl("tickets", "get", "R", "tickets.get", "tickets:read", {"key": {"type": "str", "required": True}}),
    C.ToolDecl("tickets", "comment", "W1", "tickets.comment", "tickets:write", {"key": {"type": "str", "required": True}, "body": {"type": "str", "required": True}}),
    C.ToolDecl("deploy", "rollback", "W2", "deploy.rollback", "deploy:execute", {"service": {"type": "str", "required": True}, "run_id": {"type": "int", "required": True}}, reversible=True),
]
CONTRACT_OPS = {"tickets.get", "tickets.comment", "deploy.rollback"}
RESULT_SHAPES = {"tickets___get": {"key": "id", "title": True, "body": True}, "tickets___comment": {"id": "id"}, "deploy___rollback": {"run_id": "id", "status": True}}

RULES = {"name": "example.helper", "version": 1, "rules": [
    {"id": "p.read.operators", "effect": "permit", "action": {"tier": "R"}, "when": [["principal.roles", "contains", "operator"]]},
    {"id": "p.w1.operators", "effect": "permit", "action": {"tier": "W1"}, "when": [["principal.roles", "contains", "operator"]]},
    {"id": "p.w2.approved_by_another", "effect": "permit", "action": {"tier": "W2"}, "when": [["refs.approver", "exists"], ["refs.approver", "ne", "$principal.human"]]},
    {"id": "f.money", "effect": "forbid", "action": {"tier": "MONEY"}},
]}


class FakeTickets:
    """An in-memory system of record; a real one is an HTTP client with the same two methods."""

    def __init__(self):
        self.tickets = {"T-1": {"key": "T-1", "title": "Checkout slow", "body": "p95 up since the 14:00 deploy"}}
        self.comments: list[dict] = []

    def get(self, args, credential):
        return dict(self.tickets[args["key"]])

    def comment(self, args, credential):
        self.comments.append({"key": args["key"], "body": args["body"], "by": credential["on_behalf_of"]})
        return {"id": f"c{len(self.comments)}"}


@dataclass
class Wired:
    harness: Harness
    idp: FakeIdP
    tickets: FakeTickets
    counter: P.DisagreementCounter
    audit: AuditChain
    kills: KillSwitches
    conn: sqlite3.Connection

    def token(self, user: str, roles=("operator",)) -> str:
        return self.idp.issue(user, {"name": user, "roles": list(roles)}, client_id="example-app")


def build(db: str = ":memory:") -> Wired:
    conn = sqlite3.connect(db)
    key = signing.LocalKey("k-local", b"a-32-byte-secret-held-under-privileged-access")
    signed = C.sign(C.build("example.helper", TOOLS, CONTRACT_OPS), key, ["approver-a", "approver-b"])
    bundle = P.Bundle(RULES)
    idp = FakeIdP(ISSUER, b"idp-secret", ["example-app"])
    registry = AgentRegistry(); registry.register(Agent(AGENT, owner="team-example", road="R2", ladder="L2", channel="operator"))
    identity = IdentityLibrary(idp, AuthorizerConfig(ISSUER, ("example-app",)), registry)
    audit = AuditChain(conn); kills = KillSwitches(conn, audit); counter = P.DisagreementCounter()
    gateway = FakeGateway("gw", bundle, identity, counter, mode="ENFORCE")
    tickets = FakeTickets()
    gateway.register_target("tickets", {"get": tickets.get, "comment": tickets.comment})
    gateway.register_target("deploy", {"rollback": lambda a, c: {"run_id": a["run_id"], "status": "started"}})
    C.check(signed.payload, {n: True for n in gateway.tools_list()})
    harness = Harness(consumer=AGENT, signed_catalog=signed, bundle=bundle, key=key, gateway=gateway, identity=identity, audit=audit,
                      kills=kills, sessions=SessionStore(conn), telemetry=Telemetry(conn), env="sandbox", result_shapes=RESULT_SHAPES)
    return Wired(harness, idp, tickets, counter, audit, kills, conn)


def main():
    w = build(); h = w.harness
    s = h.admit(w.token("u_dana"), board="checkout", ticket_key="T-1", budget=Budget(tokens=20000, tool_calls=20, time_s=300))
    print("admitted", s.id, "ladder", s.ladder)
    r = h.call(s, "tickets___get", {"key": "T-1"})
    print("read:", r["data"]["title"], "| pii:", r["pii_classes"], "| tainted:", r["tainted"])
    try:
        h.call(s, "tickets___comment", {"key": "T-1", "body": "Looking at the 14:00 deploy."})
    except Stop as e:
        print("W1 parked:", e.reason, "| hash", s.pending["hash"][:20], "...")
    ref = h.confirm(s, "u_dana", s.pending["hash"])
    r = h.call(s, "tickets___comment", {"key": "T-1", "body": "Looking at the 14:00 deploy."}, refs={"confirmation": ref})
    print("W1 done:", r["data"], "| comments on record:", len(w.tickets.comments))
    d = h.call(s, "deploy___rollback", {"service": "checkout", "run_id": 41})
    print("W2 without approval:", d)
    h.end(s, "turn.complete")
    print("chain verified:", w.audit.verify(), "records | gateway disagreements:", len(w.counter.disagreements))


if __name__ == "__main__":
    main()
