"""The think step behind one adapter: a model reasons over a fenced context and returns cited JSON; it never acts.

Three engines share one protocol so a service can run offline, against an internal HTTP endpoint, or against a model
provider by configuration alone:

    engine.answer(stage, ctx, payload) -> {"...stage fields...", "claims": [{"text", "citations": [ids]}], "confidence", "model_ctx"}

`RulesEngine` answers from the context with rules (tests, demonstrations, degraded mode). `ModelEngine` takes any
`complete(system, user) -> text` callable (the model gateway of governed-action-loop, an SDK, an HTTP client), a
registry of stage prompts, and applies the guard: the model sees only `ctx.fenced()`, must return strict JSON, every
claim runs through `check_citations`, a malformed answer is refused (never guessed), and a stage marked `write` is
refused on a tainted context before any model call (the taint ceiling).
"""
from __future__ import annotations
import json, time
from dataclasses import dataclass, field
from guard import SYSTEM_PROMPT_RULES, Context, check_citations, confidence


class EngineError(Exception):
    pass


@dataclass(frozen=True)
class Stage:
    name: str                 # e.g. first-read
    schema: str               # the JSON shape the prompt asks for, as prose the model can follow
    instructions: str         # what to do at this stage
    proposes_action: bool = False   # refused on a tainted context

    @property
    def ref(self) -> str:
        return f"{self.name}@1"

    def system_prompt(self, role: str) -> str:
        return f"You are {role}. {SYSTEM_PROMPT_RULES}\nStage {self.name}: {self.instructions} Return {self.schema}."


STAGES = {
    "first-read": Stage("first-read", '{"summary", "hypothesis", "claims":[{"text","citations":[id]}]}', "summarise what changed and what is failing and name the leading hypothesis."),
    "ask": Stage("ask", '{"answer", "claims":[{"text","citations":[id]}]}', "answer the question in <question> using only the sources."),
    "propose": Stage("propose", '{"kind", "args", "expected_effect", "risk", "undo", "verification", "claims":[{"text","citations":[id]}]}',
                     "propose at most one action the sources support, or kind \"none\". The proposal is advisory; a person confirms it.", proposes_action=True),
}


def _attr(v) -> str:
    return str(v).replace("\\", " ").replace('"', "'").replace("\n", " ")


def _user_text(ctx: Context, payload: dict) -> str:
    parts = [ctx.fenced()]
    for k, v in (payload or {}).items():
        parts.append(f"<{k}>\n{_attr(v) if not isinstance(v, str) else v}\n</{k}>")
    return "\n".join(parts)


class RulesEngine:
    """Deterministic answers from the context: no network, used by tests, demonstrations and degraded mode."""
    name = "rules@1"

    def answer(self, stage: str, ctx: Context, payload: dict | None = None) -> dict:
        st = STAGES[stage]
        if st.proposes_action and ctx.tainted:
            return {"kind": "none", "claims": [], "confidence": 0.0, "refused": "tainted context: a proposal is refused (taint ceiling)", "model_ctx": {"engine": self.name}}
        good = [s for s in ctx.sources if not s.suspicious]
        if stage == "ask":
            q = (payload or {}).get("question", "").lower()
            hits = [s for s in good if any(w in s.text.lower() for w in q.split()[:6])]
            claims = check_citations([{"text": s.safe_text[:160], "citations": [s.id]} for s in hits[:3]], ctx)
            return {"answer": ("From the context: " + " ".join(c["text"] for c in claims)) if claims else "No source in the context answers that.", "claims": claims, "confidence": confidence(claims, ctx), "model_ctx": {"engine": self.name}}
        if stage == "propose":
            deploys = [s for s in good if s.kind == "deploy" and ("recent" in s.text or "minutes" in s.text)]
            if deploys:
                claims = check_citations([{"text": f"Roll back {deploys[0].ref}", "citations": [deploys[0].id]}], ctx)
                return {"kind": "rollback", "args": {"run_id": deploys[0].ref}, "expected_effect": "Errors return to baseline.", "risk": "Features in the run become unavailable.", "undo": f"Re-run {deploys[0].ref}.", "verification": "the error-rate read", "claims": claims, "confidence": confidence(claims, ctx), "model_ctx": {"engine": self.name}}
            return {"kind": "none", "claims": [], "confidence": 0.0, "refused": "no action is supported by the context", "model_ctx": {"engine": self.name}}
        claims = check_citations([{"text": f"{s.kind} {s.ref}: {s.safe_text[:100]}", "citations": [s.id]} for s in good[:5]], ctx)
        recent = [s for s in good if s.kind == "deploy" and ("recent" in s.text or "minutes" in s.text)]
        hyp = f"The deployment {recent[0].ref} is the most likely cause." if recent else "No change correlates with the trigger; inconclusive."
        return {"summary": " ".join(c["text"] for c in claims)[:300], "hypothesis": hyp, "claims": claims, "confidence": confidence(claims, ctx), "model_ctx": {"engine": self.name}}


class ModelEngine:
    """A model behind `complete(system, user) -> text` (or `-> (text, usage_dict)`), with the guard applied on both sides."""
    name = "model@1"

    def __init__(self, complete, role: str = "an assistant that reads evidence and cites it", stages: dict | None = None):
        self.complete, self.role, self.stages = complete, role, dict(stages or STAGES)

    def answer(self, stage: str, ctx: Context, payload: dict | None = None) -> dict:
        st = self.stages[stage]
        if st.proposes_action and ctx.tainted:
            return {"kind": "none", "claims": [], "confidence": 0.0, "refused": "tainted context: a proposal is refused (taint ceiling)", "model_ctx": {"engine": self.name}}
        t0 = time.time()
        out = self.complete(st.system_prompt(self.role), _user_text(ctx, payload or {}))
        text, usage = (out if isinstance(out, tuple) else (out, {}))
        try:
            o = json.loads(text)
        except (ValueError, TypeError):
            raise EngineError("the model returned a malformed answer; refused")
        if not isinstance(o, dict):
            raise EngineError("the model returned a malformed answer; refused")
        claims = check_citations(o.get("claims", []), ctx)
        o["claims"], o["confidence"] = claims, confidence(claims, ctx)
        if st.proposes_action and o.get("kind") not in ("rollback", "flag", "scale", "restart", "none"):
            o.update({"kind": "none", "refused": "the model proposed nothing supported"})
        o["model_ctx"] = {"engine": self.name, "stage": st.ref, "duration_ms": int((time.time() - t0) * 1000), **usage}
        return o
