#!/usr/bin/env python3
"""Live smoke test against a running server: liveness, readiness and one real chat turn.

Standard library only, so it runs from any host with Python 3 and no project install:

    python scripts/live-smoke.py --base http://127.0.0.1:8765

Prints ``PASS name`` / ``FAIL name`` per check on stdout (diagnostics go to stderr) and exits 0
only when every check passed. The chat check spends real model budget (one capped turn); the
``live-smoke`` workflow runs it weekly and on demand when the repository holds a credential.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from urllib.request import urlopen  # a module attribute so a test can swap it for a fake

DEFAULT_BASE = "http://127.0.0.1:8765"
DEFAULT_QUESTION = "In one sentence, what is this knowledge base for?"
TIMEOUT_S = 120.0


def _json(raw: bytes) -> dict:
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _call(method: str, url: str, name: str, body: dict | None = None) -> tuple[int, dict]:
    """``(status, json body)``; status 0 when the server could not be reached at all."""
    headers = {"Accept": "application/json", "Content-Type": "application/json", "X-Request-ID": f"live-smoke-{name}"}
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(request, timeout=TIMEOUT_S) as response:
            return response.status, _json(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, _json(exc.read())
    except (urllib.error.URLError, OSError) as exc:
        print(f"{name}: {type(exc).__name__}: {getattr(exc, 'reason', exc)}", file=sys.stderr)
        return 0, {}


def check_health(base: str) -> bool:
    status, data = _call("GET", f"{base}/api/health", "health")
    return status == 200 and data.get("status") == "ok" and bool(data.get("version"))


def check_ready(base: str) -> bool:
    status, data = _call("GET", f"{base}/api/health/ready", "ready")
    checks = data.get("checks") or {}
    return status == 200 and data.get("status") == "ok" and bool(checks) and all(checks.values())


def check_chat(base: str, question: str = DEFAULT_QUESTION) -> bool:
    status, data = _call("POST", f"{base}/api/chat", "chat", {"message": question})
    answer = data.get("answer")
    return status == 200 and isinstance(answer, str) and answer.strip() != ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live smoke test against a running knowledge-base server.")
    parser.add_argument("--base", default=DEFAULT_BASE, help=f"server base URL (default {DEFAULT_BASE})")
    parser.add_argument("--question", default=DEFAULT_QUESTION, help="the question the chat check asks")
    args = parser.parse_args(argv)
    base = args.base.rstrip("/")
    results = [("health", check_health(base)), ("ready", check_ready(base)), ("chat", check_chat(base, args.question))]
    for name, passed in results:
        print(f"{'PASS' if passed else 'FAIL'} {name}")
    return 0 if all(passed for _, passed in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
