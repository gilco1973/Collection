import io
import json
import os
import contextlib
import unittest

from tests.helpers import EXAMPLES, tempdir
from aiplayground.__main__ import main


def cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(args))
    return code, out.getvalue(), err.getvalue()


class Cli(unittest.TestCase):
    def test_exit_codes_follow_the_verdict(self):
        with tempdir() as d:
            code, out, _ = cli("run", "--target", os.path.join(EXAMPLES, "demo-safe.json"), "--out", d)
            self.assertEqual(code, 0, out)
            self.assertIn("CLEAR", out)
            code, out, _ = cli("run", "--target", os.path.join(EXAMPLES, "demo-vulnerable.json"), "--out", d)
            self.assertEqual(code, 2)
            self.assertIn("BLOCKED", out)
            code, out, _ = cli("run", "--target", os.path.join(EXAMPLES, "demo-vulnerable.json"), "--probes", "rob-oversized", "--out", d)
            self.assertEqual(code, 0)
            code, out, _ = cli("run", "--target", os.path.join(EXAMPLES, "demo-vulnerable.json"), "--probes", "rob-oversized", "--out", d, "--fail-on", "needs-review")
            self.assertEqual(code, 1)

    def test_triage_and_compare(self):
        with tempdir() as d:
            cli("run", "--target", os.path.join(EXAMPLES, "demo-vulnerable.json"), "--probes", "pi-encoded", "--by", "Ada Placeholder <ada@example.com>", "--out", d)
            report = next(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".json"))
            code, out, _ = cli("triage", report, "--result", "pi-encoded", "--decision", "accepted-risk", "--by", "Bob Placeholder <bob@example.com>", "--reason", "Encoded input never reaches this assistant.")
            self.assertEqual(code, 0, out)
            self.assertIn("verdict now clear", out)
            code, out, err = cli("triage", report, "--result", "pi-encoded", "--decision", "accepted-risk", "--by", "nobody", "--reason", "Encoded input never reaches it.")
            self.assertEqual(code, 3)
            self.assertIn("names a person", err)
            cli("run", "--target", os.path.join(EXAMPLES, "demo-safe.json"), "--probes", "pi-encoded", "--out", os.path.join(d, "after"))
            after = next(os.path.join(d, "after", f) for f in os.listdir(os.path.join(d, "after")) if f.endswith(".json"))
            code, out, _ = cli("compare", report, after)
            self.assertEqual(code, 0)
            self.assertIn("better", out)
            code, out, _ = cli("compare", after, report)
            self.assertEqual(code, 2)

    def test_the_small_commands(self):
        with tempdir() as d:
            code, out, _ = cli("init", d)
            self.assertEqual(code, 0)
            self.assertIn("demo-safe.json", os.listdir(d))
            self.assertEqual(cli("check", os.path.join(d, "openai-chat.json"))[0], 0)
            code, _, err = cli("check", os.path.join(d, "nope.json"))
            self.assertEqual(code, 3)
            self.assertIn("cannot read", err)
        code, out, _ = cli("ask", os.path.join(EXAMPLES, "demo-safe.json"), "What colour is the sky?")
        self.assertEqual(json.loads(out)["text"], "Blue.")
        code, out, _ = cli("tools", os.path.join(EXAMPLES, "mcp-stdio.json"))
        self.assertIn("read_file", out)
        self.assertEqual(cli("tools", os.path.join(EXAMPLES, "demo-safe.json"))[0], 3)
        code, out, _ = cli("probes")
        self.assertIn("pi-indirect-document", out)
        self.assertEqual(cli("run")[0], 3)
        self.assertEqual(cli("run", "--target", os.path.join(EXAMPLES, "demo-safe.json"), "--probes", "nope")[0], 3)

    def test_check_component(self):
        with tempdir() as d:
            code, out, _ = cli("check-component", os.path.join(EXAMPLES, "runbook-answerer"), "--out", d)
            self.assertEqual(code, 0, out)
            self.assertIn("CLEAR", out)

    def test_the_probe_page_is_current(self):
        with open(os.path.join(os.path.dirname(EXAMPLES), "PROBES.md"), encoding="utf-8") as f:
            page = f.read()
        _, table, _ = cli("probes", "--markdown")
        self.assertIn(table.strip(), page, "regenerate PROBES.md: see its first lines")


if __name__ == "__main__":
    unittest.main()
