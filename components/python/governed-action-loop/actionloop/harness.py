"""The action loop harness.

The runtime shape of an agent: admit, think, act with the three hooks in fixed order, return, stop with a
typed reason. Session state lives in the control layer (SQLite here, any store later), never in the
worker; a killed session resumes from it. A consumer supplies a principal, a signed catalog, a bundle and
handlers behind the Gateway; it cannot register a fourth hook, reorder the three, or reach a handler
outside them: `before_call`, `after_call` and `record` are private to this module and covered by the
parity test in the conformance suite.
"""
from __future__ import annotations
import json, sqlite3, time, uuid
from dataclasses import dataclass, field
from . import catalog as C, policy as P, dataguard as DG, signing
from .audit import AuditChain
from .gateway import FakeGateway
from .identity import IdentityLibrary, PrincipalChain
from .kill import KillSwitches


class StopReason(str):
    pass


STOPS = ("budget.tokens", "budget.tool_calls", "budget.time", "budget.money", "kill.run", "kill.board", "kill.consumer",
         "ladder.violation", "taint.forbids_tier", "handler.errors", "loop.detected", "vendor.refusal", "input.blocked",
         "human.interrupt", "claim.revoked", "confirmation.declined", "turn.complete", "needs.input")


class HarnessError(Exception):
    pass


@dataclass
class Budget:
    tokens: int
    tool_calls: int
    time_s: int
    money: float = 0.0
    used_tokens: int = 0
    used_tool_calls: int = 0
    started: float = field(default_factory=time.time)
    used_money: float = 0.0

    def check_tokens_available(self):
        if self.used_tokens >= self.tokens: raise Stop("budget.tokens")

    def spend_tokens(self, n):
        self.used_tokens += n
        if self.used_tokens > self.tokens: raise Stop("budget.tokens")

    def spend_call(self):
        self.used_tool_calls += 1
        if self.used_tool_calls > self.tool_calls: raise Stop("budget.tool_calls")

    def check_time(self):
        if time.time() - self.started > self.time_s: raise Stop("budget.time")

    def to_json(self):
        return {"tokens": {"limit": self.tokens, "used": self.used_tokens}, "tool_calls": {"limit": self.tool_calls, "used": self.used_tool_calls},
                "time_s": {"limit": self.time_s, "used": int(time.time() - self.started)}, "money": {"limit": self.money, "used": self.used_money}}


class Stop(Exception):
    def __init__(self, reason: str, detail: str = ""):
        if reason not in STOPS: raise HarnessError(f"unknown stop reason {reason}")
        super().__init__(reason); self.reason, self.detail = reason, detail


@dataclass
class Session:
    id: str
    consumer: str
    chain: PrincipalChain
    board: str
    ticket_key: str | None
    catalog_hash: str
    bundle_version: int
    ladder: str
    budget: Budget
    tainted: bool = False
    taint_sources: list = field(default_factory=list)
    pending: dict | None = None
    seq: int = 0
    runtime_session_id: str = field(default_factory=lambda: "rts_" + uuid.uuid4().hex[:12])
    trace_id: str = field(default_factory=lambda: "trace_" + uuid.uuid4().hex[:16])
    run_id: str = field(default_factory=lambda: "run_" + uuid.uuid4().hex[:12])

    def to_json(self) -> dict:
        return {"v": 2, "id": self.id, "consumer": self.consumer, "chain": self.chain.tags(), "board": self.board, "ticket_key": self.ticket_key,
                "catalog_hash": self.catalog_hash, "bundle_version": self.bundle_version, "ladder": self.ladder,
                "taint": {"tainted": self.tainted, "sources": self.taint_sources}, "budget": self.budget.to_json(), "pending": self.pending,
                "last_seq": self.seq, "runtime_session_id": self.runtime_session_id, "trace_id": self.trace_id, "run_id": self.run_id}


