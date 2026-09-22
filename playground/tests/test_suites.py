import os
import unittest

from tests.helpers import EXAMPLES, C, target
from aiplayground import suites as S
from aiplayground import targets as T
from aiplayground.targets import Reply


class Loading(unittest.TestCase):
    def test_examples_load(self):
        for f in ("runbook-suite.json", "tools-suite.json"):
            self.assertTrue(S.load(os.path.join(EXAMPLES, f))["cases"])

    def test_problems_are_named(self):
        bad = [
            ({"cases": []}, "name"),
            ({"name": "s", "cases": []}, "non-empty"),
            ({"name": "s", "cases": [{"prompt": "x", "expect": {"contains": ["a"]}}]}, "id"),
            ({"name": "s", "cases": [{"id": "a", "expect": {"contains": ["a"]}}]}, "either"),
            ({"name": "s", "cases": [{"id": "a", "prompt": "x", "tool": "t", "expect": {"contains": ["a"]}}]}, "either"),
            ({"name": "s", "cases": [{"id": "a", "prompt": "x"}]}, "at least one"),
            ({"name": "s", "cases": [{"id": "a", "prompt": "x", "expect": {"containz": ["a"]}}]}, "unknown expectation"),
            ({"name": "s", "cases": [{"id": "a", "prompt": "x", "expect": {"regex": "("}}]}, "regular expression"),
            ({"name": "s", "cases": [{"id": "a", "prompt": "x", "expect": {"json": True}}, {"id": "a", "prompt": "y", "expect": {"json": True}}]}, "twice"),
            ({"name": "s", "cases": [{"id": "a", "prompt": "x", "expect": {"json": True}, "pass_rate": 2}]}, "pass_rate"),
            ({"name": "s", "cases": [{"id": "a", "prompt": "x", "expect": {"json": True}, "severity": "urgent"}]}, "severity"),
        ]
        for raw, words in bad:
            with self.assertRaisesRegex(S.SuiteError, words):
                S.load(raw)


class Expectations(unittest.TestCase):
    def test_each_check(self):
        r = Reply(text='{"a": 1} Page the on-call [doc: x]', citations=["x"], latency_ms=50, tool_calls=[{"name": "lookup", "arguments": {}}])
        self.assertEqual(S.check({"contains": ["page"], "cites": True, "calls_tool": "look.*", "max_latency_ms": 100}, r), [])
        misses = S.check({"contains": ["absent"], "not_contains": ["page"], "regex": "^zzz", "calls_no_tool": True, "max_latency_ms": 10, "json": True, "cites": False}, r)
        self.assertEqual(len(misses), 7, misses)
        self.assertEqual(S.check({"refuses": True}, Reply(text="I can't help with that.")), [])
        self.assertEqual(S.check({"refuses": True}, Reply(error="HTTP 422", status=422)), [])
        self.assertEqual(S.check({"error": True}, Reply(error="JSON-RPC -32602")), [])
        self.assertEqual(S.check({"error": True}, Reply(text="fine")), ["expected an error, got an answer"])
        self.assertIn("failed", S.check({"contains": ["x"]}, Reply(error="HTTP 500", status=500))[0])

    def test_repeat_and_pass_rate(self):
        class Flaky(T.Adapter):
            n = 0

            def ask(self, prompt, **k):
                Flaky.n += 1
                return Reply(text="yes" if Flaky.n % 3 else "no", latency_ms=5)
        t = target(kind="demo", demo="safe")
        case = {"id": "c", "prompt": "q", "expect": {"contains": ["yes"]}, "repeat": 3, "pass_rate": 0.66}
        r = S.run_case(case, Flaky(t), "s")
        self.assertEqual((r.status, r.metrics["passed"]), ("pass", 2))
        r = S.run_case({**case, "pass_rate": 1.0}, Flaky(t), "s")
        self.assertEqual(r.status, "fail")
        self.assertIn("needs 100%", r.summary)

    def test_all_attempts_erroring_is_an_error(self):
        class Down(T.Adapter):
            def ask(self, *a, **k):
                return Reply(error="unreachable: ConnectionRefusedError")
        r = S.run_case({"id": "c", "prompt": "q", "expect": {"contains": ["x"]}}, Down(target(kind="demo", demo="safe")), "s")
        self.assertEqual(r.status, "error")

    def test_cases_skip_on_the_wrong_kind_of_target(self):
        chat = T.open_target(target(kind="demo", demo="safe"))
        r = S.run_case({"id": "c", "tool": "x", "expect": {"error": True}}, chat, "s")
        self.assertEqual(r.status, "skipped")

    def test_the_example_suite_passes_on_the_sample_component(self):
        t = C.load(os.path.join(EXAMPLES, "python-function.json"))
        a = T.open_target(t)
        for r in S.run_suite(S.load(os.path.join(EXAMPLES, "runbook-suite.json")), a):
            self.assertEqual(r.status, "pass", f"{r.id}: {r.summary}")


if __name__ == "__main__":
    unittest.main()
