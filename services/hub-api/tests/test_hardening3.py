"""The third round of hardening: the identity map and claims checked for shape, a subject that must exist, a stop that
waits only for requests being answered, one execution per Idempotency-Key, one turn at a time per conversation,
readiness through the verifier's throttle, a client that stops reading, strict framing, ids-only logs, bodies of the
wrong shape as 422, separation of duties on the shelf, and a view sequence that survives a restart."""
import http.client, json, logging, os, socket, tempfile, threading, time, unittest
from hubapi.app import MAX_TURNS, drain
from hubapi.auth import AuthError, IdentityMap, IdentityMapError, MockAuth, OidcAuth
from hubapi.settings import SERVICE, Settings
from hubapi.store import Store
from tests.support import DATA, Client, HttpServer, make_api
from tests.test_hardening import raw
from tests.test_oidc import AUD, ISSUER, JWKS_URL, fetch, mint

ATTEST = {k: True for k in ("testsGreen", "exampleRun", "walkthroughRead", "rulesRead")}


def _claims(**extra):
    now = int(time.time())
    return {"iss": ISSUER, "aud": AUD, "sub": "s-1", "exp": now + 600, "nbf": now - 10, "email": "a.b@bank.example", "name": "A B", **extra}


def _example_map() -> IdentityMap:
    return IdentityMap.load(os.path.join(SERVICE, "data", "identity-map.example.json"))


class Capture(logging.Handler):
    def __init__(self):
        super().__init__(); self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(self.format(record))


class IdentityMapShape(unittest.TestCase):
    """Item 1: a typo in the identity map is named at load and by check-config, never a 500 per call."""

    def test_a_malformed_map_is_a_typed_error_at_load(self):
        for doc, expect in (({"groups": {"G": {"roles": ["ops.lead"], "ladder": "L9"}}}, "ladder"), ({"groups": {"G": {"roles": "platform.lead"}}}, "roles"),
                            ({"groups": {"G": {"entitlements": "compliance-narration"}}}, "entitlements"), ({"groups": {"G": {"team": "platform"}}}, "team"),
                            ({"groups": {"G": {"team": {"name": "no id"}}}}, "team"), ({"default": {"roles": [1]}}, "default.roles"), ({"groups": ["G"]}, "groups"), ([], "object")):
            with self.assertRaises(IdentityMapError, msg=str(doc)) as cm:
                IdentityMap(doc)
            self.assertIn(expect, str(cm.exception))
        self.assertIsInstance(IdentityMapError("x"), ValueError)
        _example_map()   # the shipped example passes its own check

    def test_check_config_refuses_a_malformed_map(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"groups": {"G_LEADS": {"roles": ["ops.lead"], "ladder": "L9"}}}, f); bad = f.name
        try:
            problems = [p for p in Settings(identity_map=bad).validate() if "IDENTITY_MAP" in p]
            self.assertEqual(len(problems), 1); self.assertIn("not well-formed", problems[0]); self.assertIn("ladder", problems[0])
        finally:
            os.remove(bad)
        self.assertEqual([p for p in Settings().validate() if "IDENTITY_MAP" in p], [])

    def test_odd_claim_types_are_a_refusal_or_ignored_never_a_500(self):
        auth = OidcAuth(ISSUER, AUD, JWKS_URL, fetch, _example_map(), "GROUP_ID_AI_SECURITY")
        api = make_api(auth=auth)
        for claims in ({"name": 5}, {"email": ["a@b.example"]}, {"groups": ["GROUP_ID_PLATFORM", 7, None]}):
            s, body = Client(api, mint(_claims(**claims))).call("GET", "/me")
            self.assertEqual(s, 200, claims)
        p = auth.principal(mint(_claims(name=5, email=["x"])))
        self.assertEqual((p.name, p.email), ("s-1", ""), "a claim of another type is not that claim")
        self.assertEqual(auth.principal(mint(_claims(groups=["GROUP_ID_PLATFORM", 7]))).roles, ["platform.lead"])
        # A groups claim that is a string would be read as its characters ("G" in "GROUP_ID_AI_SECURITY"): refused instead.
        s, body = Client(api, mint(_claims(groups="GROUP_ID_PLATFORM"))).call("GET", "/me")
        self.assertEqual(s, 401); self.assertIn("groups", body["detail"])

    def test_whatever_the_map_raises_on_a_verified_token_is_401(self):
        auth = OidcAuth(ISSUER, AUD, JWKS_URL, fetch, _example_map(), "G")
        def boom(claims, group=""): raise KeyError("ladder")
        auth.map.principal = boom
        with self.assertRaises(AuthError) as cm:
            auth.principal(mint(_claims()))
        self.assertEqual(cm.exception.status, 401); self.assertIn("identity map or claims unreadable (KeyError)", cm.exception.detail)
        self.assertEqual(Client(make_api(auth=auth), mint(_claims())).call("GET", "/me")[0], 401)


