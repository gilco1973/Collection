"""The connector boundary: a gateway with its own policy evaluation (the second rule evaluation).

Holds targets (target -> tool -> handler); on every tools/call it evaluates the same signed bundle the
harness evaluated, in LOG_ONLY or ENFORCE mode, records the decision, feeds the disagreement counter, and
only then runs the handler. A handler receives a token *reference* it redeems with the identity library,
never a credential (no standing credential in a target). A real gateway (an API gateway, an MCP host, a
service mesh) replaces this class; the harness calls it through the same `tools_call` shape.
"""
from __future__ import annotations
import uuid
from dataclasses import dataclass
from . import policy as P
from .identity import IdentityLibrary


class GatewayError(Exception):
    pass


@dataclass
class GatewayResult:
    decision: P.Decision
    result: dict | None
    span_id: str
    mode: str


class FakeGateway:
    def __init__(self, name: str, bundle: P.Bundle, identity: IdentityLibrary, counter: P.DisagreementCounter, mode: str = "LOG_ONLY", authorizer_issuer: str = ""):
        if mode not in ("LOG_ONLY", "ENFORCE"):
            raise GatewayError("mode must be LOG_ONLY or ENFORCE")
        self.name, self.bundle, self.identity, self.counter, self.mode, self.authorizer_issuer = name, bundle, identity, counter, mode, authorizer_issuer
        self.targets: dict[str, dict] = {}
        self.log: list[dict] = []

    def register_target(self, target: str, tools: dict) -> None:
        """tools: tool name -> handler(args, credential) -> dict. A target holds no credential."""
        self.targets[target] = dict(tools)

    def set_mode(self, mode: str) -> None:
        if mode not in ("LOG_ONLY", "ENFORCE"):
            raise GatewayError("bad mode")
        self.mode = mode

    def tools_list(self) -> list[str]:
        return [f"{t}___{tool}" for t, tools in self.targets.items() for tool in tools]

    def tools_call(self, name: str, args: dict, env: dict, harness_decision: P.Decision, reference: str, run_id: str) -> GatewayResult:
        """The Gateway's Policy evaluates the same env the harness built; then the target runs the generated client."""
        target, _, tool = name.partition("___")
        if target not in self.targets or tool not in self.targets[target]:
            raise GatewayError(f"no target tool {name}")
        gw_decision = P.decide(self.bundle, env)
        self.counter.record(name, harness_decision, gw_decision)
        span = "span_" + uuid.uuid4().hex[:12]
        self.log.append({"tool": name, "mode": self.mode, "decision": gw_decision.to_json(), "span": span})
        if self.mode == "ENFORCE" and not gw_decision.allow:
            return GatewayResult(gw_decision, None, span, self.mode)
        if not harness_decision.allow:
            # the harness already denied; the Gateway logs its own view and nothing runs
            return GatewayResult(gw_decision, None, span, self.mode)
        credential = self.identity.redeem(reference, audience=target, run_id=run_id)
        result = self.targets[target][tool](args, credential)
        return GatewayResult(gw_decision, result, span, self.mode)
