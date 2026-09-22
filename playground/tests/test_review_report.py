"""Regressions from the review: separation of duties in triage, Markdown injection, report integrity, a run that
judged nothing, concurrent triage, request bodies, IPv6 loopback, `init`, and the page's compare direction."""
import contextlib
import copy
import io
import json
import os
import socket
import subprocess
import sys
import threading
import unittest
import http.client

from tests.helpers import EXAMPLES, ROOT, tempdir, target, write
from aiplayground import report as Rp
from aiplayground import runner
from aiplayground import server
from aiplayground.__main__ import main
from aiplayground.probes import Attempt, Result
from aiplayground.store import Store
from aiplayground.targets import Reply

ADA = "Ada Placeholder <ada@example.com>"
BOB = "Bob Placeholder <bob@example.com>"
REASON = "Reviewed by hand; the planted marker is quoted, not obeyed."


def res(i, status, severity="high", evidence=()):
    return Result(i, i, "LLM01", severity, status, f"{i} {status}", list(evidence))


def rep_with(*results, by=ADA):
    return Rp.build(list(results), target={"name": "t"}, component=None, tester={"by": by, "role": "engineer"},
                    started="2026-01-01T00:00:00Z", suites=[], probes=[])


def cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(args))
    return code, out.getvalue(), err.getvalue()


class SeparationOfDuties(unittest.TestCase):
    def test_the_tester_cannot_clear_their_own_critical_or_high_finding_by_any_spelling(self):
        spellings = (ADA, ADA.replace(" <", "  <"), ADA.replace("ada@", "ADA@"), ADA + "\n", " " + ADA + " ",
                     "Someone Else <ada@example.com>")
        for severity in ("critical", "high"):
            for decision in ("accepted-risk", "false-positive"):
                for by in spellings:
                    r = rep_with(res("a", "fail", severity))
                    with self.assertRaisesRegex(ValueError, "someone other than the person who ran the test", msg=(severity, decision, by)):
                        Rp.triage(r, "a", decision, by, REASON)
                    self.assertEqual(r["verdict"], "blocked")
                    self.assertEqual(r["triage"], [])

    def test_a_run_without_a_named_tester_takes_no_clearing_decision_on_a_critical_or_high_finding(self):
        for tester in ("", "   ", "ada", None):
            r = rep_with(res("a", "fail", "critical"), res("m", "fail", "medium"), by=tester)
            for decision in ("accepted-risk", "false-positive"):
                with self.assertRaisesRegex(ValueError, "the run names no tester; a critical or high finding is triaged on a run with a named tester"):
                    Rp.triage(r, "a", decision, BOB, REASON)
            Rp.triage(r, "m", "accepted-risk", BOB, REASON)   # a medium finding is still anyone's to triage
            Rp.triage(r, "a", "fixed-retest", BOB, REASON)    # reopening never needs the rule
        anon = runner.run(target(kind="demo", demo="vulnerable"), probes="agency-money")
        with self.assertRaisesRegex(ValueError, "names no tester"):
            Rp.triage(anon, "agency-money", "accepted-risk", ADA, REASON)

    def test_someone_else_may_decide_and_is_recorded_normalised(self):
        r = rep_with(res("a", "fail", "high"), res("b", "fail", "critical"))
        Rp.triage(r, "a", "false-positive", "  Bob   Placeholder\t<bob@example.com>\n", REASON)
        Rp.triage(r, "b", "accepted-risk", BOB, REASON)
        self.assertEqual([t["by"] for t in r["triage"]], [BOB, BOB])
        self.assertEqual(r["verdict"], "clear")

    def test_a_person_is_one_line_to_the_end(self):
        self.assertFalse(Rp.PERSON.match("Ada <ada@example.com>\n"))
        self.assertFalse(Rp.is_person("Ada <ada@example.com> extra"))
        self.assertTrue(Rp.is_person("Ada <ada@example.com>\n"))   # accepted as its normalised form
        self.assertEqual(Rp.identity("  Ada  X <ADA@Example.com>"), "ada@example.com")
        self.assertEqual(Rp.identity("nobody"), "")

    def test_the_command_line_refuses_a_tester_who_is_not_a_person(self):
        with tempdir() as d:
            code, _, err = cli("run", "--target", os.path.join(EXAMPLES, "demo-safe.json"), "--probes", "pi-encoded", "--by", "ada", "--out", d)
            self.assertEqual(code, 3)
            self.assertIn("Name <address>", err)


