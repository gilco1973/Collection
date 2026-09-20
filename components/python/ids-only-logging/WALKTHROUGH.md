# Walkthrough: ids-only-logging

## 1. Run the live example

```
cd components/python/ids-only-logging && python3 example.py
```

One log line for a turn that carried an email, a token and incident text; the line has the ids and none of the text.

## 2. Copy and set up

```
cp logs.py /path/to/your-service/
```

Call `logs.setup("INFO")` once at start (pass a stream in tests). Log with `logs.log(event, **ids)` and pass identifiers: incident, session, turn, tool, stop reason.

## 3. Keep the rule in your tests

Seed a distinctive text into the system under test, capture the stream, assert the text is absent. The component's `tests/test_logs.py` is the pattern; copy it next to your integration tests.

## 4. Treat a leak as an incident

If incident text ever appears in a log line, that is a security incident by construction, not a bug to fix quietly. Say so in your runbook.
