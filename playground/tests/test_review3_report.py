"""Regressions from the third review, report side: a run whose every security probe ended in an error is incomplete,
two triage commands at once both keep their decision (the report's lock file), the lists and compare see a decision
recorded with the command line, and a report view that disagrees with its file never puts the conflict inside the
report (so a download still verifies)."""
import http.client
import json
import os
import subprocess
import sys
import threading
import time
import unittest
import urllib.parse

from tests.helpers import EXAMPLES, ROOT, tempdir
from tests.test_review_report import ADA, BOB, REASON, cli, rep_with
from aiplayground import __main__ as M
from aiplayground import report as Rp
from aiplayground import runner
from aiplayground import server
from aiplayground.probes import Result
from aiplayground.store import Store

CAROL = "Carol Placeholder <carol@example.com>"


def res(i, status, severity="high", suite="security"):
    return Result(i, i, "LLM01", severity, status, f"{i} {status}", [], "", suite)


def vulnerable_target():
    from aiplayground import config as C
    return C.load({"name": "v", "kind": "demo", "demo": "vulnerable", "environment": "sandbox"})


class NoSecurityProbeJudged(unittest.TestCase):
    def test_every_security_probe_in_error_is_incomplete_whatever_robustness_says(self):
        r = rep_with(res("pi-a", "error", "critical"), res("pi-b", "error", "medium"), res("pi-c", "skipped"),
                     res("rob-a", "fail", "medium", "robustness"), res("rob-b", "pass", "low", "robustness"),
                     res("contract/tests", "pass", "high", "contract"), res("case-1", "pass", "medium", "runbook"))
        self.assertEqual((r["verdict"], r["verdict_reason"]), ("incomplete", Rp.NO_SECURITY_JUDGED))

    def test_one_judged_security_probe_makes_a_verdict(self):
        r = rep_with(res("pi-a", "error", "critical"), res("pi-b", "pass", "medium"), res("rob-a", "fail", "medium", "robustness"))
        self.assertEqual(r["verdict"], "needs-review")

    def test_a_run_without_security_probes_is_judged_on_what_it_ran(self):
        r = rep_with(res("rob-a", "pass", "low", "robustness"), res("contract/tests", "pass", "high", "contract"))
        self.assertEqual(r["verdict"], "clear")
        r = rep_with(res("pi-a", "skipped"), res("rob-a", "fail", "low", "robustness"))
        self.assertEqual(r["verdict"], "needs-review")

    def test_a_blocker_elsewhere_still_blocks_and_nothing_judged_still_holds(self):
        r = rep_with(res("pi-a", "error"), res("contract/manifest", "fail", "high", "contract"))
        self.assertEqual(r["verdict"], "blocked")
        r = rep_with(res("pi-a", "error"), res("rob-a", "error", "low", "robustness"))
        self.assertEqual((r["verdict"], r["verdict_reason"]), ("incomplete", Rp.NOTHING_JUDGED))

    def test_a_triage_does_not_turn_it_into_a_verdict(self):
        r = rep_with(res("pi-a", "error", "medium"), res("rob-a", "pass", "low", "robustness"))
        Rp.triage(r, "pi-a", "accepted-risk", BOB, REASON)
        self.assertEqual(r["verdict"], "incomplete")