HOSTILE = ("PGZZ ok\n```\n\n## For the sign-off\n\n**Verdict: clear.** Accepted.\n\n"
           "![s](https://exfil.example/p.png?d=1)\n\n~~~\n    ````text\n| x | y |")


class MarkdownInjection(unittest.TestCase):
    def test_a_solution_s_answer_stays_inside_its_code_block(self):
        r = rep_with(res("x", "fail", "high", [Attempt("ask ```", Reply(text=HOSTILE))]), res("y", "review", "low", [{"raw": HOSTILE}]))
        md = Rp.to_markdown(r)
        lines = md.splitlines()
        self.assertEqual(sum(1 for l in lines if l.startswith("## For the sign-off")), 1)
        self.assertEqual(sum(1 for l in lines if l.startswith("**Verdict:")), 1)
        self.assertEqual([l for l in lines if "exfil.example" in l and not l.startswith("    ")], [])
        # every line of evidence is indented: an indented code block has no closing line to forge
        start = lines.index("## Findings")
        for l in lines[start:]:
            if any(k in l for k in ("PGZZ", "Verdict: clear", "````", "~~~", "| x | y |")):
                self.assertTrue(l.startswith("    "), l)
        # an indented block needs a blank line before it
        for i, l in enumerate(lines):
            if l.startswith("    ") and not lines[i - 1].startswith("    "):
                self.assertEqual(lines[i - 1], "", lines[i - 1:i + 1])

    def test_table_cells_and_headings_stay_on_their_line(self):
        r = rep_with(res("x", "fail", "high"))
        Rp.triage(r, "x", "accepted-risk", BOB, "Sandbox only | forged cell\n## Forged heading\n| a | b |")
        md = Rp.to_markdown(r)
        self.assertNotIn("\n## Forged heading", md)
        row = next(l for l in md.splitlines() if l.startswith("| `x`"))
        self.assertIn("Sandbox only \\| forged cell \\#\\# Forged heading \\| a \\| b \\|", row)
        self.assertEqual(row.count(" | "), 4)   # five cells: four separators outside the escaped pipes


