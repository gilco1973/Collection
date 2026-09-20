---
title: "Ids-only logging"
owner: ai-platform-engineering
status: active
reviewed: '2026-09-19'
tags: [observability, security]
audience: [engineer]
---
# ids-only-logging

> A component of the collection: `components/python/ids-only-logging/` in the repository (kind tool, python, status ready). Copy it from there; this page is its README, published by the catalog tool.


A JSON logger that lets only identifiers through. Long strings are withheld, anything that looks like a secret or an
email is masked, lists and dicts are truncated. By construction, no ticket body, question, answer or upstream log
line ever reaches a log line; the chained record is the record, the logs carry ids.

## Five-minute start

```python
import logs
logs.setup("INFO")                                   # JSON lines on stdout; pass a stream for tests
logs.log("turn.done", incident="inc_1", session="ses_9", stop="turn.complete", text="a 4,000-character answer ...")
# {"event": "turn.done", "incident": "inc_1", "session": "ses_9", "stop": "turn.complete", "text": "a 4,000-character an…[4000 chars withheld]", "ts": ...}
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

Strings above 96 characters are cut with a count; `bearer …`, `token=`, `key=`, `password=` and email addresses are
replaced; lists and dicts are capped at 20 entries; nested values are redacted recursively.

## Where it came from

Meg (`meg/responder/logs.py`, snapshot 2026-09-19), unchanged apart from the logger name being a parameter.

## Known limits

The masks are patterns, not a classifier. Values you know are text should not be passed at all; pass their ids.