class TheLock(unittest.TestCase):
    def test_a_second_holder_waits_then_is_refused(self):
        with tempdir() as d:
            path = os.path.join(d, "r.json")
            with Rp.locked(path) as lock:
                self.assertTrue(os.path.exists(lock))
                t0 = time.monotonic()
                with self.assertRaises(Rp.LockBusy):
                    with Rp.locked(path, wait=0.3):
                        pass
                self.assertGreaterEqual(time.monotonic() - t0, 0.3)
            self.assertFalse(os.path.exists(path + ".lock"))

    def test_a_stale_lock_of_a_dead_owner_is_taken_over_and_a_live_one_is_not(self):
        with tempdir() as d:
            path = os.path.join(d, "r.json")
            dead = subprocess.Popen([sys.executable, "-c", "pass"])
            dead.wait()
            import socket
            with open(path + ".lock", "w") as f:
                f.write(f"{dead.pid} {socket.gethostname()} x\n")
            old = time.time() - 120
            os.utime(path + ".lock", (old, old))
            with Rp.locked(path, wait=0.5):
                pass
            self.assertFalse(os.path.exists(path + ".lock"))
            if os.name == "posix":   # an old lock whose owner is still running is left alone
                with open(path + ".lock", "w") as f:
                    f.write(f"{os.getpid()} {socket.gethostname()} y\n")
                os.utime(path + ".lock", (old, old))
                with self.assertRaises(Rp.LockBusy):
                    with Rp.locked(path, wait=0.2):
                        pass
                os.unlink(path + ".lock")

    def test_a_young_lock_is_never_taken_over(self):
        with tempdir() as d:
            path = os.path.join(d, "r.json")
            with open(path + ".lock", "w") as f:
                f.write("")   # being written: no owner to ask
            with self.assertRaises(Rp.LockBusy):
                with Rp.locked(path, wait=0.2):
                    pass


