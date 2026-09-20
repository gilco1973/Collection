"""Logging with ids only: no free text (a ticket body, a question, an answer, a log line from upstream) ever reaches a log line.

`log(event, **ids)` writes one JSON line with the event name and the identifiers it is given. Values are
passed through `redact`, which refuses strings longer than a short id and masks anything that looks like
a secret or an email. The test suite asserts that no log line ever carries a seeded text, a secret or an email.
"""
from __future__ import annotations
import json, logging, re, sys, time

_LOG = logging.getLogger("app")
_MAX_VALUE = 96
_SECRETISH = re.compile(r"(bearer\s+\S+|token=\S+|key=\S+|password=\S+)", re.I)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def setup(level: str = "INFO", stream=None, name: str = "app") -> None:
    global _LOG
    _LOG = logging.getLogger(name)
    h = logging.StreamHandler(stream or sys.stdout)
    h.setFormatter(logging.Formatter("%(message)s"))
    _LOG.handlers[:] = [h]
    _LOG.setLevel(getattr(logging, level.upper(), logging.INFO))
    _LOG.propagate = False


def redact(v):
    if isinstance(v, str):
        v = _SECRETISH.sub("[secret]", v)
        v = _EMAIL.sub("[email]", v)
        if len(v) > _MAX_VALUE:
            return v[:24] + f"…[{len(v)} chars withheld]"
        return v
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    if isinstance(v, (list, tuple)):
        return [redact(x) for x in v][:20]
    if isinstance(v, dict):
        return {str(k): redact(x) for k, x in list(v.items())[:20]}
    return redact(str(v))


def log(event: str, level: str = "info", **ids) -> None:
    rec = {"ts": round(time.time(), 3), "event": event, **{k: redact(v) for k, v in ids.items()}}
    getattr(_LOG, level, _LOG.info)(json.dumps(rec, sort_keys=True, default=str))
