# ids-only-logging

A JSON logger that lets only identifiers through. A string that is not id-shaped (free text, a token with a space,
an address) is withheld whole, never a prefix; lists and dicts are truncated. By construction, no ticket body, question, answer or upstream log
line ever reaches a log line; the chained record is the record, the logs carry ids.

## Five-minute start

```python
import logs
logs.setup("INFO")                                   # JSON lines on stdout; pass a stream for tests
logs.log("turn.done", incident="inc_1", session="ses_9", stop="turn.complete", text="a 4,000-character answer ...")
# {"event": "turn.done", "incident": "inc_1", "session": "ses_9", "stop": "turn.complete", "text": "[withheld]", "ts": ...}
```

```
python3 -m unittest discover -s tests -t . -v
```

## What is inside

| File | What it is |
| --- | --- |
| `logs.py` | `setup(level, stream, name)`, `log(event, level, **ids)`, `redact(value)` |
| `tests/test_logs.py` | Secrets, emails and long text never appear; short ids do; levels filter |

## How to reuse it

Copy `logs.py`, call `setup` once at start, and use `log` everywhere else. Keep the rule in your test suite: seed a
distinctive text into the system under test and assert it is absent from the captured log stream (Meg's
`test_no_incident_text_in_logs`).

## Rules it enforces

A string passes only when it is id-shaped: letters, digits and `._:/@-`, at most 64 characters (`ses_1`, `agent:x`,
`v1.2`); everything else, an address included, becomes `[withheld]` with no prefix of the text. Keys go through the
same rule; lists and dicts are capped at 20 entries; nested values are redacted recursively.

## Where it came from

Meg (`meg/responder/logs.py`, snapshot 2026-09-19), unchanged apart from the logger name being a parameter.

## Known limits

The masks are patterns, not a classifier. Values you know are text should not be passed at all; pass their ids.

**Replacement test** (the platform specification's §14.3 rule for an interim): The same seeded-text test passes against the platform's telemetry sink; log lines carry ids only there too.
