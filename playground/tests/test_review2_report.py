"""Regressions from the second review, report side: credentials in the reason a run is incomplete, a lone surrogate
in an answer, Markdown outside the evidence blocks, triage writing the file it was given (and the page adopting a
decision recorded with the command line), exit codes of a wrong command, a triage log replayed through the rules,
the onboarding block reading only the contract's results, and the server's Content-Length and probe list."""
import json
import os
import re
import socket
import sys
import threading
import unittest

from tests.helpers import EXAMPLES, tempdir, write
from tests.test_review_report import ADA, BOB, REASON, cli, rep_with, res
from aiplayground import report as Rp
from aiplayground import runner
from aiplayground import server
from aiplayground.probes import Attempt, Result
from aiplayground.store import Store
from aiplayground.targets import Reply


def secret_value():
    # built at run time: nothing secret-shaped is written in the test itself
    return "tok-" + os.urandom(6).hex()


def files_of(paths):
    out = {}
    for kind, p in paths.items():
        with open(p, "rb") as f:
            out[kind] = f.read()
    return out


class IncompleteIsScrubbed(unittest.TestCase):
    def test_the_reason_a_run_is_incomplete_never_carries_a_credential(self):
        s = secret_value()
        rep = Rp.build([], target={"name": "t"}, component={"name": "c", "description": f"uses {s}"},
                       tester={"by": ADA, "role": "engineer"}, started=Rp.now(), suites=[], probes=[],
                       secrets=[s, ""], incomplete=f"the solution did not answer a plain question: exit 1: auth failed with token {s}")
        self.assertEqual(rep["verdict"], "incomplete")
        self.assertIn("[secret]", rep["verdict_reason"])
        with tempdir() as d:
            for kind, data in files_of(Rp.save(rep, d)).items():
                self.assertNotIn(s.encode(), data, kind)
            self.assertEqual(Rp.load(os.path.join(d, rep["id"] + ".json"))["verdict"], "incomplete")

    def test_a_command_that_prints_its_credential_on_the_way_out(self):
        s = secret_value()
        with tempdir() as d:
            script = write(os.path.join(d, "leaky.py"), "import os, sys\nsys.stderr.write('auth failed with token ' + os.environ['PG_REVIEW_TOKEN'] + '\\n')\nsys.exit(1)\n")
            t = write(os.path.join(d, "t.json"), {"name": "leaky", "kind": "command", "environment": "sandbox",
                                                  "command": [sys.executable, script], "env": ["PG_REVIEW_TOKEN"]})
            os.environ["PG_REVIEW_TOKEN"] = s
            try:
                code, out, err = cli("run", "--target", t, "--out", os.path.join(d, "out"))
            finally:
                del os.environ["PG_REVIEW_TOKEN"]
            self.assertEqual(code, 2, err)
            self.assertNotIn(s, out + err)
            for f in os.listdir(os.path.join(d, "out")):
                with open(os.path.join(d, "out", f), "rb") as fh:
                    self.assertNotIn(s.encode(), fh.read(), f)


class LoneSurrogate(unittest.TestCase):
    def test_an_answer_with_a_lone_surrogate_is_written_and_read_back(self):
        r = rep_with(res("x", "fail", "high", [Attempt("hi", Reply(text="hello \ud800 world"))]))
        with tempdir() as d:
            paths = Rp.save(r, d)
            back = Rp.load(paths["json"])
            self.assertIn("hello \ufffd world", json.dumps(back["results"], ensure_ascii=False))
            for kind, data in files_of(paths).items():
                data.decode("utf-8")   # every file is valid UTF-8
            self.assertTrue(files_of(paths)["json"].isascii())

    def test_a_failed_write_leaves_the_last_good_files_whole(self):
        r = rep_with(res("x", "fail", "high"))
        with tempdir() as d:
            paths = Rp.save(r, d)
            before = files_of(paths)
            Rp.triage(r, "x", "fixed-retest", BOB, REASON)
            real = Rp.to_html
            Rp.to_html = lambda rep: (_ for _ in ()).throw(RuntimeError("renderer failed"))
            try:
                with self.assertRaises(RuntimeError):
                    Rp.save(r, d)
            finally:
                Rp.to_html = real
            self.assertEqual(files_of(paths), before)
            self.assertEqual(sorted(os.listdir(d)), sorted(os.path.basename(p) for p in paths.values()))   # no temporary left
            real_replace = os.replace
            calls = []

            def failing_replace(src, dst):
                calls.append(dst)
                if dst.endswith(".json"):
                    raise OSError(28, "No space left on device")
                return real_replace(src, dst)
            os.replace = failing_replace
            try:
                with self.assertRaises(OSError):
                    Rp.save(r, d)
            finally:
                os.replace = real_replace
            self.assertEqual(Rp.load(paths["json"])["triage"], [])   # the record is the old one, whole
            self.assertFalse([f for f in os.listdir(d) if f.endswith(".tmp")])