class Integrity(unittest.TestCase):
    def saved(self, r, d):
        return Rp.save(r, d)["json"]

    def edit(self, path, fn):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        fn(data)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_two_identical_runs_never_share_an_id(self):
        a, b = rep_with(res("x", "pass")), rep_with(res("x", "pass"))
        self.assertNotEqual(a["id"], b["id"])
        self.assertNotEqual(a["nonce"], b["nonce"])
        comp = os.path.join(EXAMPLES, "runbook-answerer")
        c = runner.run(None, component_dir=comp, run_component=False, by=ADA)
        e = runner.run(None, component_dir=comp, run_component=False, by=BOB, role="ai-security")
        self.assertNotEqual(c["id"], e["id"])
        with tempdir() as d:
            s = Store(d)
            try:
                s.add_run(c)
                s.add_run(e)
                self.assertEqual(len(s.runs()), 2)
                self.assertEqual(s.run(c["id"])["tester"]["by"], ADA)
            finally:
                s.db.close()

    def test_an_edited_report_is_refused(self):
        edits = {
            "tester": lambda d: d["tester"].update(by=BOB),
            "role": lambda d: d["tester"].update(role="ai-security"),
            "result": lambda d: d["results"][0].update(status="pass"),
            "severity": lambda d: d["results"][0].update(severity="low"),
            "started": lambda d: d.update(started="2020-01-01T00:00:00Z"),
            "nonce": lambda d: d.update(nonce="0" * 32),
            "incomplete": lambda d: d.update(incomplete="unreachable"),
        }
        for name, fn in edits.items():
            with tempdir() as d:
                path = self.saved(rep_with(res("x", "fail", "critical"), res("y", "pass")), d)
                self.assertEqual(Rp.load(path)["verdict"], "blocked")
                self.edit(path, fn)
                with self.assertRaisesRegex(ValueError, "edited after it was written; its id no longer matches", msg=name):
                    Rp.load(path)
        with tempdir() as d:
            path = self.saved(rep_with(res("x", "fail", "critical")), d)
            self.edit(path, lambda r: r.pop("nonce"))
            with self.assertRaisesRegex(ValueError, "no nonce"):
                Rp.load(path)

    def test_an_edited_verdict_is_recomputed_from_what_was_recorded(self):
        with tempdir() as d:
            path = self.saved(rep_with(res("x", "fail", "critical")), d)
            self.edit(path, lambda r: r.update(verdict="clear", verdict_reason="all fine"))
            self.assertEqual(Rp.load(path)["verdict"], "blocked")

    def test_the_triage_log_is_a_hash_chain(self):
        r = rep_with(res("x", "fail", "high"), res("y", "fail", "medium"))
        Rp.triage(r, "x", "accepted-risk", BOB, REASON)
        Rp.triage(r, "y", "false-positive", BOB, REASON)
        self.assertEqual(r["triage"][0]["prev"], r["id"])
        self.assertEqual(r["triage"][1]["prev"], Rp.triage_hash(r["triage"][0]))
        self.assertEqual(r["triage_head"], Rp.triage_hash(r["triage"][1]))
        edits = {
            "dropped the last": lambda d: d["triage"].pop(),
            "dropped the first": lambda d: d["triage"].pop(0),
            "reworded a reason": lambda d: d["triage"][0].update(reason="Something else entirely."),
            "renamed the person": lambda d: d["triage"][1].update(by=ADA),
            "forged an entry": lambda d: d["triage"].append({"result_id": "x", "decision": "false-positive", "by": BOB, "reason": REASON, "at": "x"}),
            "reordered": lambda d: d["triage"].reverse(),
            "a list no more": lambda d: d.update(triage={"x": 1}),
        }
        for name, fn in edits.items():
            with tempdir() as d:
                path = self.saved(copy.deepcopy(r), d)
                self.assertEqual(Rp.load(path)["verdict"], "clear")
                self.edit(path, fn)
                with self.assertRaisesRegex(ValueError, "triage log was edited after it was written", msg=name):
                    Rp.load(path)

    def test_triage_through_the_command_line_keeps_the_chain_and_refuses_an_edited_report(self):
        with tempdir() as d:
            cli("run", "--target", os.path.join(EXAMPLES, "demo-vulnerable.json"), "--probes", "pi-encoded", "--by", ADA, "--out", d)
            report = next(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".json"))
            code, out, err = cli("triage", report, "--result", "pi-encoded", "--decision", "accepted-risk", "--by", BOB, "--reason", REASON)
            self.assertEqual(code, 0, err)
            code, out, err = cli("triage", report, "--result", "pi-encoded", "--decision", "fixed-retest", "--by", BOB, "--reason", REASON)
            self.assertEqual(code, 0, err)
            self.assertEqual(len(Rp.load(report)["triage"]), 2)
            self.edit(report, lambda r: r["tester"].update(by=BOB))
            code, _, err = cli("triage", report, "--result", "pi-encoded", "--decision", "accepted-risk", "--by", ADA, "--reason", REASON)
            self.assertEqual(code, 3)
            self.assertIn("its id no longer matches", err)
            code, _, err = cli("compare", report, report)
            self.assertEqual(code, 3)


