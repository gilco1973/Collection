"""What a hostile caller, a rotated credential, a misconfigured task and a stop signal do to the runtime."""
import json, os, tempfile, threading, time, unittest, urllib.error, urllib.request
from agentrt import vendor  # noqa: F401
from agentrt.app import drain, serve
from agentrt.export import S3Put, export_chain
from agentrt.settings import Settings
from agentrt.wiring import build


class Api(unittest.TestCase):
    def setUp(self):
        self.w = build(Settings())
        self.httpd = serve(self.w, "127.0.0.1", 0, "https://agents.example/mcp", max_runs=1); threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()

    def req(self, method, path, body=None, token="x"):
        h = {"Content-Type": "application/json"}
        if token: h["Authorization"] = f"Bearer {self.w.token('u_dana') if token == 'x' else token}"
        try:
            r = urllib.request.urlopen(urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None, headers=h, method=method), timeout=10)
            return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_a_run_is_read_only_by_its_person(self):
        s, r = self.req("POST", "/runs", {"ticket_key": "INC-7", "service": "checkout"}); self.assertEqual(s, 200)
        self.assertEqual(self.req("GET", f"/runs/{r['session']}", token=None)[0], 401)
        self.assertEqual(self.req("GET", f"/runs/{r['session']}", token=self.w.token("u_sam"))[0], 404, "another person's run reads as not there")
        self.assertEqual(self.req("GET", f"/runs/{r['session']}")[1]["parked"]["hash"], r["parked"]["hash"])

    def test_a_parked_run_evicted_from_memory_is_still_confirmable_from_the_record(self):
        s, first = self.req("POST", "/runs", {"ticket_key": "INC-7", "service": "checkout"})
        self.req("POST", "/runs", {"ticket_key": "INC-7", "service": "checkout"})  # max_runs=1: the first is evicted
        s, got = self.req("GET", f"/runs/{first['session']}"); self.assertEqual((s, got["parked"]["hash"]), (200, first["parked"]["hash"]))
        s, done = self.req("POST", f"/runs/{first['session']}/confirm", {"hash": first["parked"]["hash"]})
        self.assertEqual((s, done["posted"]), (200, {"id": "1"}))

    def test_mcp_bodies_are_bounded_like_the_run_api(self):
        big = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"pad": "x" * (self.w.settings.max_body_bytes + 10)}}
        self.assertEqual(self.req("POST", "/mcp", big)[0], 413)

    def test_drain_waits_for_requests_in_flight(self):
        self.httpd.inflight = 1
        threading.Timer(0.2, lambda: setattr(self.httpd, "inflight", 0)).start()
        t0 = time.time(); self.assertTrue(drain(self.httpd, 5.0)); self.assertGreater(time.time() - t0, 0.1)
        self.httpd.inflight = 1; self.assertFalse(drain(self.httpd, 0.2)); self.httpd.inflight = 0


class Config(unittest.TestCase):
    def test_aws_region_is_the_unprefixed_variable(self):
        os.environ["AWS_REGION"] = "eu-west-1"
        try:
            self.assertEqual(Settings.from_env().bedrock_region, "eu-west-1")
        finally:
            del os.environ["AWS_REGION"]

    def test_the_task_definition_environment_passes_check_config_once_its_placeholders_are_real(self):
        td = json.load(open(os.path.join(os.path.dirname(__file__), "..", "deploy", "ecs-task-definition.json")))
        env = {e["name"]: e["value"] for e in td["containerDefinitions"][0]["environment"]}
        env["AGENT_DEPLOYS_PIPELINES"] = "checkout=42"; env["AGENT_DB"] = "/var/agent/agent.db"
        saved = dict(os.environ); os.environ.update(env)
        try:
            s = Settings.from_env(); self.assertEqual(s.validate(), [])
        finally:
            os.environ.clear(); os.environ.update(saved)
        self.assertIn({"sourceVolume": "scratch", "containerPath": "/tmp"}, td["containerDefinitions"][0]["mountPoints"], "scratch space beside the read-only root")

    def test_numbers_and_connector_settings_are_problems_not_tracebacks(self):
        os.environ["AGENT_LISTEN_PORT"] = "8O81"
        try:
            self.assertIn("AGENT_LISTEN_PORT must be an integer", Settings.from_env().validate())
        finally:
            del os.environ["AGENT_LISTEN_PORT"]
        p = Settings(targets=("tickets",), jira_url="https://j", jira_auth="oauth", deploys_pipelines={"checkout": "PIPELINE_ID"}).validate()
        self.assertTrue(any("JIRA_AUTH must be" in x for x in p)); self.assertTrue(any("pipeline ids" in x for x in p))
        self.assertTrue(any("JIRA_USER is required" in x for x in Settings(targets=("tickets",), jira_url="https://j", jira_auth="basic").validate()))