class MarkdownOutsideTheEvidence(unittest.TestCase):
    HOSTILE = ('pay_![approved](https://exfil.example/p.png) [Signed off](https://exfil.example/ok) '
               '<script src="https://exfil.example/x.js"></script> **bold** `code` # heading | cell')

    def test_summaries_titles_and_triage_render_as_text(self):
        r = rep_with(Result("x", "Title [t](https://exfil.example/t)", "LLM01", "high", "fail", self.HOSTILE, []),
                     Result("y", "Held", "LLM01", "low", "pass", self.HOSTILE, []),
                     Result("z", "Skipped", "LLM01", "low", "skipped", self.HOSTILE, []))
        Rp.triage(r, "x", "accepted-risk", BOB, "Accepted: " + self.HOSTILE)
        md = Rp.to_markdown(r)
        for line in md.splitlines():
            if line.startswith("    "):
                continue   # the evidence: an indented code block, never rendered
            self.assertNotRegex(line, r"(?<!\\)\]\(", line)       # no link or image
            self.assertNotRegex(line, r"<(?!/?code)", line)        # no raw HTML
            self.assertNotIn("<script", line)
            self.assertNotRegex(line, r"(?<!\\)\*\*bold", line)
        self.assertIn("\\!\\[approved\\]\\(https://exfil.example/p.png\\)", md)
        self.assertIn("&lt;script", md)
        self.assertIn("\\*\\*bold\\*\\*", md)

    def test_a_code_span_cannot_be_ended_early(self):
        r = rep_with(res("x`](https://exfil.example/)`", "fail", "high"))
        md = Rp.to_markdown(r)
        heading = next(l for l in md.splitlines() if l.startswith("### "))
        self.assertEqual(len(re.findall(r"(?<!\\)`", heading)), 2, heading)   # one span: its two unescaped backticks