class Subject(unittest.TestCase):
    """Item 2: a token without oid and sub never becomes the shared principal u_."""

    def test_a_token_without_a_subject_is_refused(self):
        auth = OidcAuth(ISSUER, AUD, JWKS_URL, fetch, _example_map(), "G")
        for claims in ({}, {"sub": ""}, {"sub": "  "}, {"sub": 12}, {"oid": ["x"]}):
            c = _claims(**claims); c.pop("sub", None); c.update(claims)
            with self.assertRaises(AuthError, msg=str(claims)) as cm:
                auth.principal(mint(c))
            self.assertEqual((cm.exception.status, cm.exception.detail), (401, "token has no subject"))
        self.assertEqual(auth.principal(mint(_claims(oid=7))).id, "u_s-1", "an oid of the wrong type falls back to the subject")
        api = make_api(auth=auth); c = _claims(); del c["sub"]
        s, body = Client(api, mint(c)).call("GET", "/me")
        self.assertEqual((s, body["detail"]), (401, "token has no subject"))


class Drain(unittest.TestCase):
    """Item 3: an idle keep-alive connection is not a request in flight; a stop waits only for answers being written."""

    def test_an_idle_keep_alive_connection_does_not_hold_the_drain(self):
        srv = HttpServer(make_api()); host, port = srv.base.replace("http://", "").split(":")
        c = http.client.HTTPConnection(host, int(port), timeout=10)
        try:
            c.request("GET", "/api/health"); r = c.getresponse(); r.read()
            for _ in range(50):  # the counter drops right after the last byte is written; give the handler thread its turn
                if srv.httpd.inflight == 0: break
                time.sleep(0.02)
            self.assertEqual(srv.httpd.inflight, 0, "nothing is being answered once the response is written")
            srv.httpd.shutdown()
            t0 = time.time()
            self.assertTrue(drain(srv.httpd, timeout_s=5.0)); self.assertLess(time.time() - t0, 1.0)
            # A request that arrives on the kept-alive connection after the stop began is refused and the connection closes.
            c.request("GET", "/api/health"); r = c.getresponse(); body = r.read()
            self.assertEqual((r.status, r.getheader("Connection")), (503, "close")); self.assertEqual(json.loads(body)["code"], "not.ready")
        finally:
            c.close(); srv.httpd.server_close()