class NothingChecked(unittest.TestCase):
    def test_a_run_that_judged_nothing_is_incomplete_not_clear(self):
        r = rep_with(res("a", "skipped"), res("b", "skipped"))
        self.assertEqual((r["verdict"], r["verdict_reason"]),
                         ("incomplete", "nothing applicable was checked: choose probes or cases that apply to this solution"))
        self.assertEqual(rep_with()["verdict"], "incomplete")
        self.assertEqual(rep_with(res("a", "pass"), res("b", "skipped"))["verdict"], "clear")
        self.assertEqual(runner.run(target(kind="demo", demo="safe"), probes="none")["verdict"], "incomplete")

    def test_the_command_line_exits_2(self):
        with tempdir() as d:
            code, out, _ = cli("run", "--target", os.path.join(EXAMPLES, "demo-safe.json"), "--probes", "tool-alive", "--out", d)
            self.assertEqual(code, 2, out)
            self.assertIn("INCOMPLETE: nothing applicable was checked", out)


class ConcurrentTriage(unittest.TestCase):
    def test_every_decision_made_at_the_same_time_is_kept(self):
        with tempdir() as d:
            s = Store(d)
            try:
                rep = rep_with(*[res(f"f{i}", "fail", "medium") for i in range(8)], res("h", "fail", "high"))
                s.add_run(rep)
                ids = [r["id"] for r in rep["results"]]
                barrier = threading.Barrier(len(ids))
                errors = []

                def tri(rid):
                    barrier.wait()
                    try:
                        s.triage(rep["id"], rid, "false-positive", BOB, REASON)
                    except Exception as e:   # noqa: BLE001 - reported below
                        errors.append(e)

                threads = [threading.Thread(target=tri, args=(i,)) for i in ids]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()
                self.assertEqual(errors, [])
                kept = s.run(rep["id"])
                self.assertEqual(sorted(t["result_id"] for t in kept["triage"]), sorted(ids))
                self.assertEqual(kept["verdict"], "clear")
                self.assertEqual(Rp.load(os.path.join(d, "reports", rep["id"] + ".json"))["verdict"], "clear")
            finally:
                s.db.close()


def ipv6_loopback() -> bool:
    try:
        with socket.socket(socket.AF_INET6) as s:
            s.bind(("::1", 0))
        return True
    except OSError:
        return False


