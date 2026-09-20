"""Model gateway: the one door to a model.

One adapter over the model provider (Bedrock Converse, the Anthropic API, an internal endpoint), an inference
profile per consumer, a model allowlist, the prompt loaded by reference with its hash, the model context
stamped on every call, token usage charged to the session's budget. `FakeModel` is a deterministic stand-in
so the whole loop runs offline; swap it for a real adapter with the same `complete` signature and nothing
above this module changes (`bedrock-converse-adapter` in this collection is one).
"""
from __future__ import annotations
import hashlib, json, time, uuid
from dataclasses import dataclass


class ModelGatewayError(Exception):
    pass


@dataclass(frozen=True)
class InferenceProfile:
    consumer: str
    model_id: str
    region: str
    max_output_tokens: int = 2000


@dataclass
class ModelContext:
    model_id: str
    prompt_ref: str
    prompt_hash: str
    profile: str
    region: str
    gateway_call_id: str
    input_tokens: int
    output_tokens: int
    duration_ms: int

    def to_json(self) -> dict:
        return self.__dict__.copy()


class PromptRegistryV0:
    """Prompts as versioned text loaded by reference ("plan_ticket@1"); the hash travels with every call."""

    def __init__(self, prompts: dict[str, str]):
        self._p = dict(prompts)

    def load(self, ref: str) -> tuple[str, str]:
        if ref not in self._p:
            raise ModelGatewayError(f"unknown prompt reference {ref}")
        text = self._p[ref]
        return text, "sha256:" + hashlib.sha256(text.encode()).hexdigest()


class FakeModel:
    """Deterministic stand-in for a model. `responses` maps a substring of the system prompt to the JSON the
    fake returns (a dict, or a callable taking the user text); anything unmatched echoes a short summary.
    It never invents an action and never reads a source marked suspicious="true"."""

    def __init__(self, responses: dict | None = None):
        self.responses = dict(responses or {})
        self.calls: list[dict] = []

    def complete(self, model_id: str, system: str, user: str, max_tokens: int) -> tuple[str, int, int]:
        self.calls.append({"model_id": model_id, "system": system, "user": user, "max_tokens": max_tokens})
        text = None
        for key, resp in self.responses.items():
            if key in system:
                text = json.dumps(resp(user) if callable(resp) else resp); break
        if text is None:
            text = "OK: " + user[:80]
        return text, len(system) // 4 + len(user) // 4, len(text) // 4


class ModelGateway:
    def __init__(self, adapter, profiles: dict[str, InferenceProfile], allowlist: set[str], prompts: PromptRegistryV0, telemetry=None):
        self.adapter, self.profiles, self.allowlist, self.prompts, self.telemetry = adapter, profiles, set(allowlist), prompts, telemetry

    def complete(self, consumer: str, prompt_ref: str, user_text: str, session, phase: str) -> tuple[str, ModelContext]:
        """`session` needs `.budget` (a harness Budget), `.consumer`, `.board`, `.ticket_key`."""
        if consumer not in self.profiles:
            raise ModelGatewayError(f"no inference profile for {consumer}")
        prof = self.profiles[consumer]
        if prof.model_id not in self.allowlist:
            raise ModelGatewayError(f"model {prof.model_id} is not on the allowlist")
        system, phash = self.prompts.load(prompt_ref)
        session.budget.check_tokens_available()
        t0 = time.time()
        text, tin, tout = self.adapter.complete(prof.model_id, system, user_text, prof.max_output_tokens)
        ctx = ModelContext(prof.model_id, prompt_ref, phash, f"profile/{consumer}", prof.region, "gwc_" + uuid.uuid4().hex[:12], tin, tout, int((time.time() - t0) * 1000) + 1)
        session.budget.spend_tokens(tin + tout)
        if self.telemetry:
            self.telemetry.model_call(session.consumer, session.board, session.ticket_key, phase, tin, tout, ctx.duration_ms, prof.model_id)
        return text, ctx
