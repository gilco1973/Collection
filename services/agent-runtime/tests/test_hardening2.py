"""The fourth review's findings in the runtime: a run stopped by the id an operator has, a health route that never
walks the chain, a switch thrown without the identity provider, a budget stop that is final, the run limit per
person, the record commands on odd paths and a fresh volume, and a posted run rebuilt from the record."""
import contextlib, io, json, os, sqlite3, tempfile, threading, unittest, urllib.error, urllib.request
from agentrt import vendor  # noqa: F401
from agentrt.app import serve
from agentrt.settings import Settings
from agentrt.wiring import build, open_record


def cli(argv) -> tuple:
    from agentrt.__main__ import main
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = main(argv)
    return rc, out.getvalue().strip()


class Api(unittest.TestCase):
    """A server over a file record (the CLI opens the same file), one run kept in memory."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.saved = dict(os.environ)
        os.environ["AGENT_DB"] = os.path.join(self.tmp.name, "record.db")
        self.w = build(Settings(db_path=os.environ["AGENT_DB"]))
        self.httpd = serve(self.w, "127.0.0.1", 0, "https://agents.example/mcp", max_runs=1); threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown(); self.w.conn.close()
        os.environ.clear(); os.environ.update(self.saved); self.tmp.cleanup()

    def req(self, method, path, body=None, token="x", base=None):
        h = {"Content-Type": "application/json"}
        if token: h["Authorization"] = f"Bearer {self.w.token('u_dana') if token == 'x' else token}"
        try:
            r = urllib.request.urlopen(urllib.request.Request((base or self.base) + path, data=json.dumps(body).encode() if body is not None else None, headers=h, method=method), timeout=10)
            return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def run_one(self):
        s, r = self.req("POST", "/runs", {"ticket_key": "INC-7", "service": "checkout"}); self.assertEqual(s, 200); return r

    def test_a_run_names_its_run_id_and_is_stopped_by_its_session_id(self):
        r = self.run_one(); sid = r["session"]
        self.assertTrue(r["run_id"].startswith("run_")); self.assertEqual(r["run_id"], self.w.harness.sessions.load_json(sid)["run_id"])
        rc, out = cli(["stop", "run", sid, "--by", "u_ops"])
        self.assertEqual((rc, out.startswith(f"run {r['run_id']}: stopped")), (0, True), out)
        self.assertEqual(self.w.kills.state(self.w.harness.consumer, "incidents", r["run_id"]), "run", "the switch is on the run id the harness checks")
        s, body = self.req("POST", f"/runs/{sid}/confirm", {"hash": r["parked"]["hash"]})
        self.assertEqual((s, body["reason"], "retry" in body), (409, "kill.run", False), "a thrown switch is final: nothing to retry")
        self.assertEqual(self.w.targets["tickets"].comments, [])
        rc, out = cli(["stop", "run", "ses_nobody", "--by", "u_ops"]); self.assertEqual(rc, 2); self.assertIn("unknown session: ses_nobody", out)
        rc, out = cli(["stop", "run", r["run_id"], "--by", "u_ops"]); self.assertEqual(rc, 2, "a run id is not what an operator has; the session id is")
        for bad in (self.w.template["name"], "agent:other", "incidents"):
            rc, out = cli(["stop", "consumer", bad, "--by", "u_ops"]); self.assertEqual(rc, 2, bad); self.assertIn(self.w.harness.consumer, out)
        for ok in ("-", "self", self.w.harness.consumer):
            rc, out = cli(["stop", "consumer", ok, "--by", "u_ops"]); self.assertEqual(rc, 0, ok); self.assertTrue(out.startswith(f"consumer {self.w.harness.consumer}:"), out)

    def test_health_counts_the_record_and_ready_walks_it_at_most_once_per_interval(self):
        walks = []
        real = self.w.audit.verify
        self.w.audit.verify = lambda: walks.append(1) or real()
        for _ in range(3):
            s, h = self.req("GET", "/health", token=None)
            self.assertEqual((s, h["records"], h["head"]), (200, self.w.conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0], self.w.audit.head()))
        self.assertEqual(walks, [], "an anonymous health probe never walks the chain")
        for _ in range(3):
            self.assertEqual(self.req("GET", "/ready", token=None)[1]["checks"]["record"], "ok")
        self.assertEqual(len(walks), 1, "readiness walks the chain once per interval, whoever asks")
        self.run_one()
        self.w.conn.execute("UPDATE audit SET body = '{\"tampered\": true}' WHERE seq = (SELECT MAX(seq) FROM audit)"); self.w.conn.commit()
        self.assertEqual(self.req("GET", "/ready", token=None)[0], 200, "within the interval the last walk stands")
        fresh = serve(self.w, "127.0.0.1", 0, "https://agents.example/mcp", verify_interval_s=0.0); threading.Thread(target=fresh.serve_forever, daemon=True).start()
        try:
            s, body = self.req("GET", "/ready", token=None, base=f"http://127.0.0.1:{fresh.server_address[1]}")
            self.assertEqual((s, body["checks"]["record"]), (503, "AuditError"))
            self.assertEqual(self.req("GET", "/health", token=None, base=f"http://127.0.0.1:{fresh.server_address[1]}")[0], 200, "health reports the tampered record's length; it does not judge it")
        finally:
            fresh.shutdown()

    def test_a_budget_stop_on_confirm_is_final(self):
        self.w.template["budget"]["tool_calls"] = 2   # the first read is two reads; the parked comment would be the third
        r = self.run_one(); sid, h = r["session"], r["parked"]["hash"]
        s, body = self.req("POST", f"/runs/{sid}/confirm", {"hash": h})
        self.assertEqual((s, body["reason"], "retry" in body), (409, "budget.tool_calls", False), body)
        j = self.w.harness.sessions.load_json(sid)
        self.assertEqual((j["ended"], j["pending"]), ("budget.tool_calls", None), "the run ended in the record and nothing is parked any more")
        s, got = self.req("GET", f"/runs/{sid}")
        self.assertEqual((s, got["parked"], got["blocked"], got["ended"]), (200, None, "budget.tool_calls", "budget.tool_calls"))
        self.assertEqual(self.req("POST", f"/runs/{sid}/confirm", {"hash": h})[0], 409, "and it cannot be confirmed again")
        self.assertEqual(self.w.targets["tickets"].comments, []); self.assertEqual(j["budget"]["tool_calls"]["used"], 3, "one refused attempt, not one per retry")

    def test_the_run_limit_is_per_person_not_per_token(self):
        w2 = build(Settings(runs_per_minute=1)); httpd = serve(w2, "127.0.0.1", 0, "https://agents.example/mcp"); threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            t1 = w2.idp.issue("u_dana", {"name": "u_dana", "roles": ["operator"]}, client_id="agent-sandbox", ttl_s=3600)
            t2 = w2.idp.issue("u_dana", {"name": "u_dana", "roles": ["operator"]}, client_id="agent-sandbox", ttl_s=3601)
            self.assertNotEqual(t1, t2)
            self.assertEqual([self.req("POST", "/runs", {"ticket_key": "INC-7", "service": "checkout"}, token=t, base=base)[0] for t in (t1, t1, t2, t2)], [200, 429, 429, 429])
            sam = w2.token("u_sam")
            self.assertEqual(self.req("POST", "/runs", {"ticket_key": "INC-7", "service": "checkout"}, token=sam, base=base)[0], 200, "another person has a bucket of their own")
            self.assertEqual(self.req("POST", "/runs", {"ticket_key": "INC-7", "service": "checkout"}, token="not.a.token", base=base)[0], 401)
        finally:
            httpd.shutdown()

    def test_a_posted_run_evicted_from_memory_is_rebuilt_from_the_record(self):
        first = self.run_one(); sid = first["session"]
        s, done = self.req("POST", f"/runs/{sid}/confirm", {"hash": first["parked"]["hash"]}); self.assertEqual((s, done["posted"], done["ended"]), (200, {"id": "1"}, "turn.complete"))
        self.run_one()   # max_runs=1: the posted run is evicted
        s, got = self.req("GET", f"/runs/{sid}")
        self.assertEqual(s, 200, "never 404 while the record has the session")
        self.assertEqual((got["session"], got["run_id"], got["parked"], got["blocked"], got["ended"]), (sid, first["run_id"], None, None, "turn.complete"))
        self.assertEqual((got["posted"]["tool"], got["posted"]["from"]), (first["parked"]["tool"], "record"), "the write that ran, as the chain recorded it")
        self.assertEqual(self.req("GET", f"/runs/{sid}", token=self.w.token("u_sam"))[0], 404, "still only for the person whose run it is")
        self.assertEqual(self.req("POST", f"/runs/{sid}/confirm", {"hash": first["parked"]["hash"]})[0], 409, "and nothing to confirm")


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.saved = dict(os.environ)
        os.environ["AGENT_DB"] = os.path.join(self.tmp.name, "record.db")

    def tearDown(self):
        os.environ.clear(); os.environ.update(self.saved); self.tmp.cleanup()

    def test_stop_and_resume_need_only_the_record(self):
        import agentrt.wiring as W
        os.environ.update({"AGENT_IDENTITY": "oidc", "AGENT_IDP_ISSUER": "https://idp.example", "AGENT_IDP_AUDIENCE": "agent", "AGENT_OPERATOR_GROUP_ID": "g_placeholder"})
        real = W.fetch_json
        W.fetch_json = lambda url: (_ for _ in ()).throw(OSError("unreachable"))   # the provider is down
        try:
            rc, out = cli(["stop", "board", "incidents", "--by", "u_ops"]); self.assertEqual((rc, out.startswith("board incidents: stopped")), (0, True), out)
            w = W.open_switches(Settings.from_env()); self.assertEqual(w.kills.state(w.consumer, "incidents", "run_x"), "board"); w.conn.close()
            rc, out = cli(["resume", "board", "incidents", "--by", "u_ops"]); self.assertEqual(rc, 0, out)
            rc, out = cli(["token", "u_dana"]); self.assertEqual((rc, out), (2, "token: sandbox only (the fake identity provider)"))
            rc, out = cli(["export-audit"]); self.assertEqual((rc, out), (2, "export-audit: the runtime could not be built: OSError"), "named, never a traceback")
            os.environ["AGENT_ENV"] = "staging"   # misconfigured: fakes in staging
            rc, out = cli(["serve"]); self.assertEqual(rc, 2); self.assertTrue(out.startswith("config: "), out)
            rc, out = cli(["stop", "board", "incidents", "--by", "u_ops"]); self.assertEqual(rc, 0, "the switch is thrown whatever else is wrong with the task")
        finally:
            W.fetch_json = real

    def test_verify_record_never_creates_the_record_and_refuses_what_is_not_a_file(self):
        rc, out = cli(["verify-record"])
        self.assertEqual((rc, out), (0, "record: none yet (a first start creates it)")); self.assertFalse(os.path.exists(os.environ["AGENT_DB"]), "the entrypoint runs this before serve; serve creates it")
        os.environ["AGENT_DB"] = self.tmp.name   # a directory
        rc, out = cli(["verify-record"]); self.assertEqual(rc, 2); self.assertEqual(out, f"verify-record: the record is not a file: AGENT_DB={self.tmp.name}")
        rc, out = cli(["backup", os.path.join(self.tmp.name, "copy.db")]); self.assertEqual(rc, 2); self.assertEqual(out, f"backup: the record is not a file: AGENT_DB={self.tmp.name}")
        os.environ["AGENT_DB"] = p = os.path.join(self.tmp.name, "plain.db")
        c = sqlite3.connect(p); c.execute("CREATE TABLE t(x)"); c.commit(); c.close()   # version 0, no chain: read-only leaves it at 0
        rc, out = cli(["verify-record"]); self.assertEqual((rc, out), (0, "record ok: 0 records (no chain yet)"))
        self.assertEqual(sqlite3.connect(p).execute("PRAGMA user_version").fetchone()[0], 0, "verifying opens read-only: no migration stamp")
        w = build(Settings(db_path=p)); w.audit.record(event="x"); w.conn.close()
        rc, out = cli(["verify-record"]); self.assertEqual(rc, 0); self.assertTrue(out.startswith("record ok: 1 records"), out)
        sqlite3.connect(p).execute("UPDATE audit SET body = '{}'").connection.commit()
        rc, out = cli(["verify-record"]); self.assertEqual((rc, out), (1, "record broken: AuditError"))

    def test_read_only_open_survives_odd_characters_in_the_path_and_backup_names_its_failure(self):
        for sub in ("a?b", "100%25", "x#y", "with space"):
            d = os.path.join(self.tmp.name, sub); os.makedirs(d); p = os.path.join(d, "record.db")
            c = sqlite3.connect(p); c.execute("PRAGMA user_version = 1"); c.execute("CREATE TABLE t(x)"); c.commit(); c.close()
            conn = open_record(p, readonly=True)
            self.assertEqual(conn.execute("SELECT name FROM sqlite_master").fetchall(), [("t",)], sub)
            with self.assertRaises(sqlite3.OperationalError): conn.execute("CREATE TABLE u(x)")
            conn.close()
            self.assertEqual(sorted(os.listdir(d)), ["record.db"], f"nothing else was created beside {sub}")
            os.environ["AGENT_DB"] = p
            rc, out = cli(["backup", os.path.join(d, "copy.db")]); self.assertEqual(rc, 0, out)
        self.assertEqual(sorted(os.listdir(self.tmp.name)), ["100%25", "a?b", "with space", "x#y"], "no stray file at an unescaped path")
        rc, out = cli(["backup", os.path.join(self.tmp.name, "no-such-dir", "copy.db")])
        self.assertEqual(rc, 2); self.assertTrue(out.startswith("backup failed: OperationalError"), out)