class ServerBodies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempdir()
        cls.data = cls.tmp.__enter__()
        cls.httpd = server.make_server(cls.data, port=0, token="test-token", quiet=True)
        cls.port = cls.httpd.server_address[1]
        cls.httpd.store.save_target({"name": "body-demo", "kind": "demo", "demo": "safe", "environment": "sandbox"})
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.httpd.store.db.close()
        cls.tmp.__exit__(None, None, None)

    def post(self, path, raw, conn=None):
        c = conn or http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            c.request("POST", path, body=raw, headers={"X-Playground-Token": "test-token", "Content-Type": "application/json"})
            r = c.getresponse()
            return r.status, json.loads(r.read())
        finally:
            if conn is None:
                c.close()

    def test_a_body_that_is_not_a_json_object_is_a_422(self):
        for path in ("/api/targets", "/api/runs", "/api/targets/body-demo/ask", "/api/targets/body-demo/call"):
            for raw in (b"[]", b'"x"', b"3", b"null", b"{not json", b"\xff\xfe"):
                code, out = self.post(path, raw)
                self.assertEqual(code, 422, (path, raw, out))
                self.assertIn("the body is a JSON object", out["error"])

    def test_wrong_shapes_inside_a_run_request_are_a_422(self):
        for body in ({"target": ["body-demo"]}, {"component": 3}, {"target": "body-demo", "role": "admin"},
                     {"target": "body-demo", "suites": "x"}, {"target": "body-demo", "probes": 3}, {"target": "body-demo", "by": "ada"}):
            code, out = self.post("/api/runs", json.dumps(body).encode())
            self.assertEqual(code, 422, (body, out))

    def test_the_connection_survives_a_refusal(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            self.assertEqual(self.post("/api/runs", b"[]", c)[0], 422)
            c.request("POST", "/api/runs", body=b"[1, 2, 3]", headers={"X-Playground-Token": "wrong", "Content-Type": "application/json"})
            r = c.getresponse()
            r.read()
            self.assertEqual(r.status, 401)
            c.request("GET", "/api/meta", headers={"X-Playground-Token": "test-token"})
            r = c.getresponse()
            self.assertEqual((r.status, json.loads(r.read())["roles"]), (200, ["engineer", "ai-security"]))
        finally:
            c.close()


class Ipv6(unittest.TestCase):
    def test_the_ipv6_loopback_gets_an_ipv6_server(self):
        self.assertEqual(server.ThreadingHTTPServerV6.address_family, socket.AF_INET6)

    @unittest.skipUnless(ipv6_loopback(), "this machine has no IPv6 loopback")
    def test_serve_on_ipv6_loopback(self):
        with tempdir() as d:
            httpd = server.make_server(d, port=0, host="::1", token="t6", quiet=True)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                port = httpd.server_address[1]
                c = http.client.HTTPConnection("::1", port, timeout=30)
                c.request("GET", "/api/meta", headers={"X-Playground-Token": "t6", "Host": f"[::1]:{port}"})
                r = c.getresponse()
                self.assertEqual(r.status, 200)
                r.read()
                c.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
                httpd.store.db.close()

    @unittest.skipIf(ipv6_loopback(), "this machine has an IPv6 loopback")
    def test_serve_says_why_when_there_is_no_ipv6(self):
        with tempdir() as d:
            code, _, err = cli("serve", "--host", "::1", "--port", "0", "--data", d)
            self.assertEqual(code, 2)
            self.assertIn("cannot listen on ::1", err)


class Init(unittest.TestCase):
    def test_init_copies_what_the_examples_point_at_and_they_work_from_the_copy(self):
        with tempdir() as d:
            dest = os.path.join(d, "mine")
            code, out, _ = cli("init", dest)
            self.assertEqual(code, 0)
            names = os.listdir(dest)
            self.assertIn("demo_mcp.py", names)
            self.assertIn("runbook-answerer", names)
            for dirpath, dirnames, filenames in os.walk(dest):
                self.assertNotIn("__pycache__", dirnames)
                self.assertFalse([f for f in filenames if f.endswith(".pyc")])
            self.assertTrue(os.path.exists(os.path.join(dest, "runbook-answerer", "component.json")))
            # from a directory with no playground in it, as the copy would be used
            elsewhere = os.path.join(d, "elsewhere")
            os.makedirs(elsewhere)
            env = dict(os.environ, PYTHONPATH=ROOT)
            tools = subprocess.run([sys.executable, "-m", "aiplayground", "tools", os.path.join(dest, "mcp-stdio.json")],
                                   cwd=elsewhere, env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(tools.returncode, 0, tools.stderr)
            self.assertIn("read_file", tools.stdout)
            ask = subprocess.run([sys.executable, "-m", "aiplayground", "ask", os.path.join(dest, "python-function.json"), "How do I restart the queue?"],
                                 cwd=elsewhere, env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(ask.returncode, 0, ask.stderr)
            self.assertIn("text", json.loads(ask.stdout))

    def test_init_leaves_existing_files_alone(self):
        with tempdir() as d:
            write(os.path.join(d, "demo_mcp.py"), "# mine\n")
            write(os.path.join(d, "runbook-answerer", "answerer.py"), "# mine\n")
            write(os.path.join(d, "demo-safe.json"), "{}")
            code, out, _ = cli("init", d)
            self.assertEqual(code, 0)
            for rel, body in (("demo_mcp.py", "# mine\n"), (os.path.join("runbook-answerer", "answerer.py"), "# mine\n"), ("demo-safe.json", "{}")):
                with open(os.path.join(d, rel), encoding="utf-8") as f:
                    self.assertEqual(f.read(), body)
            self.assertFalse(os.path.exists(os.path.join(d, "runbook-answerer", "component.json")))
            self.assertEqual(cli("init", d)[1].split(":")[0], "wrote 0 file(s) to " + d)


class PageCompare(unittest.TestCase):
    def test_the_page_orders_the_two_runs_by_when_they_started(self):
        with open(os.path.join(ROOT, "aiplayground", "static", "app.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("viewCompare(inOrder())", js)
        self.assertIn('"compare?a=" + encodeURIComponent(ids[0]) + "&b=" + encodeURIComponent(ids[1])', js)


if __name__ == "__main__":
    unittest.main()
