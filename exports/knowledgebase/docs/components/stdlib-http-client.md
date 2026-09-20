---
title: "Stdlib http client"
owner: ai-platform-engineering
status: active
reviewed: '2026-09-19'
tags: [agents, observability]
audience: [engineer]
---
# stdlib-http-client

> A component of the collection: `components/python/stdlib-http-client/` in the repository (category tool, python, status ready). Copy it from there; this page is its README, published by the shelf tool. It is an interim implementation of the platform design specification §5.3, §4.11 (PLT-HDL-1, PLT-HDL-2, PLT-CTR-1); the replacement test is under Known limits. Version 1.0.0; sign-off: owner pending; AI security pending; walkthrough `WALKTHROUGH.md`; live example `example.py`.


One HTTP client for every upstream, on `urllib` only: timeouts, bounded retries with exponential backoff on 429 and
5xx, a response-size ceiling, error messages that never carry the query string (tokens travel there), and a
`RecordingTransport` that replays canned responses so client code is tested without a network.

## Five-minute start

```python
from httpclient import Http, RecordingTransport
t = RecordingTransport({("GET", "https://api.example/incidents"): (200, {"incidents": []})})
http = Http(t, timeout=10, retries=3, sleep=lambda s: None)
print(http.json("GET", "https://api.example/incidents?limit=5", {"Authorization": "Token x"}))
print(t.calls[0]["headers"]["Authorization"])        # "[secret]": the recording never keeps a credential
```

Production: `Http()` with the default `UrllibTransport`.

```
python3 -m unittest discover -s tests -t . -v
```

## What is inside

| File | What it is |
| --- | --- |
| `httpclient.py` | `Http.request/json/form`, `HttpError(status, url, body)`, `UrllibTransport`, `RecordingTransport` |
| `tests/test_httpclient.py` | Retry then succeed, redaction, non-retryable errors, bounded backoff, form posts |

## How to reuse it

Copy `httpclient.py`. Every client in your service takes an `Http` in its constructor and nothing else touches the
network. In tests, hand the same client a `RecordingTransport` keyed by `(METHOD, url_prefix)`; a route may be a tuple
or a callable `(method, url, body) -> (status, payload)`.

## Rules it enforces

Retries only on 429, 500, 502, 503, 504 and only up to `retries`; a body above 4 MB is a 413; the URL in an error is
stripped of its query; recorded headers named `authorization`, `api-key` or `x-api-key` are replaced.

## Where it came from

Meg (`meg/responder/httpclient.py`, snapshot 2026-09-19), used by every live connector there.

## Known limits

Synchronous. No connection pooling (urllib opens a connection per request); fine for a service making tens of calls
per turn, not for a high-throughput proxy.

**Replacement test** (the platform specification's §14.3 rule for an interim): The generated clients from the contract registry replace the hand-written ones behind the same handler protocol; the recording transport becomes the registry's recorded contracts.
