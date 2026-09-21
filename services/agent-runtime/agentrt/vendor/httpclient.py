"""One HTTP client for every upstream (urllib only): timeouts, bounded retries with backoff on 429 and 5xx,
a response-size ceiling, and errors that never carry a credential.

`Http.request` returns (status, headers, body-bytes); `json()` parses. The `Transport` protocol lets tests
substitute a recording transport; `RecordingTransport` replays canned responses by (method, url-prefix).
"""
from __future__ import annotations
import json, time, urllib.error, urllib.parse, urllib.request
from dataclasses import dataclass, field

MAX_BODY = 4 * 1024 * 1024
RETRY_STATUS = (429, 500, 502, 503, 504)
RETRY_METHODS = ("GET", "HEAD", "OPTIONS", "PUT", "DELETE")  # a POST that timed out after it took effect would run twice


class HttpError(Exception):
    def __init__(self, status: int, url: str, body: str = ""):
        super().__init__(f"HTTP {status} from {_safe_url(url)}")
        self.status, self.url, self.body = status, _safe_url(url), body[:500]


def _safe_url(url: str) -> str:
    """The URL without its query string (tokens sometimes travel there) for error messages and logs."""
    p = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, "", ""))


class UrllibTransport:
    def send(self, method: str, url: str, headers: dict, body: bytes | None, timeout: float):
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read(MAX_BODY + 1)
                if len(data) > MAX_BODY:
                    raise HttpError(413, url, "response above the size ceiling")
                return r.status, dict(r.headers), data
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read(MAX_BODY)


@dataclass
class RecordingTransport:
    """Canned responses for tests and the recorded-contract drift check: routes[(METHOD, url_prefix)] = (status, body)."""
    routes: dict = field(default_factory=dict)
    calls: list = field(default_factory=list)

    def send(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": {k: ("[secret]" if k.lower() in ("authorization", "api-key", "x-api-key") else v) for k, v in headers.items()}, "body": body})
        for (m, prefix), resp in self.routes.items():
            if m == method and url.startswith(prefix):
                status, payload = resp(method, url, body) if callable(resp) else resp
                return status, {"Content-Type": "application/json"}, (json.dumps(payload).encode() if not isinstance(payload, bytes) else payload)
        return 404, {}, b'{"error":"no canned route"}'


class Http:
    def __init__(self, transport=None, timeout: float = 15.0, retries: int = 3, backoff_s: float = 0.5, sleep=time.sleep, user_agent: str = "app/1.0", retry_methods: tuple = RETRY_METHODS):
        self.t, self.timeout, self.retries, self.backoff_s, self.sleep, self.ua = transport or UrllibTransport(), timeout, retries, backoff_s, sleep, user_agent
        self.retry_methods = tuple(m.upper() for m in retry_methods)

    def request(self, method: str, url: str, headers: dict | None = None, body: bytes | None = None, expect=(200, 201, 202, 204)):
        h = {"User-Agent": self.ua, "Accept": "application/json", **(headers or {})}
        last = None
        for attempt in range(self.retries + 1):
            status, rh, data = self.t.send(method, url, h, body, self.timeout)
            if status in expect:
                return status, rh, data
            last = HttpError(status, url, data.decode("utf-8", "replace") if data else "")
            if status not in RETRY_STATUS or attempt == self.retries or method.upper() not in self.retry_methods:
                raise last
            self.sleep(self.backoff_s * (2 ** attempt))
        raise last  # pragma: no cover

    def json(self, method: str, url: str, headers: dict | None = None, payload=None, expect=(200, 201, 202, 204)):
        body = None
        h = dict(headers or {})
        if payload is not None:
            body = json.dumps(payload).encode(); h["Content-Type"] = "application/json"
        status, rh, data = self.request(method, url, h, body, expect)
        if not data:
            return {}
        try:
            return json.loads(data)
        except ValueError:
            raise HttpError(status, url, "non-JSON body")

    def form(self, url: str, fields: dict, headers: dict | None = None):
        body = urllib.parse.urlencode(fields).encode()
        h = {"Content-Type": "application/x-www-form-urlencoded", **(headers or {})}
        _, _, data = self.request("POST", url, h, body)
        return json.loads(data)
