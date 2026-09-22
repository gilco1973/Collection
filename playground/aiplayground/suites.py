"""Suites: the tester's own cases, in a JSON file next to the solution.

A case asks one question (or calls one tool) and states what a good answer looks like. The probes test what every
solution must hold; a suite tests what this solution is for: that the runbook question gets the runbook answer,
that the tool returns the ticket. `repeat` asks the same case several times and `pass_rate` says how many of those
must pass, since a model does not answer the same way twice.

    {
      "name": "late-file-runbook",
      "cases": [
        {"id": "late-file", "prompt": "What do we do when the ACH file is late?", "context": "...",
         "expect": {"contains": ["page"], "cites": true, "max_latency_ms": 8000}, "repeat": 3, "pass_rate": 0.66},
        {"id": "lookup", "tool": "lookup_ticket", "arguments": {"ticket_id": "INC-1042"}, "expect": {"contains": ["open"]}}
      ]
    }
"""
from __future__ import annotations

import json
import re

from .probes import Attempt, Result, refused

EXPECT_KEYS = {"contains", "contains_any", "not_contains", "regex", "not_regex", "cites", "refuses", "calls_tool", "calls_no_tool",
               "max_latency_ms", "json", "error"}
SEVERITIES = ("critical", "high", "medium", "low", "info")
LIST_KEYS = ("contains", "contains_any", "not_contains")
REGEX_KEYS = ("regex", "not_regex", "calls_tool")
BOOL_KEYS = ("cites", "refuses", "calls_no_tool", "json", "error")
NOT_A_REFUSAL = (401, 404, 407, 408, 429)   # unauthorised, not found, proxy, timeout, rate limited: the service did not decide
SOURCE_MARK = re.compile(r"\[(?:doc|source|src|ref)\s*:|§", re.I)   # a citation, not the word "source"


class SuiteError(ValueError):
    pass


def load(source) -> dict:
    if isinstance(source, dict):
        raw = source
    else:
        try:
            with open(source, encoding="utf-8") as f:
                raw = json.load(f)
        except OSError as e:
            raise SuiteError(f"cannot read the suite: {e.strerror}: {source}") from None
        except json.JSONDecodeError as e:
            raise SuiteError(f"the suite is not JSON: line {e.lineno}: {e.msg}") from None
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not raw["name"]:
        raise SuiteError("a suite is an object with a `name` and `cases`")
    cases = raw.get("cases")
    if not isinstance(cases, list) or not cases:
        raise SuiteError(f"{raw['name']}: `cases` is a non-empty list")
    seen = set()
    for i, c in enumerate(cases):
        where = f"{raw['name']} case {i + 1}"
        if not isinstance(c, dict) or not isinstance(c.get("id"), str) or not c["id"]:
            raise SuiteError(f"{where}: every case has an `id`")
        if c["id"] in seen:
            raise SuiteError(f"{where}: the id {c['id']} is used twice")
        seen.add(c["id"])
        if ("prompt" in c) == ("tool" in c):
            raise SuiteError(f"{where} ({c['id']}): a case has either `prompt` or `tool`")
        expect = c.get("expect", {})
        if not isinstance(expect, dict) or not expect:
            raise SuiteError(f"{where} ({c['id']}): `expect` names at least one check")
        unknown = set(expect) - EXPECT_KEYS
        if unknown:
            raise SuiteError(f"{where} ({c['id']}): unknown expectation(s): {', '.join(sorted(unknown))}")
        _check_types(f"{where} ({c['id']})", c, expect)
    return raw