class TriageWritesTheFileItWasGiven(unittest.TestCase):
    def run_vulnerable(self, d):
        code, out, err = cli("run", "--target", os.path.join(EXAMPLES, "demo-vulnerable.json"), "--probes", "pi-roleplay,pi-encoded",
                             "--by", ADA, "--out", d)
        return next(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".json"))

    def test_a_renamed_copy_is_triaged_in_place_and_the_original_is_untouched(self):
        with tempdir() as d:
            original = self.run_vulnerable(d)
            copy = os.path.join(d, "pg-copy (1).json")
            with open(original, "rb") as f, open(copy, "wb") as g:
                g.write(f.read())
            code, out, err = cli("triage", copy, "--result", "pi-roleplay", "--decision", "false-positive", "--by", BOB, "--reason", REASON)
            self.assertEqual(code, 0, err)
            self.assertEqual([t["result_id"] for t in Rp.load(copy)["triage"]], ["pi-roleplay"])
            self.assertEqual(Rp.load(original)["triage"], [])
            self.assertTrue(os.path.exists(os.path.join(d, "pg-copy (1).md")) and os.path.exists(os.path.join(d, "pg-copy (1).html")))
            self.assertIn("pg-copy (1).html", out)

    def test_a_decision_landed_meanwhile_is_never_overwritten(self):
        with tempdir() as d:
            path = self.run_vulnerable(d)
            real_load, calls = Rp.load, []

            def load_then_someone_else_triages(p):
                calls.append(p)
                if len(calls) == 2:   # between our read and our write, another person records a decision
                    other = real_load(p)
                    Rp.triage(other, "pi-encoded", "fixed-retest", ADA, REASON)
                    Rp.save_as(other, p)
                return real_load(p)
            Rp.load = load_then_someone_else_triages
            try:
                code, out, err = cli("triage", path, "--result", "pi-roleplay", "--decision", "false-positive", "--by", BOB, "--reason", REASON)
            finally:
                Rp.load = real_load
            self.assertEqual(code, 3)
            self.assertIn("triaged by someone else meanwhile", err)
            self.assertEqual([t["result_id"] for t in Rp.load(path)["triage"]], ["pi-encoded"])

    def test_the_page_adopts_a_decision_recorded_with_the_command_line(self):
        with tempdir() as d:
            s = Store(d)
            try:
                rep = runner.run(vulnerable_target(), probes="pi-roleplay,pi-encoded", by=ADA)
                s.add_run(rep)
                path = os.path.join(d, "reports", rep["id"] + ".json")
                code, _, err = cli("triage", path, "--result", "pi-roleplay", "--decision", "false-positive", "--by", BOB, "--reason", REASON)
                self.assertEqual(code, 0, err)
                s.triage(rep["id"], "pi-encoded", "false-positive", BOB, REASON)
                self.assertEqual([t["result_id"] for t in Rp.load(path)["triage"]], ["pi-roleplay", "pi-encoded"])
                self.assertEqual([t["result_id"] for t in s.run(rep["id"])["triage"]], ["pi-roleplay", "pi-encoded"])
                # the file and the database now disagree (a decision on each side): the page refuses, neither is lost
                cli("triage", path, "--result", "pi-roleplay", "--decision", "fixed-retest", "--by", BOB, "--reason", REASON)
                db = s.run(rep["id"])
                Rp.triage(db, "pi-encoded", "fixed-retest", BOB, REASON)
                s.db.execute("UPDATE runs SET report = ? WHERE id = ?", (json.dumps(db), rep["id"]))
                with self.assertRaisesRegex(ValueError, "disagree"):
                    s.triage(rep["id"], "pi-roleplay", "false-positive", BOB, REASON)
                self.assertEqual(Rp.load(path)["triage"][-1]["result_id"], "pi-roleplay")
            finally:
                s.db.close()


def vulnerable_target():
    from aiplayground import config as C
    return C.load({"name": "v", "kind": "demo", "demo": "vulnerable", "environment": "sandbox"})


class ExitCodes(unittest.TestCase):
    def test_a_wrong_command_is_3_before_anything_runs(self):
        with tempdir() as d:
            afile = write(os.path.join(d, "afile"), "x")
            safe = os.path.join(EXAMPLES, "demo-safe.json")
            for args, says in ((("check-component", os.path.join(d, "no-such-thing"), "--out", d), "not a directory"),
                               (("run", "--target", safe, "--component", os.path.join(d, "no-such-thing"), "--out", d), "not a directory"),
                               (("run", "--target", safe, "--out", afile), "is not a directory"),
                               (("run", "--target", safe, "--out", os.path.join(afile, "reports")), "cannot be made"),
                               (("triage", d, "--result", "x", "--decision", "fixed-retest", "--by", BOB, "--reason", REASON), "is a directory"),
                               (("compare", os.path.join(d, "none.json"), os.path.join(d, "none.json")), "No such file")):
                code, out, err = cli(*args)
                self.assertEqual(code, 3, (args, out, err))
                self.assertIn(says, err, args)
                self.assertNotIn("Traceback", err)
                self.assertEqual(len(err.strip().splitlines()), 1, err)
            self.assertEqual(sorted(os.listdir(d)), ["afile"])   # nothing ran, nothing was written


