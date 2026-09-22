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
        for k in ("regex", "not_regex"):
            if k in expect:
                try:
                    re.compile(expect[k])
                except re.error as e:
                    raise SuiteError(f"{where} ({c['id']}): `{k}` is not a regular expression: {e}") from None
        if c.get("severity", "medium") not in SEVERITIES:
            raise SuiteError(f"{where} ({c['id']}): `severity` is one of {', '.join(SEVERITIES)}")
        if not (1 <= int(c.get("repeat", 1)) <= 20):
            raise SuiteError(f"{where} ({c['id']}): `repeat` is between 1 and 20")
        if not (0 < float(c.get("pass_rate", 1.0)) <= 1):
            raise SuiteError(f"{where} ({c['id']}): `pass_rate` is above 0 and at most 1")
    return raw


def check(expect: dict, reply) -> list:
    """The expectations this reply misses, each as a sentence."""
    text = reply.text or ""
    low = text.lower()
    missed = []
    if expect.get("error") is True:
        if not reply.error:
            missed.append("expected an error, got an answer")
        return missed
    if reply.error and expect.get("error") is not False and not expect.get("refuses"):
        return [f"the solution failed: {reply.error}"]
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
        has = bool(reply.citations) or bool(re.search(r"\[doc:|\bsource\b|§", text, re.I))
        if has != bool(expect["cites"]):
            missed.append("names no source" if expect["cites"] else "names a source it should not")
    if "refuses" in expect:
        did = refused(reply) or (reply.error is not None and reply.status in (400, 403, 409, 413, 422, 451))
        if did != bool(expect["refuses"]):
            missed.append("did not refuse" if expect["refuses"] else "refused")
    if expect.get("calls_tool"):
        names = [c["name"] for c in reply.tool_calls]
        if not any(re.fullmatch(expect["calls_tool"], n) for n in names):
            missed.append(f"did not call a tool matching {expect['calls_tool']!r} (called: {', '.join(names) or 'none'})")
    if expect.get("calls_no_tool") and reply.tool_calls:
        missed.append(f"called {', '.join(c['name'] for c in reply.tool_calls)}")
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
    errors = sum(1 for a in attempts if a.reply.error and not case["expect"].get("error") and not case["expect"].get("refuses"))
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


def run_suite(suite: dict, adapter) -> list:
    return [run_case(c, adapter, suite["name"]) for c in suite["cases"]]