def _check_types(where: str, c: dict, expect: dict) -> None:
    """Every value the right type, so a typo in a suite is named at load instead of crashing (or passing) a run."""
    def bad(msg):
        raise SuiteError(f"{where}: {msg}")
    for k in ("prompt", "tool", "system", "context", "title", "recommendation"):
        if k in c and not isinstance(c[k], str):
            bad(f"`{k}` is a string")
    if "tool" in c and not c["tool"]:
        bad("`tool` names a tool")
    if "arguments" in c and not isinstance(c["arguments"], dict):
        bad("`arguments` is an object")
    for k in LIST_KEYS:
        if k in expect:
            v = expect[k]
            if not isinstance(v, list) or not all(isinstance(x, str) and x for x in v):
                bad(f"`{k}` is a list of non-empty strings, e.g. [\"page\"]")
            if k == "contains_any" and not v:
                bad("`contains_any` names at least one string")
    for k in REGEX_KEYS:
        if k in expect:
            if not isinstance(expect[k], str) or not expect[k]:
                bad(f"`{k}` is a regular expression, as a string")
            try:
                re.compile(expect[k])
            except re.error as e:
                bad(f"`{k}` is not a regular expression: {e}")
    for k in BOOL_KEYS:
        if k in expect and not isinstance(expect[k], bool):
            bad(f"`{k}` is true or false")
    if "max_latency_ms" in expect:
        v = expect["max_latency_ms"]
        if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
            bad("`max_latency_ms` is a positive whole number of milliseconds")
    if c.get("severity", "medium") not in SEVERITIES:
        bad(f"`severity` is one of {', '.join(SEVERITIES)}")
    repeat = c.get("repeat", 1)
    if isinstance(repeat, bool) or not isinstance(repeat, int) or not 1 <= repeat <= 20:
        bad("`repeat` is between 1 and 20")
    rate = c.get("pass_rate", 1.0)
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not 0 < rate <= 1:
        bad("`pass_rate` is above 0 and at most 1")


def service_refused(reply) -> bool:
    """The service turned the request away itself: a 4xx that is a decision, not a missing route, a missing
    credential, a timeout or a rate limit. A 5xx, a timeout or an unreachable service is never a refusal."""
    status = reply.status if isinstance(reply.status, int) and not isinstance(reply.status, bool) else None
    return reply.error is not None and status is not None and 400 <= status < 500 and status not in NOT_A_REFUSAL


def check(expect: dict, reply) -> list:
    """The expectations this reply misses, each as a sentence."""
    text = reply.text or ""
    low = text.lower()
    missed = []
    if expect.get("error") is True:
        if not reply.error:
            missed.append("expected an error, got an answer")
        return missed
    if reply.error and not (expect.get("refuses") is True and service_refused(reply)):
        # `error: false` says the same thing out loud: an errored reply meets no other expectation
        return [f"the solution failed: {reply.error}" + (" (expected no error)" if expect.get("error") is False else "")]
    for s in expect.get("contains", []):
        if s.lower() not in low:
            missed.append(f"does not contain {s!r}")
    if expect.get("contains_any") and not any(s.lower() in low for s in expect["contains_any"]):
        missed.append(f"contains none of {expect['contains_any']!r}")
    for s in expect.get("not_contains", []):
        if s.lower() in low:
            missed.append(f"contains {s!r}")
    if expect.get("regex") and not re.search(expect["regex"], text, re.I | re.S):
        missed.append(f"does not match /{expect['regex']}/")
    if expect.get("not_regex") and re.search(expect["not_regex"], text, re.I | re.S):
        missed.append(f"matches /{expect['not_regex']}/")
    if "cites" in expect:
        has = bool(reply.citations) or bool(SOURCE_MARK.search(text))
        if has != bool(expect["cites"]):
            missed.append("names no source" if expect["cites"] else "names a source it should not")
    if "refuses" in expect:
        did = service_refused(reply) or (reply.error is None and refused(reply))
        if did != bool(expect["refuses"]):
            missed.append("did not refuse" if expect["refuses"] else "refused")
    if expect.get("calls_tool"):
        names = [str(c.get("name", "")) for c in reply.tool_calls]
        if not any(re.fullmatch(expect["calls_tool"], n) for n in names):
            missed.append(f"did not call a tool matching {expect['calls_tool']!r} (called: {', '.join(names) or 'none'})")
    if expect.get("calls_no_tool") and reply.tool_calls:
        missed.append(f"called {', '.join(str(c.get('name', '')) for c in reply.tool_calls)}")
    if expect.get("max_latency_ms") and reply.latency_ms > int(expect["max_latency_ms"]):
        missed.append(f"took {reply.latency_ms} ms, over {expect['max_latency_ms']} ms")
    if expect.get("json"):
        try:
            json.loads(text)
        except ValueError:
            missed.append("is not JSON")
    return missed


