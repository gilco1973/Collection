import json
import os
import sys
import unittest

from tests.helpers import EXAMPLES, C, tempdir, target, write
from aiplayground import report as Rp
from aiplayground import runner
from aiplayground.probes import Result

ADA = "Ada Placeholder <ada@example.com>"
BOB = "Bob Placeholder <bob@example.com>"


def rep_with(*results, by=ADA):
    return Rp.build(list(results), target={"name": "t"}, component=None, tester={"by": by, "role": "engineer"}, started=Rp.now(), suites=[], probes=[])


def res(i, status, severity="high"):
    return Result(i, i, "LLM01", severity, status, f"{i} {status}")


class Verdicts(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(rep_with(res("a", "pass"), res("b", "skipped"))["verdict"], "clear")
        self.assertEqual(rep_with(res("a", "fail", "critical"))["verdict"], "blocked")
        self.assertEqual(rep_with(res("a", "fail", "medium"))["verdict"], "needs-review")
        self.assertEqual(rep_with(res("a", "review", "critical"))["verdict"], "needs-review")
        self.assertEqual(rep_with(res("a", "error", "low"))["verdict"], "needs-review")
        r = Rp.build([], target={"name": "t"}, component=None, tester={}, started=Rp.now(), suites=[], probes=[], incomplete="unreachable")
        self.assertEqual(r["verdict"], "incomplete")

    def test_results_are_ordered_worst_first(self):
        r = rep_with(res("p", "pass"), res("f", "fail", "low"), res("c", "fail", "critical"), res("s", "skipped"))
        self.assertEqual([x["id"] for x in r["results"]], ["c", "f", "p", "s"])


class Triage(unittest.TestCase):
    def test_a_named_person_with_a_reason_changes_the_verdict_not_the_results(self):
        r = rep_with(res("a", "fail", "high"), res("b", "fail", "medium"))
        before = json.dumps(r["results"])
        Rp.triage(r, "a", "accepted-risk", BOB, "Only reachable from the sandbox; tracked as a known limit.")
        self.assertEqual(r["verdict"], "needs-review")
        Rp.triage(r, "b", "false-positive", ADA, "The marker was the ticket number, not the planted one.")
        self.assertEqual(r["verdict"], "clear")
        self.assertEqual(json.dumps(r["results"]), before)
        self.assertEqual(r["onboarding"]["known_limits_to_add"], ["a: Only reachable from the sandbox; tracked as a known limit."])
        Rp.triage(r, "a", "fixed-retest", ADA, "Fixed in 0.2.0; the next run will show it.")
        self.assertEqual(r["verdict"], "blocked")

    def test_what_triage_refuses(self):
        r = rep_with(res("a", "fail", "critical"), res("p", "pass"))
        for args, words in (((("a", "waived", BOB, "x" * 20)), "decision"), (("a", "accepted-risk", "bob", "x" * 20), "names a person"),
                            (("a", "accepted-risk", BOB, "short"), "reason"), (("zz", "accepted-risk", BOB, "x" * 20), "no result"),
                            (("p", "accepted-risk", BOB, "x" * 20), "only a failure"), (("a", "accepted-risk", ADA, "x" * 20), "someone other")):
            with self.assertRaisesRegex(ValueError, words):
                Rp.triage(r, *args)


class Rendering(unittest.TestCase):
    def test_secrets_are_scrubbed_and_long_text_cut(self):
        out = Rp.scrub({"a": ["token s3cr3tvalue here", "x" * 5000]}, ["s3cr3tvalue"])
        self.assertEqual(out["a"][0], "token [secret] here")
        self.assertLess(len(out["a"][1]), 2100)

    def test_html_escapes_everything_a_solution_said(self):
        from aiplayground.probes import Attempt
        from aiplayground.targets import Reply
        r = Result("x", "<b>title</b>", "LLM05", "high", "fail", "<img src=x onerror=alert(1)>", [Attempt("<script>q</script>", Reply(text="<script>alert(1)</script>"))])
        page = Rp.to_html(rep_with(r))
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertNotIn("<img src=x", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertIn("## Findings", Rp.to_markdown(rep_with(r)))

    def test_save_load_and_compare(self):
        a = rep_with(res("x", "fail"), res("y", "pass"), res("gone", "pass"))
        b = rep_with(res("x", "pass"), res("y", "fail"), res("new", "review"))
        with tempdir() as d:
            paths = Rp.save(a, d)
            self.assertTrue(all(os.path.exists(p) for p in paths.values()))
            self.assertEqual(Rp.load(paths["json"])["id"], a["id"])
            with self.assertRaisesRegex(ValueError, "not a playground report"):
                Rp.load(write(os.path.join(d, "other.json"), {"kind": "else"}))
        changes = {c["id"]: c["change"] for c in Rp.compare(a, b)}
        self.assertEqual(changes, {"x": "better", "y": "worse", "gone": "gone", "new": "new"})


class Runner(unittest.TestCase):
    def test_an_unreachable_solution_gives_an_incomplete_report(self):
        rep = runner.run(target(kind="http", preset="simple-json", url="http://127.0.0.1:9/chat", timeout_s=1))
        self.assertEqual(rep["verdict"], "incomplete")
        self.assertIn("did not answer", rep["verdict_reason"])

    def test_component_only_and_role_defaults(self):
        rep = runner.run(None, component_dir=os.path.join(EXAMPLES, "runbook-answerer"), run_component=False)
        self.assertTrue(all(r["suite"] == "contract" for r in rep["results"]))
        sec = runner.run(target(kind="demo", demo="safe"), role="ai-security")
        self.assertIn("tool-alive", sec["probes"])
        eng = runner.run(target(kind="demo", demo="safe"), probes="none")
        self.assertEqual(eng["results"], [])
        with self.assertRaisesRegex(ValueError, "role"):
            runner.run(target(kind="demo", demo="safe"), role="admin")

    def test_a_secret_the_solution_echoes_never_reaches_the_report(self):
        os.environ["PG_RUN_SECRET"] = "very-secret-value-123"
        try:
            with tempdir() as d:
                script = write(os.path.join(d, "leak.py"), "import os\nprint('the key is ' + os.environ['PG_RUN_SECRET'])\n")
                t = target(kind="command", command=[sys.executable, script], env=["PG_RUN_SECRET"])
                rep = runner.run(t, probes="pi-direct-override,leak-context-secret")
                self.assertNotIn("very-secret-value-123", json.dumps(rep))
                self.assertIn("[secret]", json.dumps(rep))
        finally:
            del os.environ["PG_RUN_SECRET"]

    def test_the_five_minute_start_is_clear(self):
        rep = runner.run(C.load(os.path.join(EXAMPLES, "python-function.json")), component_dir=os.path.join(EXAMPLES, "runbook-answerer"),
                         suites=[os.path.join(EXAMPLES, "runbook-suite.json")], by=ADA)
        self.assertEqual(rep["verdict"], "clear", rep["verdict_reason"])
        self.assertEqual(rep["onboarding"]["tests_green"], "pass")
        self.assertFalse(rep["onboarding"]["is_a_signoff"])


if __name__ == "__main__":
    unittest.main()
