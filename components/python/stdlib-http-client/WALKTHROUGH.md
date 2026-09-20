# Walkthrough: stdlib-http-client

## 1. Run the live example

```
cd components/python/stdlib-http-client && python3 example.py
```

A flaky upstream answered on the third attempt with backoff, the recorded header shown as `[secret]`, and a 403 whose message carries no query string.

## 2. Copy and construct once

```
cp httpclient.py /path/to/your-service/
```

`http = Http(timeout=15, retries=3)` once; every client takes it in its constructor. Nothing else in the service opens a socket.

## 3. Write a client

```python
class PagerDuty:
    def __init__(self, http, secrets): self.http, self.secrets = http, secrets
    def incident(self, pd_id):
        return self.http.json("GET", f"https://api.pagerduty.com/incidents/{pd_id}", {"Authorization": "Token token=" + self.secrets.get("pagerduty/api")})
```

The secret is fetched by name at call time (`secrets-by-name`), never held on the instance.

## 4. Test without a network

`RecordingTransport({("GET", "https://api.pagerduty.com/incidents/"): (200, {...})})` and pass it as `Http(transport)`. A route can be a callable to script failures. The recording keeps every call with credentials replaced.

## 5. Prove it

```
python3 -m unittest discover -s tests -t . -v
```