def run_case(case: dict, adapter, suite_name: str) -> Result:
    n = int(case.get("repeat", 1))
    need = float(case.get("pass_rate", 1.0))
    attempts, failures = [], []
    for _ in range(n):
        if "tool" in case:
            reply = adapter.call_tool(case["tool"], case.get("arguments", {})) if adapter.tool_server else None
            if reply is None:
                return Result(f"{suite_name}/{case['id']}", case.get("title", case["id"]), "EVAL", case.get("severity", "medium"), "skipped",
                              "a tool case needs a tool server target", suite=suite_name)
            a = Attempt(f"tools/call {case['tool']} {json.dumps(case.get('arguments', {}))[:300]}", reply)
        else:
            if not adapter.chat:
                return Result(f"{suite_name}/{case['id']}", case.get("title", case["id"]), "EVAL", case.get("severity", "medium"), "skipped",
                              "a question case needs a target that answers questions", suite=suite_name)
            reply = adapter.ask(case["prompt"], system=case.get("system", ""), context=case.get("context", ""))
            a = Attempt(case["prompt"], reply, case.get("system", ""), case.get("context", ""))
        attempts.append(a)
        failures.append(check(case["expect"], reply))
    passed = sum(1 for f in failures if not f)
    rate = passed / n
    expect = case["expect"]
    errors = sum(1 for a in attempts if a.reply.error and expect.get("error") is not True and not (expect.get("refuses") is True and service_refused(a.reply)))
    metrics = {"attempts": n, "passed": passed, "pass_rate": round(rate, 2), "required": need,
               "p50_ms": sorted(a.reply.latency_ms for a in attempts)[n // 2]}
    title = case.get("title", case["id"])
    rid = f"{suite_name}/{case['id']}"
    if errors == n:
        return Result(rid, title, "EVAL", case.get("severity", "medium"), "error", f"every attempt failed: {attempts[0].reply.error}",
                      attempts[:3], case.get("recommendation", ""), suite_name, metrics)
    if rate + 1e-9 >= need:
        return Result(rid, title, "EVAL", case.get("severity", "medium"), "pass", f"{passed} of {n} attempts met every expectation",
                      attempts[:1], case.get("recommendation", ""), suite_name, metrics)
    first = next(f for f in failures if f)
    shown = [a for a, f in zip(attempts, failures) if f][:3]
    return Result(rid, title, "EVAL", case.get("severity", "medium"), "fail",
                  f"{passed} of {n} attempts passed (needs {int(need * 100)}%): " + "; ".join(first), shown, case.get("recommendation", ""), suite_name, metrics)


def run_case_safely(case: dict, adapter, suite_name: str) -> Result:
    """run_case, but a case that breaks (an odd reply, a value the loader let through) is an `error` result for that
    case, never the end of the run."""
    try:
        return run_case(case, adapter, suite_name)
    except Exception as e:   # noqa: BLE001 - the report says what broke
        cid = case.get("id", "?") if isinstance(case, dict) else "?"
        title = case.get("title", cid) if isinstance(case, dict) else cid
        severity = case.get("severity", "medium") if isinstance(case, dict) and case.get("severity") in SEVERITIES else "medium"
        return Result(f"{suite_name}/{cid}", str(title), "EVAL", severity, "error", f"the case itself failed: {type(e).__name__}: {e}"[:300], suite=suite_name)


def run_suite(suite: dict, adapter) -> list:
    return [run_case_safely(c, adapter, suite["name"]) for c in suite["cases"]]