class TriageLogReplayed(unittest.TestCase):
    def forge(self, rep, **entry):
        e = {"result_id": "x", "decision": "accepted-risk", "by": ADA, "reason": REASON, "at": Rp.now(), "prev": rep["triage_head"]}
        e.update(entry)
        rep["triage"].append(e)
        rep["triage_head"] = Rp.triage_hash(e)
        return rep

    def test_an_entry_appended_by_hand_with_its_chain_recomputed_is_refused(self):
        cases = {
            "the tester clears their own critical finding": {},
            "the tester under a plus address": {"by": "Ada Placeholder <ada+sec@example.com>"},
            "a reason of one letter": {"by": BOB, "reason": "x"},
            "not a person": {"by": "bob"},
            "a finding that does not exist": {"by": BOB, "result_id": "nope"},
            "a finding that held": {"by": BOB, "result_id": "p"},
            "an unknown decision": {"by": BOB, "decision": "waived"},
            "a person not recorded as triage records one": {"by": "  Bob   Placeholder <bob@example.com>"},
        }
        for name, entry in cases.items():
            with self.subTest(name), tempdir() as d:
                rep = self.forge(rep_with(res("x", "fail", "critical"), res("p", "pass")), **entry)
                path = write(os.path.join(d, "r.json"), rep)
                with self.assertRaisesRegex(ValueError, "the triage log breaks the rules"):
                    Rp.load(path)
        with tempdir() as d:   # a run with no named tester: nobody clears its critical finding
            rep = self.forge(rep_with(res("x", "fail", "critical"), by=""), by=BOB)
            with self.assertRaisesRegex(ValueError, "names no tester"):
                Rp.load(write(os.path.join(d, "r.json"), rep))
        with tempdir() as d:   # the same entry, made by the rules, loads
            rep = self.forge(rep_with(res("x", "fail", "critical")), by=BOB)
            self.assertEqual(Rp.load(write(os.path.join(d, "r.json"), rep))["verdict"], "clear")

    def test_a_plus_address_is_the_same_person(self):
        self.assertEqual(Rp.identity("Ada Placeholder <ada+sec@example.com>"), Rp.identity(ADA))
        self.assertEqual(Rp.identity("Ada <ADA+X+Y@Example.com>"), "ada@example.com")
        r = rep_with(res("x", "fail", "high"))
        with self.assertRaisesRegex(ValueError, "someone other than"):
            Rp.triage(r, "x", "accepted-risk", "Ada Placeholder <ada+sec@example.com>", REASON)


class OnboardingReadsTheContract(unittest.TestCase):
    def test_a_suite_named_contract_cannot_stand_in_for_the_contract_check(self):
        fake = Result("contract/tests", "tests", "QUAL", "info", "pass", "the suite says so", [], suite="contract")
        mine = rep_with(fake)
        self.assertEqual(mine["onboarding"]["tests_green"], "pass")   # the contract's own result counts
        other = Result("contract/tests", "tests", "QUAL", "info", "pass", "a case", [], suite="cases")
        self.assertEqual(rep_with(other)["onboarding"]["tests_green"], "not run")


class VerdictReasons(unittest.TestCase):
    def test_a_run_where_every_applicable_check_ended_in_an_error_judged_nothing(self):
        r = rep_with(res("a", "error", "high"), res("b", "error", "low"), res("c", "skipped", "low"))
        self.assertEqual((r["verdict"], r["verdict_reason"]), ("incomplete", Rp.NOTHING_JUDGED))
        for other in ("pass", "fail", "review"):
            r = rep_with(res("a", "error", "low"), res("b", other, "low"))
            self.assertEqual(r["verdict"], "needs-review", other)

    def test_a_long_list_of_findings_says_how_many_are_not_named(self):
        r = rep_with(*[res(f"f{i}", "fail", "critical") for i in range(9)])
        self.assertTrue(r["verdict_reason"].startswith("9 critical or high finding(s) failed: f0, f1"), r["verdict_reason"])
        self.assertTrue(r["verdict_reason"].endswith("f5, and 3 more"), r["verdict_reason"])
        r = rep_with(*[res(f"m{i}", "review", "medium") for i in range(7)])
        self.assertTrue(r["verdict_reason"].endswith("m5, and 1 more"), r["verdict_reason"])
        r = rep_with(*[res(f"m{i}", "review", "medium") for i in range(6)])
        self.assertNotIn("more", r["verdict_reason"])


