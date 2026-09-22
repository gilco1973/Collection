"""Logging with ids only: no free text (a ticket body, a question, an answer, a log line from upstream) ever reaches a log line.

`log(event, **ids)` writes one JSON line with the event name and the identifiers it is given. Every string,
value or key, goes through `redact`: an id-shaped string (`ID_SHAPE`: letters, digits, `._:/@-`, at most 64
characters) passes as it is; anything else is withheld whole, never a prefix, so a sentence, a token with a
space or an `=`, or an address never reaches the line. The test suite asserts that no log line ever carries a
seeded text, a secret or an email.
"""
from __future__ import annotations
import json, logging, re, sys, time

_LOG = logging.getLogger("app")
ID_SHAPE = re.compile(r"^[A-Za-z0-9._:/@-]{1,64}$")   # what an identifier looks like: ses_1, inc-7, agent:x, a/b, v1.2
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")   # id-shaped, but a person: withheld too
WITHHELD = "[withheld]"


def setup(level: str = "INFO", stream=None, name: str = "app") -> None:
    global _LOG
    _LOG = logging.getLogger(name)
    h = logging.StreamHandler(stream or sys.stdout)
    h.setFormatter(logging.Formatter("%(message)s"))
    _LOG.handlers[:] = [h]
    _LOG.setLevel(getattr(logging, level.upper(), logging.INFO))
    _LOG.propagate = False


def redact(v):
    """An id passes; any other string is withheld entirely (no prefix: the first 24 characters of a ticket body are
    still the ticket body). Numbers, booleans and None pass; lists and dicts are walked, keys under the same rule."""
    if isinstance(v, str):
        return v if ID_SHAPE.match(v) and not _EMAIL.search(v) else WITHHELD
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    if isinstance(v, (list, tuple)):
        return [redact(x) for x in v][:20]
    if isinstance(v, dict):
        return {redact(str(k)): redact(x) for k, x in list(v.items())[:20]}
    return redact(str(v))


def log(event: str, level: str = "info", **ids) -> None:
    rec = {"ts": round(time.time(), 3), "event": redact(event), **{redact(k): redact(v) for k, v in ids.items()}}
    getattr(_LOG, level, _LOG.info)(json.dumps(rec, sort_keys=True, default=str))
