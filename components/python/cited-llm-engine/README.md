# cited-llm-engine

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