class ServerEdges(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempdir()
        cls.data = cls.tmp.__enter__()
        cls.httpd = server.make_server(cls.data, port=0, token="test-token", quiet=True)
        cls.port = cls.httpd.server_address[1]
        cls.httpd.store.save_target({"name": "edge-demo", "kind": "demo", "demo": "safe", "environment": "sandbox"})
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.httpd.store.db.close()
        cls.tmp.__exit__(None, None, None)

    def raw(self, request: bytes) -> bytes:
        with socket.create_connection(("127.0.0.1", self.port), timeout=30) as s:
            s.sendall(request)
            data = b""
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    return data
                data += chunk

    def test_a_content_length_in_other_digits_is_a_400(self):
        for n in (b"\xb2", b"\xd9\xa3", b"1_0", b"+5", b" "):
            got = self.raw(b"POST /api/runs HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nX-Playground-Token: test-token\r\n"
                           b"Content-Type: application/json\r\nContent-Length: %s\r\n\r\n{}" % (self.port, n))
            self.assertTrue(got.startswith(b"HTTP/1.1 400"), (n, got[:120]))
            self.assertIn(b"Content-Length is a number of bytes", got)

    def test_a_probe_list_of_anything_but_ids_is_a_422(self):
        for probes in ([{}], [1], [None], ["pi-encoded", ["x"]]):
            body = json.dumps({"target": "edge-demo", "probes": probes}).encode()
            got = self.raw(b"POST /api/runs HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nX-Playground-Token: test-token\r\nConnection: close\r\n"
                           b"Content-Type: application/json\r\nContent-Length: %d\r\n\r\n%s" % (self.port, len(body), body))
            self.assertTrue(got.startswith(b"HTTP/1.1 422"), (probes, got[:200]))

    def test_two_suites_of_one_name_are_a_422_before_the_run(self):
        suite = {"name": "twice", "cases": [{"id": "a", "prompt": "hi", "expect": {"max_latency_ms": 60000}}]}
        body = json.dumps({"target": "edge-demo", "probes": "none", "suites": [suite, suite]}).encode()
        got = self.raw(b"POST /api/runs HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nX-Playground-Token: test-token\r\nConnection: close\r\n"
                       b"Content-Type: application/json\r\nContent-Length: %d\r\n\r\n%s" % (self.port, len(body), body))
        self.assertTrue(got.startswith(b"HTTP/1.1 422"), got[:200])
        self.assertIn(b"same name", got)


if __name__ == "__main__":
    unittest.main()


class ViewAdoptsTheFile(unittest.TestCase):
    def test_a_decision_recorded_on_the_file_shows_in_the_page_before_any_page_triage(self):
        import json as _json
        import threading
        import urllib.request
        from aiplayground import report as _Rp
        from aiplayground import runner as _runner
        from aiplayground import server as _server
        from tests.helpers import target as _target, tempdir as _tempdir
        with _tempdir() as d:
            httpd = _server.make_server(d, port=0, token="t", quiet=True)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                rep = _runner.run(_target(kind="demo", demo="vulnerable"), probes="pi-encoded", by="Ada Placeholder <ada@example.com>")
                httpd.store.add_run(rep)
                on_file = _Rp.load(httpd.store.report_path(rep["id"]))
                _Rp.triage(on_file, "pi-encoded", "accepted-risk", "Bob Placeholder <bob@example.com>", "Encoded input never reaches it in use.")
                _Rp.save(on_file, os.path.join(d, "reports"))
                req = urllib.request.Request(f"http://127.0.0.1:{httpd.server_address[1]}/api/runs/{rep['id']}", headers={"X-Playground-Token": "t"})
                with urllib.request.urlopen(req) as r:
                    shown = _json.loads(r.read())
                self.assertEqual([t["result_id"] for t in shown["triage"]], ["pi-encoded"])
                self.assertNotIn("conflict", shown)
            finally:
                httpd.shutdown()
                httpd.server_close()
                httpd.store.db.close()
