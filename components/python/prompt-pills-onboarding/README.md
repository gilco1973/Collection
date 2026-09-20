# prompt-pills-onboarding

Explain a bot inside the room it works in. A how-to card posted at the start (and on `help`) with three things to
know, clickable starter prompts grouped by category and filtered by the person's roles and the rollout increment,
who does what, and what the bot never does; a one-line hint the first time a person speaks to it; a five-step guide
page. Nobody has to remember syntax under stress.

## Five-minute start

```python
from onboarding import EXAMPLE
card = EXAMPLE.welcome_card({"service": "payments-api", "incident": "inc_42"}, "https://app.example", roles=["operator"], increment=2)
hint = EXAMPLE.first_time_hint("Dana")
html = EXAMPLE.guide_html()
```

```
python3 -m unittest discover -s tests -t . -v
```

## What is inside

| File | What it is |
| --- | --- |
| `onboarding.py` | `Pill`, `Bot` (`visible_pills`, `welcome_card` as an Adaptive Card, `first_time_hint`, `guide_html`), `EXAMPLE` |
| `tests/test_onboarding.py` | Filtering by increment and role; a valid card whose buttons carry the command and never a placeholder; the hint and the guide |

## How to reuse it

Build a `Bot` with your pills (tier `R`, `W1` or `W2`, `needs` roles), steps, roles and the "never" sentence. Post the
card with `teams-graph-connector`; handle `Action.Submit` data `{"bot": "command", "text": ...}` as if the person
typed it.

## Where it came from

Meg's in-room onboarding (`responder/onboarding.py`, snapshot 2026-09-19), with the content made a configuration.

## Known limits

**Replacement test** (the platform specification's §14.3 rule for an interim): The how-to card becomes the consumer's enablement module (PLT-ONB-12) rendered by the UI modules; the pill catalog is the same data.