class IdempotencyRace(unittest.TestCase):
    """Item 4: one execution per key; the second caller while the first runs is told so; a failure frees the key."""

    def setUp(self):
        self.api = make_api(); self.gk = Client(self.api, "mock.gk"); self.body = {"kind": "access", "consumerId": "compliance-narration"}

    def test_a_second_call_while_the_first_runs_is_409_then_replays(self):
        gate, entered = threading.Event(), threading.Event(); orig = self.api.store.put
        def slow_put(kind, id, doc, owner=None):
            if kind == "request": entered.set(); gate.wait(5)
            return orig(kind, id, doc, owner)
        self.api.store.put = slow_put; res = []
        t = threading.Thread(target=lambda: res.append(self.gk.call("POST", "/me/requests", self.body, {"Idempotency-Key": "once"}))); t.start()
        self.assertTrue(entered.wait(5))
        s, body = self.gk.call("POST", "/me/requests", self.body, {"Idempotency-Key": "once"})
        self.assertEqual((s, body["code"]), (409, "idempotency.in_progress"))
        gate.set(); t.join(5); self.api.store.put = orig
        self.assertEqual(res[0][0], 201)
        s, again = self.gk.call("POST", "/me/requests", self.body, {"Idempotency-Key": "once"})
        self.assertEqual((s, again["id"]), (201, res[0][1]["id"]), "once finished, the key replays the first answer")
        self.assertEqual(len(self.api.store.list("request", "u_gk")), 1)
        # Another person, or another route, with the same key: the per-person, per-route rule still holds.
        self.assertEqual(Client(self.api, "mock.investigator").call("POST", "/me/requests", self.body, {"Idempotency-Key": "once"})[0], 201)
        self.assertEqual(self.gk.call("POST", "/briefs", {}, {"Idempotency-Key": "once"})[1]["code"], "idempotency.reused")

    def test_two_at_once_execute_once(self):
        barrier = threading.Barrier(2); orig = self.api.store.replay
        def slow_replay(key, principal):
            r = orig(key, principal)
            try: barrier.wait(0.5)
            except threading.BrokenBarrierError: pass
            return r
        self.api.store.replay = slow_replay; res = []
        ts = [threading.Thread(target=lambda: res.append(self.gk.call("POST", "/me/requests", self.body, {"Idempotency-Key": "k"}))) for _ in range(2)]
        [t.start() for t in ts]; [t.join(5) for t in ts]; self.api.store.replay = orig
        self.assertEqual(len(self.api.store.list("request", "u_gk")), 1, "the lookup and the reservation are one section")
        ids = {b.get("id") for s, b in res if s == 201}; self.assertEqual(len(ids), 1)
        self.assertTrue(all(s in (201, 409) for s, _ in res), res)

    def test_a_problem_a_defect_and_a_stream_free_the_key(self):
        state = {"n": 0}
        def flaky(c):
            state["n"] += 1
            if state["n"] == 1: raise ValueError("defect")
            return 201, {"n": state["n"]}
        self.api.route("POST", "/flaky", flaky)
        logging.getLogger("hubapi").disabled = True
        try:
            self.assertEqual(self.gk.call("POST", "/flaky", None, {"Idempotency-Key": "f"})[0], 500)
        finally:
            logging.getLogger("hubapi").disabled = False
        self.assertIsNone(self.api.store.replay("f", "u_gk"), "a 500 leaves no placeholder behind")
        self.assertEqual(self.gk.call("POST", "/flaky", None, {"Idempotency-Key": "f"}), (201, {"n": 2}))
        self.assertEqual(self.gk.call("POST", "/flaky", None, {"Idempotency-Key": "f"}), (201, {"n": 2}), "and the answer replays")
        s, body = self.gk.call("POST", "/me/requests", {"kind": "nope"}, {"Idempotency-Key": "p"})
        self.assertEqual(s, 422); self.assertIsNone(self.api.store.replay("p", "u_gk"))
        _, c = self.gk.call("POST", "/conversations", {"assistantId": "employee-assistant"})
        self.assertEqual(self.gk.call("POST", f"/conversations/{c['id']}/turns", {"text": "hi"}, {"Idempotency-Key": "s"})[0], 200)
        self.assertIsNone(self.api.store.replay("s", "u_gk"), "a stream is never replayed")