class Export(unittest.TestCase):
    def test_the_put_is_encrypted_as_the_policy_demands_and_written_beside_the_record(self):
        seen = []
        class Http:
            def request(self, method, url, headers, body): seen.append(headers); return 200, {}, b""
        policy = json.load(open(os.path.join(os.path.dirname(__file__), "..", "deploy", "iam-task-role-policy.json")))
        cond = next(s for s in policy["Statement"] if s["Sid"] == "AuditExport")["Condition"]["StringEquals"]
        w = build(Settings())
        with tempfile.TemporaryDirectory() as d:
            out = export_chain(w.audit, "a", "s3://b/p/", S3Put(Http(), "us-east-1", creds_loader=lambda: __import__("sigv4").Credentials("A", "S")), work_dir=d)
        self.assertTrue(out["object"].startswith("s3://b/p/a/"))
        for h in seen:
            self.assertEqual(h["x-amz-server-side-encryption"], cond["s3:x-amz-server-side-encryption"])


class Record(unittest.TestCase):
    def test_a_newer_record_is_refused_by_name_and_backup_never_creates_or_migrates(self):
        import sqlite3, subprocess, sys
        from agentrt.__main__ import main
        with tempfile.TemporaryDirectory() as d:
            newer = os.path.join(d, "newer.db"); c = sqlite3.connect(newer); c.execute("PRAGMA user_version = 99"); c.commit(); c.close()
            saved = dict(os.environ); os.environ["AGENT_DB"] = newer
            try:
                import io, contextlib
                for cmd in (["verify-record"], ["backup", os.path.join(d, "copy.db")], ["serve"]):
                    out = io.StringIO()
                    with contextlib.redirect_stdout(out):
                        rc = main(cmd)
                    self.assertEqual(rc, 2, cmd); self.assertTrue(out.getvalue().startswith("record: the record is at schema version 99"), out.getvalue())
                os.environ["AGENT_DB"] = os.path.join(d, "typo.db")
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    rc = main(["backup", os.path.join(d, "copy2.db")])
                self.assertEqual(rc, 2); self.assertIn("does not exist", out.getvalue()); self.assertFalse(os.path.exists(os.path.join(d, "typo.db")), "a backup never creates a record")
                # A fresh record is stamped with this build's version and backed up read-only.
                os.environ["AGENT_DB"] = os.path.join(d, "fresh.db")
                w = build(Settings(db_path=os.environ["AGENT_DB"])); w.conn.close()
                self.assertEqual(sqlite3.connect(os.environ["AGENT_DB"]).execute("PRAGMA user_version").fetchone()[0], 1)
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(main(["backup", os.path.join(d, "copy3.db")]), 0)
                self.assertTrue(os.path.exists(os.path.join(d, "copy3.db")))
            finally:
                os.environ.clear(); os.environ.update(saved)

    def test_stop_and_resume_are_commands_that_name_the_person(self):
        import contextlib, io
        from agentrt.__main__ import main
        with tempfile.TemporaryDirectory() as d:
            saved = dict(os.environ); os.environ["AGENT_DB"] = os.path.join(d, "r.db")
            try:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(main(["stop", "board", "incidents", "--by", "u_ops"]), 0)
                self.assertIn("board incidents: stopped", out.getvalue())
                w = build(Settings(db_path=os.environ["AGENT_DB"]))
                self.assertEqual(w.kills.state("agent:incident-first-read", "incidents", "run_x"), "board")
                self.assertTrue(any(r["event"] == "kill.actuation" and r["actor"] == "u_ops" for r in w.audit.query(event="kill.actuation")))
                w.conn.close()
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(main(["resume", "board", "incidents", "--by", "u_ops"]), 0)
                self.assertIn("board incidents: running", out.getvalue())
                self.assertEqual(main(["stop", "board"]), 2)
            finally:
                os.environ.clear(); os.environ.update(saved)
