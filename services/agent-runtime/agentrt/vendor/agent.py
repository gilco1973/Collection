"""The incident first-read agent: a template (data), tools (called only through the harness), a harness (the loop).

The agent is glue and small on purpose. The template says what it is and may call; the harness enforces tiers,
taint, budgets and the record; the engine (the think step) answers from fenced sources and cites them. Nothing
here decides anything on its own.
"""
from __future__ import annotations
import json, os, re
from actionloop import catalog as C
from actionloop.harness import Budget, Harness, Session, Stop
from engine import RulesEngine
from guard import Context

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_KEYS = ("name", "role", "ladder", "stages", "tools", "never", "budget")


def load_template(path: str | None = None) -> dict:
    """TEMPLATE.md as data: its first ```json block, with every key an agent needs present."""
    text = open(path or os.path.join(HERE, "TEMPLATE.md"), encoding="utf-8").read()
    block = re.search(r"```json\n(.*?)\n```", text, re.S)
    if not block:
        raise ValueError("TEMPLATE.md has no ```json block")
    t = json.loads(block.group(1))
    missing = [k for k in TEMPLATE_KEYS if k not in t]
    if missing:
        raise ValueError(f"the template is missing {missing}")
    return t


def tool_name(t: dict) -> str:
    return f"{t['target']}___{t['op']}"


def catalog_from(template: dict) -> tuple[list, set, dict]:
    """Tool declarations, contract operations and result shapes for the harness, all from the template's `tools`."""
    decls = [C.ToolDecl(t["target"], t["op"], t["tier"], t["contract"], t["permission"], t["args"]) for t in template["tools"]]
    return decls, {t["contract"] for t in template["tools"]}, {tool_name(t): t["result"] for t in template["tools"]}


def budget_from(template: dict) -> Budget:
    return Budget(**template["budget"])


class FirstReadAgent:
    """Read the ticket and the last deploy (R), think (cited), propose (refused on taint), post the read (W1, confirmed once)."""

    def __init__(self, template: dict, harness: Harness, engine=None):
        self.template, self.harness, self.engine = template, harness, engine or RulesEngine()

    def run(self, s: Session, ticket_key: str, service: str) -> dict:
        ctx = Context()
        ticket = self.harness.call(s, "tickets___get", {"key": ticket_key})
        t = ticket["data"]
        ctx.add("ticket", ticket_key, f"{t.get('summary') or t.get('title') or ''}: {t.get('description') or t.get('body') or ''}", "tickets")
        deploy = self.harness.call(s, "deploys___recent", {"service": service})["data"]
        m = deploy.get("minutes_before_trigger")
        minutes = int(m) if m is not None else None
        if minutes is None:
            ctx.add("deploy", "none", f"no finished deploy of {deploy.get('service')} is on record. {deploy.get('notes', '')}", "deploys")
        else:
            ctx.add("deploy", str(deploy.get("run_id")), f"deploy #{deploy.get('run_id')} of {deploy.get('service')} finished {minutes} minutes before the trigger"
                    + (" (recent)" if minutes <= 30 else "") + f". {deploy.get('notes', '')}", "deploys")
        first = self.engine.answer("first-read", ctx)
        proposal = self.engine.answer("propose", ctx) if "propose" in self.template["stages"] else None
        body = self.render(first, proposal)
        out = {"first_read": first, "proposal": proposal, "comment": body, "parked": None, "blocked": None, "tainted": s.tainted or ctx.tainted}
        try:
            self.harness.call(s, "tickets___comment", {"key": ticket_key, "body": body})
        except Stop as e:
            if e.reason == "needs.input":
                out["parked"] = {"hash": s.pending["hash"], "tool": s.pending["tool"], "args": dict(s.pending["args"])}
            else:
                out["blocked"] = e.reason
        return out

    def post(self, s: Session, by_human: str, parked: dict) -> dict:
        """The person confirms the exact parked call; the harness consumes the confirmation once."""
        ref = self.harness.confirm(s, by_human, parked["hash"])
        return self.harness.call(s, parked["tool"], parked["args"], refs={"confirmation": ref})

    @staticmethod
    def render(first: dict, proposal: dict | None) -> str:
        lines = [f"First read: {first.get('summary', '')}", f"Hypothesis: {first.get('hypothesis', '')}", f"Claims cited: {len(first.get('claims', []))} · confidence {first.get('confidence', 0):.2f}"]
        if proposal is None:
            lines.append("Proposal: none (this agent does not propose)")
        elif proposal.get("refused"):
            lines.append(f"Proposal: refused ({proposal['refused']})")
        elif proposal.get("kind") == "none":
            lines.append("Proposal: none; no action is supported by the sources")
        else:
            lines.append(f"Proposal (advisory, a person confirms): {proposal['kind']} {proposal.get('args')} · expected {proposal.get('expected_effect')} · undo {proposal.get('undo')}")
        return "\n".join(lines)