class OneTurnAtATime(unittest.TestCase):
    """Item 5: two turns at once on one conversation are one turn and a 409, never a lost update; the ceiling holds."""

    def test_a_second_turn_while_one_streams_is_409_and_nothing_is_lost(self):
        gate, started = threading.Event(), threading.Event()
        class Slow:
            name = "slow"
            def stream(self, conversation, text, principal):
                started.set(); gate.wait(5)
                yield {"kind": "text", "provenance": "model", "text": "done"}
        api = make_api(assistant=Slow()); gk = Client(api, "mock.gk")
        _, c = gk.call("POST", "/conversations", {"assistantId": "employee-assistant"})
        res = []
        t = threading.Thread(target=lambda: res.append(gk.call("POST", f"/conversations/{c['id']}/turns", {"text": "first"}))); t.start()
        self.assertTrue(started.wait(5))
        s, body = gk.call("POST", f"/conversations/{c['id']}/turns", {"text": "second"})
        self.assertEqual((s, body["code"]), (409, "conversation.busy"))
        gate.set(); t.join(5)
        self.assertEqual(res[0][0], 200)
        self.assertEqual(gk.call("POST", f"/conversations/{c['id']}/turns", {"text": "third"})[0], 200, "free again once the first is written")
        x = api.store.get("conversation", c["id"])
        self.assertEqual([v["text"] for t in x["turns"] if t["role"] == "user" for v in t["views"]], ["first", "third"]); self.assertEqual(len(x["turns"]), 4)
        self.assertEqual([t["id"] for t in x["turns"]], ["t1", "t2", "t3", "t4"])

    def test_a_turn_that_fails_to_start_frees_the_conversation(self):
        class Broken:
            name = "broken"
            def stream(self, conversation, text, principal):
                raise RuntimeError("no adapter"); yield
        api = make_api(assistant=Broken()); gk = Client(api, "mock.gk")
        _, c = gk.call("POST", "/conversations", {"assistantId": "employee-assistant"})
        with self.assertRaises(RuntimeError):
            res = api.handle("POST", f"/conversations/{c['id']}/turns", {"Authorization": "Bearer mock.gk"}, b'{"text": "x"}')
            try: list(res.events)
            finally: res.done(True)
        self.assertNotIn(c["id"], api._busy)

    def test_the_ceiling_is_a_ceiling_under_concurrency(self):
        api = make_api(); gk = Client(api, "mock.gk")
        _, c = gk.call("POST", "/conversations", {"assistantId": "employee-assistant"})
        x = api.store.get("conversation", c["id"]); x["turns"] = [{"id": f"t{i}", "role": "user", "at": "", "views": []} for i in range(MAX_TURNS - 1)]
        api.store.put("conversation", x["id"], x, x["owner"]); res = []
        ts = [threading.Thread(target=lambda: res.append(gk.call("POST", f"/conversations/{c['id']}/turns", {"text": "one more"})[0])) for _ in range(3)]
        [t.start() for t in ts]; [t.join(5) for t in ts]
        self.assertEqual(res, [409, 409, 409]); self.assertEqual(len(api.store.get("conversation", c["id"])["turns"]), MAX_TURNS - 1)
        x["turns"] = x["turns"][:MAX_TURNS - 2]; api.store.put("conversation", x["id"], x, x["owner"])
        self.assertEqual(gk.call("POST", f"/conversations/{c['id']}/turns", {"text": "fits"})[0], 200)
        self.assertEqual(len(api.store.get("conversation", c["id"])["turns"]), MAX_TURNS)