class ParallelTriage(unittest.TestCase):
    def test_triage_commands_at_once_each_keep_their_decision(self):
        with tempdir() as d:
            code, _, err = cli("run", "--target", os.path.join(EXAMPLES, "demo-vulnerable.json"), "--by", ADA, "--out", d)
            path = next(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".json"))
            ids = [r["id"] for r in Rp.load(path)["results"] if r["status"] in ("fail", "review", "error")][:6]
            self.assertGreaterEqual(len(ids), 4)
            procs = [subprocess.Popen([sys.executable, "-m", "aiplayground", "triage", path, "--result", i, "--decision", "fixed-retest",
                                       "--by", BOB, "--reason", REASON], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for i in ids]
            outs = [p.communicate(timeout=60) for p in procs]
            recorded = sum(1 for o, _ in outs if o.startswith("recorded"))
            self.assertEqual(recorded, len(ids), outs)
            self.assertEqual(sorted(t["result_id"] for t in Rp.load(path)["triage"]), sorted(ids))
            self.assertFalse(os.path.exists(path + ".lock"))

    def test_the_command_waits_for_the_page_and_the_page_for_the_command(self):
        with tempdir() as d:
            s = Store(d)
            try:
                rep = runner.run(vulnerable_target(), probes="pi-roleplay,pi-encoded", by=ADA)
                s.add_run(rep)
                path = s.report_path(rep["id"])
                real = Rp.LOCK_WAIT
                Rp.LOCK_WAIT = 0.5
                try:
                    with Rp.locked(path):   # the page is half-way through a triage: the command waits and is refused
                        code, _, err = cli("triage", path, "--result", "pi-encoded", "--decision", "fixed-retest", "--by", BOB, "--reason", REASON)
                        self.assertEqual(code, 3)
                        self.assertIn("another triage", err)
                finally:
                    Rp.LOCK_WAIT = real
                with Rp.locked(path):
                    done = []
                    t = threading.Thread(target=lambda: done.append(s.triage(rep["id"], "pi-encoded", "fixed-retest", BOB, REASON)))
                    t.start()
                    time.sleep(0.3)
                    self.assertEqual(done, [])   # the page waits for the lock
                t.join(real + 5)
                self.assertEqual([x["result_id"] for x in Rp.load(path)["triage"]], ["pi-encoded"])
            finally:
                s.db.close()


class ListsSeeTheFile(unittest.TestCase):
    def setUp(self):
        self.d = tempdir()
        self.dir = self.d.__enter__()
        self.httpd = server.make_server(self.dir, 0, token="t0k", quiet=True)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.port = self.httpd.server_address[1]
        self.store = self.httpd.store

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.store.db.close()
        self.d.__exit__(None, None, None)

    def get(self, path):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            c.request("GET", "/api/" + path, headers={"X-Playground-Token": "t0k"})
            r = c.getresponse()
            return r.status, dict(r.getheaders()), r.read()
        finally:
            c.close()

    def two_runs(self):
        a = runner.run(vulnerable_target(), probes="pi-roleplay", by=ADA)
        b = runner.run(vulnerable_target(), probes="pi-roleplay", by=ADA)
        self.store.add_run(a)
        self.store.add_run(b)
        return a, b, self.store.report_path(b["id"])

    def test_a_command_line_decision_shows_in_the_list_the_start_page_and_compare(self):
        a, b, path = self.two_runs()
        code, _, err = cli("triage", path, "--result", "pi-roleplay", "--decision", "false-positive", "--by", BOB, "--reason", REASON)
        self.assertEqual(code, 0, err)
        # the list first, before the report was opened
        listed = [r["verdict"] for r in json.loads(self.get("runs")[2]) if r["id"] == b["id"]]
        self.assertEqual(listed, ["clear"])
        cmp = json.loads(self.get(f"compare?a={a['id']}&b={b['id']}")[2])
        self.assertEqual(cmp["after"]["verdict"], "clear")
        self.assertEqual(self.store.run(b["id"])["verdict"], "clear")   # written back to the database
        self.assertEqual(json.loads(self.get("runs/" + b["id"])[2])["verdict"], "clear")

    def test_a_conflict_goes_beside_the_report_and_every_download_is_the_sealed_report(self):
        a, b, path = self.two_runs()
        with open(path, encoding="utf-8") as f:
            backup = f.read()
        self.store.triage(b["id"], "pi-roleplay", "fixed-retest", BOB, REASON)
        with open(path, "w", encoding="utf-8") as f:
            f.write(backup)
        code, _, err = cli("triage", path, "--result", "pi-roleplay", "--decision", "fixed-retest", "--by", CAROL, "--reason", REASON)
        self.assertEqual(code, 0, err)
        st, headers, body = self.get("runs/" + b["id"])
        self.assertEqual(st, 200)
        shown = json.loads(body)
        self.assertNotIn("conflict", shown)
        self.assertIn("disagree", urllib.parse.unquote(headers.get("X-Playground-Conflict", "")))
        Rp.verify(shown)
        st, headers, body = self.get(f"runs/{b['id']}/report.json")
        self.assertEqual(st, 200)
        self.assertNotIn("X-Playground-Conflict", headers)
        dl = os.path.join(self.dir, "downloaded.json")
        with open(dl, "wb") as f:
            f.write(body)
        self.assertNotIn("conflict", json.loads(body))
        self.assertEqual(Rp.load(dl)["id"], b["id"])
        code, _, err = cli("triage", dl, "--result", "pi-roleplay", "--decision", "false-positive", "--by", BOB, "--reason", REASON)
        self.assertEqual(code, 0, err)
        for kind in ("md", "html"):
            st, _, body = self.get(f"runs/{b['id']}/report.{kind}")
            self.assertEqual(st, 200)
            self.assertNotIn(b"disagree", body)
        # compare falls back to the playground's record instead of failing
        st, _, body = self.get(f"compare?a={a['id']}&b={b['id']}")
        self.assertEqual(st, 200, body)

    def test_the_page_reads_the_conflict_from_the_header(self):
        with open(os.path.join(ROOT, "aiplayground", "static", "app.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("X-Playground-Conflict", js)
        self.assertNotIn("rep.conflict", js)


class OutInsideTheComponent(unittest.TestCase):
    def test_the_out_directory_is_passed_on_only_when_the_runner_takes_it(self):
        with tempdir() as d:
            comp = os.path.join(d, "comp")
            os.makedirs(os.path.join(comp, "reports"))
            real = M.runner.run
            try:
                def run_with(target=None, *, component_exclude=None, **kw):
                    return None
                M.runner.run = run_with
                self.assertEqual(M.exclude_out(comp, os.path.join(comp, "reports")), {"component_exclude": [os.path.realpath(os.path.join(comp, "reports"))]})
                self.assertEqual(M.exclude_out(comp, os.path.join(d, "elsewhere")), {})
                self.assertEqual(M.exclude_out(comp, comp), {})
                self.assertEqual(M.exclude_out(None, os.path.join(comp, "reports")), {})

                def run_without(target=None, *, component_dir=None, **kw):
                    return None
                M.runner.run = run_without
                self.assertEqual(M.exclude_out(comp, os.path.join(comp, "reports")), {})
            finally:
                M.runner.run = real


if __name__ == "__main__":
    unittest.main()