class SessionStore:
    """Session state beside the fleet, never in the worker that runs the model."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        conn.execute("CREATE TABLE IF NOT EXISTS session (id TEXT PRIMARY KEY, body TEXT, updated REAL)")
        conn.commit()

    def save(self, s: Session):
        self.conn.execute("INSERT OR REPLACE INTO session VALUES (?,?,?)", (s.id, json.dumps(s.to_json()), time.time())); self.conn.commit()

    def load_json(self, sid: str) -> dict | None:
        r = self.conn.execute("SELECT body FROM session WHERE id=?", (sid,)).fetchone()
        return json.loads(r[0]) if r else None


@dataclass(frozen=True)
class CallContext:
    session: Session
    tool: dict
    args: dict
    tier: str
    env: dict
    traceparent: str


Allow, Deny, Pending = "Allow", "Deny", "Pending"


class Harness:
    def __init__(self, *, consumer: str, signed_catalog: signing.Signed, bundle: P.Bundle, key: signing.LocalKey, gateway: FakeGateway,
                 identity: IdentityLibrary, audit: AuditChain, kills: KillSwitches, sessions: SessionStore, telemetry=None, env: str = "sandbox",
                 result_shapes: dict | None = None, resource_fn=None):
        signing.verify(signed_catalog, key)  # an unsigned or tampered catalog never loads
        self.consumer, self.catalog, self.bundle, self.gateway = consumer, signed_catalog, bundle, gateway
        self.identity, self.audit, self.kills, self.sessions, self.telemetry, self.env = identity, audit, kills, sessions, telemetry, env
        self.result_shapes = result_shapes or {}
        self.resource_fn = resource_fn  # a consumer may add resource attributes (never principal or session fields) for its rules
        self._hook_order: list[str] = []  # written by the private hooks; read by the parity test

    # ---------------- admit ----------------
    def admit(self, token: str, board: str, ticket_key: str | None, budget: Budget, ladder: str | None = None) -> Session:
        chain = self.identity.resolve(token, self.consumer)
        s = Session(id="ses_" + uuid.uuid4().hex[:12], consumer=self.consumer, chain=chain, board=board, ticket_key=ticket_key,
                    catalog_hash=self.catalog.hash, bundle_version=self.bundle.version, ladder=ladder or chain.agent.ladder, budget=budget)
        scope = self.kills.state(self.consumer, board, s.run_id)
        if scope:
            self._rec(s, "admit", decision="deny", deny_code=f"kill.{scope}")
            raise Stop(f"kill.{scope}")
        self._rec(s, "admit", decision="allow")
        self.sessions.save(s)
        return s

    # ---------------- act ----------------
    def call(self, s: Session, name: str, args: dict, refs: dict | None = None, phase: str = "execute") -> dict:
        """One tool call through the fixed hook order. Returns the guarded result or raises Stop."""
        self._hook_order = []
        s.budget.check_time()
        traceparent = f"00-{s.trace_id}-{uuid.uuid4().hex[:16]}-01"
        ctx, verdict, decision = self._before_call(s, name, args, refs or {}, traceparent)
        if verdict == Deny:
            self._record(ctx, "decision", decision, None)
            if decision.deny_code and decision.deny_code.startswith("kill."):
                raise Stop(decision.deny_code)
            if decision.deny_code == "taint_ceiling":
                raise Stop("taint.forbids_tier", name)
            if decision.deny_code == "ladder_ceiling":
                raise Stop("ladder.violation", name)
            return {"denied": True, "code": decision.deny_code, "policy_ids": list(decision.policy_ids)}
        if verdict == Pending:
            s.pending = {"tool": name, "args": args, "tier": ctx.tier, "hash": signing.sha256({"tool": name, "args": args})}
            self.sessions.save(s)
            self._record(ctx, "intent", decision, None)
            raise Stop("needs.input", f"{ctx.tier} confirmation for {name}")
        if ctx.tier != "R":
            self._record(ctx, "intent", decision, None)  # W tiers: no dispatch without an Intent record
        s.budget.spend_call()
        ref = self.identity.mint_reference(s.chain, audience=ctx.tool["target"], run_id=s.run_id)
        try:
            gw = self.gateway.tools_call(name, ctx.args, ctx.env, decision, ref, s.run_id)
        except Exception as e:  # the handler protocol: an upstream failure is a typed stop with a record, never a raw exception into the consumer
            self._record(ctx, "decision", P.Decision(decision.allow, decision.policy_ids, "handler_error", ctx.tier), None)
            self.sessions.save(s)
            raise Stop("handler.errors", f"{name}: {type(e).__name__}")
        if self.telemetry:
            self.telemetry.gateway_call(s.consumer, s.board, s.ticket_key, phase)
        if gw.result is None:
            self._record(ctx, "decision", gw.decision, None, span=gw.span_id)
            return {"denied": True, "code": gw.decision.deny_code, "by": "gateway"}
        guarded = self._after_call(ctx, gw.result)
        self._record(ctx, "decision", decision, guarded, span=gw.span_id)
        self.sessions.save(s)
        return guarded

    # ---------------- the three hooks: private, fixed composition ----------------
    def _before_call(self, s: Session, name: str, args: dict, refs: dict, traceparent: str):
        self._hook_order.append("before_call")
        scope = self.kills.state(self.consumer, s.board, s.run_id)                      # kill.state
        if scope:
            return CallContext(s, {"name": name, "target": name.partition("___")[0], "tier": "R"}, args, "R", {}, traceparent), Deny, P.Decision(False, ("kill",), f"kill.{scope}")
        entry = C.lookup(self.catalog, name)                                              # catalog.lookup
        validated = C.validate_args(entry, args)                                          # schema.validate
        resource = {"board": s.board, "ticket": s.ticket_key}
        if self.resource_fn:
            extra = self.resource_fn(s) or {}
            resource.update({k: v for k, v in extra.items() if k not in ("board", "ticket")})
        env = {"principal": s.chain.tags(), "action": name, "action_id": entry["action_id"], "tier": entry["tier"], "resource": resource,
               "context": {"input": validated}, "session": {"tainted": s.tainted, "ladder": s.ladder, "id": s.id}, "refs": refs}
        decision = P.decide(self.bundle, env)                                              # policy.decide
        ctx = CallContext(s, entry, validated, entry["tier"], env, traceparent)
        if not decision.allow:
            if decision.deny_code == "confirmation_required":
                return ctx, Pending, decision                                              # W1: elicitation raised here only
            return ctx, Deny, decision
        return ctx, Allow, decision

    def _after_call(self, ctx: CallContext, raw: dict) -> dict:
        self._hook_order.append("after_call")
        shape = self.result_shapes.get(ctx.tool["name"], {k: True for k in raw})
        g = DG.after_call(raw, shape)                                                      # project → classify → mask → score
        if g.taint and not ctx.session.tainted:
            ctx.session.tainted = True
            ctx.session.taint_sources.append(f"upstream:{ctx.tool['target']}")             # session.taint_if(score)
        return {"data": g.masked_for_model, "pii_classes": g.pii_classes, "score": g.score, "tainted": g.taint}

    def _record(self, ctx: CallContext, event: str, decision: P.Decision, result: dict | None, span: str | None = None):
        self._hook_order.append("record")
        s = ctx.session; s.seq += 1
        self.audit.record(consumer=s.consumer, env=self.env, event=event, tool=ctx.tool.get("name"), tier=ctx.tier,
                          decision="allow" if decision.allow else "deny", deny_code=decision.deny_code, policy_ids=list(decision.policy_ids),
                          chain=s.chain.tags(), session=s.id, board=s.board, ticket=s.ticket_key, taint=s.tainted, seq=s.seq,
                          traceparent=ctx.traceparent, runtime_session_id=s.runtime_session_id, trace_id=s.trace_id, span_id=span,
                          intent_seq=None, result_summary=(None if result is None else {"pii_classes": result.get("pii_classes"), "score": result.get("score")}))

    def _rec(self, s: Session, event: str, **kw):
        s.seq += 1
        self.audit.record(consumer=s.consumer, env=self.env, event=event, chain=s.chain.tags(), session=s.id, board=s.board, ticket=s.ticket_key,
                          seq=s.seq, runtime_session_id=s.runtime_session_id, trace_id=s.trace_id, taint=s.tainted, **kw)

    # ---------------- taint, confirmation, stop, resume ----------------
    def taint(self, s: Session, sources: list, reason: str):
        if sources:
            s.tainted = True; s.taint_sources = sorted(set(s.taint_sources) | set(sources))
        self._rec(s, "taint.set", sources=list(sources), reason=reason); self.sessions.save(s)

    def confirm(self, s: Session, by_human: str, expected_hash: str) -> str:
        """W1 confirmation by the acting person, bound to the hash they saw; consumed once (replay refused)."""
        if not s.pending or s.pending["hash"] != expected_hash:
            raise HarnessError("no pending request with that hash")
        if by_human != s.chain.human.id:
            raise HarnessError("a W1 confirmation must come from the acting person")
        ref = "conf_" + uuid.uuid4().hex[:12]
        self._rec(s, "confirmation", by=by_human, hash=expected_hash, ref=ref)
        s.pending = None; self.sessions.save(s)
        return ref

    def clear_taint_by_confirmation(self, s: Session, by_human: str, segment_hash: str):
        """The scope confirmation: the acting person accepts the foreign instructions, hash-bound, for this run only."""
        if by_human != s.chain.human.id:
            raise HarnessError("only the assignee can confirm foreign instructions")
        s.tainted = False
        self._rec(s, "scope.confirmed", by=by_human, hash=segment_hash); self.sessions.save(s)

    def end(self, s: Session, reason: str, detail: str = ""):
        if reason not in STOPS: raise HarnessError("unknown stop reason")
        self._rec(s, "stop", reason=reason, detail=detail); self.sessions.save(s)

    def resume(self, sid: str, token: str) -> Session:
        """After a worker kill: rebuild the session from the control layer's state."""
        j = self.sessions.load_json(sid)
        if not j: raise HarnessError("unknown session")
        chain = self.identity.resolve(token, self.consumer)
        if chain.human.id != j["chain"]["human"]:
            raise HarnessError("a session resumes only for the person it was admitted for")
        b = j["budget"]
        budget = Budget(b["tokens"]["limit"], b["tool_calls"]["limit"], b["time_s"]["limit"], b["money"]["limit"], b["tokens"]["used"], b["tool_calls"]["used"])
        s = Session(id=j["id"], consumer=j["consumer"], chain=chain, board=j["board"], ticket_key=j["ticket_key"], catalog_hash=j["catalog_hash"],
                    bundle_version=j["bundle_version"], ladder=j["ladder"], budget=budget, tainted=j["taint"]["tainted"], taint_sources=j["taint"]["sources"],
                    pending=j["pending"], seq=j["last_seq"], runtime_session_id=j["runtime_session_id"], trace_id=j["trace_id"], run_id=j["run_id"])
        if s.catalog_hash != self.catalog.hash:
            raise HarnessError("catalog changed under the session; refuse")
        self._rec(s, "resume")
        return s
