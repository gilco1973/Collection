---
title: "Cited llm engine"
owner: ai-platform-architecture
status: active
reviewed: '2026-09-19'
tags: [agents, prompting, evaluation]
audience: [engineer]
---
# cited-llm-engine

> A component of the collection: `components/python/cited-llm-engine/` in the repository (kind pattern, python, status ready). Copy it from there; this page is its README, published by the shelf tool. It is an interim implementation of the platform design specification §4.8, §4.9, §4.5 (PLT-MDL-1, PLT-PRM-1, PLT-PRM-2, PLT-PRM-3, PLT-DATA-3); the replacement test is under Known limits.


The think step behind one adapter. A model reasons over a fenced context and returns strict, cited JSON; it never
acts. `RulesEngine` answers from the context with rules (tests, demonstrations, degraded mode); `ModelEngine` wraps
any `complete(system, user) -> text` callable with the guard on both sides: fenced context in, citations checked on
the way out, a malformed answer refused, and a stage that proposes an action refused on a tainted context before any
model call.

## Five-minute start

```python
from guard import Context
from engine import RulesEngine, ModelEngine
ctx = Context(); ctx.add("alert", "PD-1", "High error rate on payments-api", "pagerduty")
ctx.add("deploy", "4822", "deploy #4822 finished 7 minutes before the trigger (recent)", "ado")
print(RulesEngine().answer("first-read", ctx)["hypothesis"])
engine = ModelEngine(lambda system, user: my_gateway(system, user))   # any model behind one function
print(engine.answer("ask", ctx, {"question": "which deploy?"})["claims"])
```

```
python3 -m unittest discover -s tests -t . -v
```

## What is inside

| File | What it is |
| --- | --- |
| `engine.py` | `Stage` (name, schema, instructions, proposes_action) and the three example stages; `RulesEngine`; `ModelEngine`; `EngineError` |
| `guard.py` | Vendored from `untrusted-input-guard` |
| `tests/test_engine.py` | Rules cite; taint refuses proposals in both engines before any call; the model sees only the fenced context; malformed answers refused; unsupported kinds become none |

## How to reuse it

Copy both files. Define your stages (schema and instructions); keep `proposes_action=True` on anything that could
become a write. Route `complete` through `governed-action-loop`'s `ModelGateway` so the allowlist, prompt hash and
budget apply. Turn a proposal into a call only through the loop's confirmation and approval path.

## Where it came from

The engine protocol of Meg's `responder/think.py` (snapshot 2026-09-19), reduced from four engines and eight incident
stages to two engines and three example stages.

## Known limits

**Replacement test** (the platform specification's §14.3 rule for an interim): Stage prompts publish to the prompt registry with an evaluation suite (PLT-PRM-2) and load by version; the same cited-JSON contract holds.