class ReadyThrottle(unittest.TestCase):
    """Item 7: anonymous /ready refreshes the keys through the verifier's throttle: never a fetch per call."""

    def test_twenty_ready_calls_are_at_most_one_fetch(self):
        calls, state = [], {"fail": False}
        def counting(url):
            calls.append(time.time()); time.sleep(0.02)
            if state["fail"]: raise OSError("idp down")
            return fetch(url)
        auth = OidcAuth(ISSUER, AUD, JWKS_URL, counting, _example_map(), "G")
        api = make_api(auth=auth); anon = Client(api, None)
        self.assertEqual(anon.call("GET", "/ready")[0], 200); self.assertEqual(len(calls), 1)
        state["fail"] = True; auth.jwks._at -= 3601; auth.jwks._tried -= 61   # past the refresh time, within the maximum age
        res = []
        ts = [threading.Thread(target=lambda: res.append(anon.call("GET", "/ready")[0])) for _ in range(20)]
        [t.start() for t in ts]; [t.join(5) for t in ts]
        self.assertEqual(len(calls), 2, "one refresh for twenty checks"); self.assertEqual(res, [200] * 20, "stale keys within their maximum age keep the task ready")
        self.assertEqual(anon.call("GET", "/ready")[0], 200); self.assertEqual(len(calls), 2)


