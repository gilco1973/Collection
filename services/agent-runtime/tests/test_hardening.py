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
            def request(self, method, url, headers, body):
                if method == "GET": return 404, {}, b""   # no pointer yet
                seen.append(headers); return 200, {}, b""
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


class ThirdReview(unittest.TestCase):
    """What the third review found in the runtime: the CLI's consumer target, a confirmation lost to an outage,
    bodies that are not objects, handlers the template never named, half-sent requests, and an export pointer
    that moved backwards."""

    def setUp(self):
        self.w = build(Settings())
        self.httpd = serve(self.w, "127.0.0.1", 0, "https://agents.example/mcp", socket_timeout_s=0.5); threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()

    def req(self, method, path, body=None, raw=None):
        h = {"Content-Type": "application/json", "Authorization": f"Bearer {self.w.token('u_dana')}"}
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        try:
            r = urllib.request.urlopen(urllib.request.Request(self.base + path, data=data, headers=h, method=method), timeout=10)
            return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_stop_consumer_self_targets_what_the_harness_checks(self):
        import contextlib, io
        from actionloop.harness import Stop
        from agentrt.__main__ import main
        with tempfile.TemporaryDirectory() as d:
            saved = dict(os.environ); os.environ["AGENT_DB"] = os.path.join(d, "r.db")
            try:
                for who in ("u_alice", "u_bob"):
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(main(["stop", "consumer", "-", "--by", who]), 0)
                w = build(Settings(db_path=os.environ["AGENT_DB"]))
                self.assertEqual(w.kills.state(w.harness.consumer, "incidents", "run_x"), "consumer")
                with self.assertRaises(Stop) as cm:
                    w.harness.admit(w.token("u_dana"), "incidents", None, __import__("agent").budget_from(w.template))
                self.assertEqual(cm.exception.reason, "kill.consumer")
                w.conn.close()
            finally:
                os.environ.clear(); os.environ.update(saved)

    def test_a_confirmed_write_that_failed_upstream_is_parked_again_and_confirmable(self):
        s, r = self.req("POST", "/runs", {"ticket_key": "INC-7", "service": "checkout"}); sid, h = r["session"], r["parked"]["hash"]
        self.w.targets["tickets"].down = True
        s, body = self.req("POST", f"/runs/{sid}/confirm", {"hash": h})
        self.assertEqual((s, body["reason"], body["retry"]), (409, "handler.errors", True))
        self.w.targets["tickets"].down = False
        self.assertEqual(self.req("GET", f"/runs/{sid}")[1]["parked"]["hash"], h, "the same call is parked again, with the hash the person saw")
        self.assertEqual(self.w.harness.sessions.load_json(sid)["pending"]["hash"], h, "in the record, not only in memory")
        s, done = self.req("POST", f"/runs/{sid}/confirm", {"hash": h})
        self.assertEqual((s, done["posted"]), (200, {"id": "1"})); self.assertEqual(len(self.w.targets["tickets"].comments), 1)
        self.assertEqual(self.req("POST", f"/runs/{sid}/confirm", {"hash": h})[0], 409, "and once posted it is gone for good")

    def test_a_body_that_is_not_an_object_is_a_400_on_both_routes(self):
        before = self.w.audit.verify()
        for raw in (b"null", b"[]", b'"x"', b"1"):
            s, body = self.req("POST", "/runs", raw=raw)
            self.assertEqual((s, body["title"]), (400, "Bad request"), raw)
            s, body = self.req("POST", "/runs/ses_x/confirm", raw=raw)
            self.assertEqual((s, body["title"]), (400, "Bad request"), raw)
        self.assertEqual(self.w.audit.verify(), before, "nothing was admitted or recorded")

    def test_the_gateway_holds_exactly_the_template_tools(self):
        from actionloop import catalog as C
        listed = {e["name"] for e in self.w.harness.catalog.payload["tools"]}
        self.assertEqual(set(self.w.harness.gateway.tools_list()), listed)
        C.check(self.w.harness.catalog.payload, {n: True for n in self.w.harness.gateway.tools_list()})  # unfiltered: no extra handler, none missing

    def test_half_sent_and_idle_connections_hold_no_thread_and_count_nothing(self):
        import http.client, socket
        self.assertEqual(self.httpd.RequestHandlerClass.timeout, 0.5)
        idle = socket.create_connection(("127.0.0.1", self.httpd.server_address[1]))           # opened, nothing sent
        half = socket.create_connection(("127.0.0.1", self.httpd.server_address[1]))
        half.sendall(b"POST /runs HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer y\r\nContent-Type: application/json\r\nContent-Length: 10\r\n\r\n")
        time.sleep(0.1)
        with self.httpd.inflight_lock:
            self.assertEqual(self.httpd.inflight, 1, "the half-sent request arrived (its headers parsed); the idle connection never did")
        time.sleep(1.0)
        with self.httpd.inflight_lock:
            self.assertEqual(self.httpd.inflight, 0, "both were dropped at the socket timeout")
        half.settimeout(1.0); self.assertEqual(half.recv(100), b"", "no answer, the connection was closed")
        idle.close(); half.close()
        c = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=5)
        c.request("GET", "/health"); c.getresponse().read()
        with self.httpd.inflight_lock:
            self.assertEqual(self.httpd.inflight, 0, "a keep-alive connection between requests is not in flight")
        c.close()

    def test_the_export_pointer_only_moves_forward(self):
        import sqlite3
        from agentrt.export import ExportError
        from actionloop.audit import AuditChain
        objects = {}
        class Http:
            def request(self, method, url, headers, body):
                key = url.split("amazonaws.com/")[1]
                if method == "GET": return (200, {}, objects[key]) if key in objects else (404, {}, b"")
                objects[key] = body; return 200, {}, b""
        put = S3Put(Http(), "us-east-1", creds_loader=lambda: __import__("sigv4").Credentials("A", "S"))
        long_chain = AuditChain(sqlite3.connect(":memory:"))
        for i in range(10): long_chain.record(event="x", i=i)
        first = export_chain(long_chain, "agent", "s3://b/p/", put, now=1_800_000_000)
        self.assertEqual((first["records"], first["previous"]), (10, None))
        restored = AuditChain(sqlite3.connect(":memory:"))                              # the record restored from an old backup
        for i in range(3): restored.record(event="x", i=i)
        with self.assertRaises(ExportError) as cm:
            export_chain(restored, "agent", "s3://b/p/", put, now=1_800_000_100)
        self.assertIn("chain shorter than the last export", str(cm.exception))
        self.assertEqual(json.loads(objects["p/agent/latest.json"])["records"], 10, "the pointer still names the longer export")
        diverged = AuditChain(sqlite3.connect(":memory:"))                              # as long, but not the same chain
        for i in range(12): diverged.record(event="y", i=i)
        with self.assertRaises(ExportError): export_chain(diverged, "agent", "s3://b/p/", put, now=1_800_000_200)
        for i in range(10, 12): long_chain.record(event="x", i=i)
        third = export_chain(long_chain, "agent", "s3://b/p/", put, now=1_800_000_300)
        self.assertEqual((third["records"], third["previous"]), (12, first["head"]), "a longer chain carrying the last head moves the pointer, naming what it replaced")
        class NoGet:
            def put(self, bucket, key, body, content_type="application/json"): return f"s3://{bucket}/{key}"
        self.assertEqual(export_chain(restored, "agent", "s3://b/p/", NoGet(), now=0)["previous"], None, "a put without get reads as no pointer")
