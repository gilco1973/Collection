"""Operations plumbing shared by the routes: request ids, a per-principal rate limit, readiness.

A request id comes in on `X-Request-Id` (the hub sends one on every call) or is minted here; it is echoed on the
response, so the support line a person sees matches a log line an operator can find. Log lines carry it through a
thread-local, never anything about the person. The rate limit is a token bucket per principal id: the bank's
gateway limits by network, this limits by person, so one runaway client cannot exhaust the process for everyone.
"""
from __future__ import annotations
import logging, re, threading, time, uuid

_local = threading.local()
_SAFE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def request_id(header_value: str | None) -> str:
    """The caller's id when it is a plain token of at most 64 characters, else a fresh one."""
    v = (header_value or "").strip()
    rid = v if _SAFE.match(v) else uuid.uuid4().hex[:16]
    _local.rid = rid
    return rid


def current_request_id() -> str:
    return getattr(_local, "rid", "-")


class RequestIdFilter(logging.Filter):
    """Adds `rid` to every record so the format can print it; `-` outside a request."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.rid = current_request_id()
        return True


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s rid=%(rid)s %(message)s"


def install_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=LOG_FORMAT)
    f = RequestIdFilter()
    for h in logging.getLogger().handlers:
        h.addFilter(f)


class RateLimiter:
    """A token bucket per key: `per_minute` tokens, refilled continuously; 0 disables. Returns seconds to wait, 0 when allowed."""

    def __init__(self, per_minute: int, burst: int | None = None, now=time.time):
        self.rate = per_minute / 60.0
        self.capacity = float(burst if burst is not None else max(1, per_minute))
        self.now = now
        self._b: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, cost: float = 1.0) -> float:
        if self.rate <= 0:
            return 0.0
        with self._lock:
            t = self.now()
            tokens, at = self._b.get(key, (self.capacity, t))
            tokens = min(self.capacity, tokens + (t - at) * self.rate)
            if tokens >= cost:
                self._b[key] = (tokens - cost, t)
                return 0.0
            self._b[key] = (tokens, t)
            if len(self._b) > 10_000:  # forget idle keys rather than grow without bound
                cutoff = t - 120
                self._b = {k: v for k, v in self._b.items() if v[1] >= cutoff}
            return max(1.0, (cost - tokens) / self.rate)


def readiness(checks: dict) -> tuple[bool, dict]:
    """Runs each named check; a check returns nothing when fine and raises or returns a string when not."""
    out, ok = {}, True
    for name, fn in checks.items():
        try:
            r = fn()
            if r:
                out[name] = str(r); ok = False
            else:
                out[name] = "ok"
        except Exception as e:  # the check names the class, never the message: messages can carry values
            out[name] = type(e).__name__; ok = False
    return ok, out