class SlowClient(unittest.TestCase):
    """Item 9: a client that stops reading the stream is an abort: the record gets its stop view, the thread is released
    after one timeout, nothing is logged as an error."""

    def test_a_write_that_times_out_aborts_the_stream(self):
        class Big:
            name = "big"
            def stream(self, conversation, text, principal):
                for i in range(400):
                    yield {"kind": "text", "provenance": "model", "text": "x" * 65536}
        api = make_api(assistant=Big()); srv = HttpServer(api); handler = srv.httpd.RequestHandlerClass; handler.timeout = 1
        cap = Capture(); cap.setFormatter(logging.Formatter("%(levelname)s %(message)s")); log = logging.getLogger("hubapi"); log.addHandler(cap); level = log.level; log.setLevel(logging.INFO)
        try:
            conv = json.loads(srv.request("POST", "/api/conversations", {"assistantId": "employee-assistant"}).read())
            host, port = srv.base.replace("http://", "").split(":")
            s = socket.create_connection((host, int(port))); s.settimeout(30); body = b'{"text":"hello"}'
            s.sendall(f"POST /api/conversations/{conv['id']}/turns HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer mock.gk\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)
            self.assertTrue(s.recv(64).startswith(b"HTTP/1.1 200")); t0 = time.time()
            while len(api.store.get("conversation", conv["id"])["turns"]) < 2 and time.time() - t0 < 15:
                time.sleep(0.1)
            elapsed = time.time() - t0
            x = api.store.get("conversation", conv["id"]); kinds = [v["kind"] for v in x["turns"][1]["views"]]
            self.assertEqual(kinds[-1], "stop", "the aborted turn carries its stop view"); self.assertLess(elapsed, 6, "one timeout, not two")
            self.assertFalse([l for l in cap.lines if l.startswith("ERROR")], cap.lines)
            self.assertTrue(any("stream aborted" in l for l in cap.lines), cap.lines)
            s.close()
        finally:
            handler.timeout = 30; log.removeHandler(cap); log.setLevel(level); srv.close()


class ContentLength(unittest.TestCase):
    """Item 10: Content-Length is ASCII digits, once."""

    def test_only_one_plain_decimal_length_is_accepted(self):
        srv = HttpServer(make_api())
        try:
            body = b'{"kind":"access","consumerId":"compliance-narration"}'
            head = b"POST /api/me/requests HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer mock.gk\r\nContent-Type: application/json\r\nContent-Length: "
            for cl in (b"5_3", b"+53", "٥٣".encode(), b"53\r\nContent-Length: 0", b"0x35", b"53 53", b"9" * 19):
                out = raw(srv, head + cl + b"\r\n\r\n" + body)
                self.assertIn(b"HTTP/1.1 400", out, cl); self.assertIn(b"Connection: close", out, cl); self.assertEqual(out.count(b"HTTP/1.1 "), 1, cl)
            self.assertIn(b"HTTP/1.1 201", raw(srv, head + b" 53 \r\n\r\n" + body), "surrounding whitespace is the header's, not the number's")
            # A second ask for the same access is 409 (a duplicate pending request); a different listing shows the length was read.
            body2 = b'{"kind":"access","consumerId":"sanctions-screening"}'
            n = str(len(body2)).encode()
            self.assertIn(b"HTTP/1.1 201", raw(srv, head + n + b"\r\nContent-Length: " + n + b"\r\n\r\n" + body2), "the same value twice is one value")
        finally:
            srv.close()


class StreamLog(unittest.TestCase):
    """Item 11: the stream's log line carries the path, never the query string."""

    def test_the_query_string_never_reaches_the_log(self):
        cap = Capture(); cap.setFormatter(logging.Formatter("%(message)s")); log = logging.getLogger("hubapi"); log.addHandler(cap); level = log.level; log.setLevel(logging.INFO)
        srv = HttpServer(make_api())
        try:
            conv = json.loads(srv.request("POST", "/api/conversations", {"assistantId": "employee-assistant"}).read())
            srv.request("POST", f"/api/conversations/{conv['id']}/turns?token=SECRETVALUE", {"text": "hello"}).read()
            lines = [l for l in cap.lines if "stream" in l]
            self.assertEqual(len(lines), 1); self.assertNotIn("SECRETVALUE", lines[0]); self.assertNotIn("?", lines[0]); self.assertIn(f"/api/conversations/{conv['id']}/turns 200 stream", lines[0])
        finally:
            log.removeHandler(cap); log.setLevel(level); srv.close()


class BodyShapes(unittest.TestCase):
    """Item 12: a body of the wrong shape is a 200 on a best-effort estimate or a 422, never a 500."""

    def test_estimate_road_and_feedback_take_wrong_shapes(self):
        api = make_api(); gk = Client(api, "mock.gk")
        _, b = gk.call("POST", "/briefs"); _, c = gk.call("POST", "/conversations", {"assistantId": "employee-assistant"})
        for body in ({"dataAndTools": [1]}, {"dataAndTools": {"tools": 5, "dataClasses": "confidential"}}, {"model": {"need": {}}}, {"model": "frontier"}, {"dataAndTools": {"tools": {"a": 1}}}):
            s, out = gk.call("POST", f"/briefs/{b['id']}/estimate", body)
            self.assertEqual(s, 200, body); self.assertEqual(out["reviewHours"], 3, body)
        self.assertEqual(gk.call("POST", f"/briefs/{b['id']}/estimate", {"dataAndTools": {"tools": [1, 2], "dataClasses": ["confidential"]}, "model": {"need": "utility"}})[1]["modelSpendMonthly"], 56)
        for body in ({"useCase": [1]}, {"useCase": {"channel": ["batch"]}}, {"dataAndTools": {"tierCeiling": 3}}, {"dataAndTools": 7}):
            s, out = gk.call("POST", f"/briefs/{b['id']}/road", body)
            self.assertEqual(s, 200, body); self.assertEqual(out["road"], "R2", body)
        self.assertEqual(gk.call("POST", f"/briefs/{b['id']}/road", {"useCase": {"channel": "batch"}})[1]["road"], "R4")
        for seq in (2**63, -1, 2**70, 1.5, True, "1"):
            s, out = gk.call("POST", f"/conversations/{c['id']}/feedback", {"seq": seq})
            self.assertEqual((s, out["code"]), (422, "validation"), seq)


class Duties(unittest.TestCase):
    """Item 14: two sign-offs on one component version are two people."""

    def setUp(self):
        personas = json.load(open(os.path.join(DATA, "examples.json")))["principals"]
        personas["gk"]["roles"].append("ai.security")
        self.api = make_api(auth=MockAuth(personas)); self.gk = Client(self.api, "mock.gk")
        self.name = self.gk.call("GET", "/shelf")[1][0]["name"]; self.r = self.api.catalog.shelf_record(self.name)

    def test_the_owner_may_not_sign_for_ai_security_on_their_own_component(self):
        self.assertEqual(self.gk.call("GET", f"/shelf/{self.name}")[1]["youMaySign"], ["owner"])
        self.assertEqual(self.gk.call("POST", f"/shelf/{self.name}/signoffs", {"role": "owner", "attest": ATTEST, "usedIn": "p"})[0], 201)
        s, out = self.gk.call("POST", f"/shelf/{self.name}/signoffs", {"role": "ai_security", "attest": ATTEST})
        self.assertEqual((s, out["code"]), (403, "shelf.role"))
        self.assertEqual(list(self.gk.call("GET", f"/shelf/{self.name}")[1]["recorded"]), ["owner"])
        p = self.api.auth.principal("mock.gk")
        self.assertTrue(self.api.catalog.may_sign({**self.r, "owner": "someone.else"}, p, "ai_security"), "on someone else's component the role applies")

    def test_the_other_role_already_recorded_by_the_same_person_is_409(self):
        me = self.gk.call("GET", "/me")[1]
        rec = {"id": "so_test", "component": self.name, "role": "ai_security", "by": me["name"], "email": me["email"].upper(), "date": "2026-01-01", "version": self.r["version"], "attest": ATTEST, "recordedAt": "2026-01-01T00:00:00Z"}
        self.api.store.put("signoff", rec["id"], rec, "u_other")
        s, out = self.gk.call("POST", f"/shelf/{self.name}/signoffs", {"role": "owner", "attest": ATTEST, "usedIn": "p"})
        self.assertEqual((s, out["code"]), (409, "shelf.duties"))
        rec["version"] = "0.0.1"; self.api.store.put("signoff", rec["id"], rec, "u_other")
        self.assertEqual(self.gk.call("POST", f"/shelf/{self.name}/signoffs", {"role": "owner", "attest": ATTEST, "usedIn": "p"})[0], 201, "a row at another version is another sign-off")


class ViewSequence(unittest.TestCase):
    """Item 15: a view's seq is its position in the conversation, the same after a restart; feedback names a stored view."""

    def test_seq_continues_across_a_restart_and_feedback_must_name_a_view(self):
        store = Store(":memory:")
        api1 = make_api(); api1.store = store; gk = Client(api1, "mock.gk")
        _, c = gk.call("POST", "/conversations", {"assistantId": "employee-assistant"})
        _, ev1 = gk.call("POST", f"/conversations/{c['id']}/turns", {"text": "one"})
        api2 = make_api(); api2.store = store; gk2 = Client(api2, "mock.gk")   # a deploy: a new process, the same record
        _, ev2 = gk2.call("POST", f"/conversations/{c['id']}/turns", {"text": "two"})
        s1, s2 = [e["seq"] for e in ev1], [e["seq"] for e in ev2]
        self.assertEqual(s1[0], 2, "seq 1 is the person's own message"); self.assertEqual(s2[0], s1[-1] + 2)
        self.assertFalse(set(s1) & set(s2)); self.assertEqual(sorted(s1 + s2), s1 + s2)
        self.assertEqual(ev1[-1]["view"]["seq"], s1[-1]); self.assertEqual(api2.view_count(store.get("conversation", c["id"])), s2[-1])
        _, d = gk2.call("POST", "/conversations", {"assistantId": "employee-assistant"}); _, ev3 = gk2.call("POST", f"/conversations/{d['id']}/turns", {"text": "one"})
        self.assertEqual([e["seq"] for e in ev3], s1, "the sequence is per conversation")
        self.assertEqual(gk2.call("POST", f"/conversations/{c['id']}/feedback", {"seq": ev2[-1]["view"]["seq"], "answered": True})[0], 204)
        for seq in (0, s2[-1] + 1, 10_000):
            s, out = gk2.call("POST", f"/conversations/{c['id']}/feedback", {"seq": seq})
            self.assertEqual((s, out["errors"]), (422, {"seq": ["unknown view"]}), seq)
        self.assertEqual(gk2.call("POST", f"/conversations/{d['id']}/feedback", {"seq": s2[-1]})[0], 422, "a seq of another conversation is not a view of this one")
