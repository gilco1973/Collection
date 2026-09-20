"""The contract, route by route, against the in-process application, and once end to end over HTTP."""
import json, os, tempfile, unittest
from hubapi.app import Problem
from tests.support import Client, HttpServer, make_api

ATTEST = {"testsGreen": True, "exampleRun": True, "walkthroughRead": True, "rulesRead": True}


class Contract(unittest.TestCase):
    def setUp(self):
        self.api = make_api()
        self.gk, self.emp, self.sec, self.anon = Client(self.api, "mock.gk"), Client(self.api, "mock.employee"), Client(self.api, "mock.security"), Client(self.api, None)

    def test_health_is_anonymous_and_everything_else_is_not(self):
        self.assertEqual(self.anon.call("GET", "/health")[0], 200)
        status, body = self.anon.call("GET", "/me")
        self.assertEqual(status, 401); self.assertEqual(body["code"], "unauthenticated")
        self.assertEqual(self.anon.call("GET", "/shelf")[0], 401)
        self.assertEqual(Client(self.api, "mock.nobody").call("GET", "/me")[0], 401)

    def test_me_and_preferences(self):
        s, me = self.gk.call("GET", "/me")
        self.assertEqual((s, me["id"]), (200, "u_gk")); self.assertIn("ops.lead", me["roles"])
        prefs = {**me["preferences"], "density": "dense"}
        self.assertEqual(self.gk.call("PUT", "/me/preferences", prefs)[1]["preferences"]["density"], "dense")
        self.assertEqual(self.gk.call("GET", "/me")[1]["preferences"]["density"], "dense")
        self.assertEqual(self.emp.call("GET", "/me")[1]["preferences"]["density"], "comfortable")

    def test_catalog_resolves_access_per_person_and_lists_the_collection(self):
        cat = self.gk.call("GET", "/catalog")[1]
        self.assertEqual(next(c for c in cat["available"] if c["id"] == "investigation-triage")["access"], "open")
        self.assertEqual(next(c for c in self.emp.call("GET", "/catalog")[1]["available"] if c["id"] == "investigation-triage")["access"], "request")
        self.assertTrue(any(l.get("collection") for l in cat["listings"]))
        self.assertEqual(cat["counts"]["agents"], len([l for l in cat["listings"] if l["kind"] == "agent"]))
        hits = self.gk.call("GET", "/catalog/search?q=audit")[1]
        self.assertTrue(any(h["id"] == "audit-chain" for h in hits))
        self.assertEqual(self.emp.call("GET", "/consumers/investigation-triage")[1]["access"], "request")
        self.assertEqual(self.gk.call("GET", "/consumers/audit-chain")[1]["crumbs"][1], "Tools")
        self.assertEqual(self.gk.call("GET", "/consumers/nope")[0], 404)

    def test_requests_ladder_ceiling_and_workspace(self):
        s, r = self.gk.call("POST", "/me/requests", {"kind": "access", "consumerId": "compliance-narration"}, {"Idempotency-Key": "k1"})
        self.assertEqual(s, 201); self.assertEqual(r["status"], "pending")
        again = self.gk.call("POST", "/me/requests", {"kind": "access", "consumerId": "compliance-narration"}, {"Idempotency-Key": "k1"})
        self.assertEqual(again[1]["id"], r["id"])  # replayed
        self.assertEqual(self.emp.call("POST", "/me/requests", {"kind": "ladder", "consumerId": "investigation-triage", "ladder": "L2"})[0], 403)
        ws = self.gk.call("GET", "/me/workspace")[1]
        self.assertEqual(ws["header"]["role"], "ops.lead"); self.assertEqual([x["id"] for x in ws["requests"]], [r["id"]])
        self.assertTrue(ws["teamConsumers"]); self.assertEqual(self.emp.call("GET", "/me/workspace")[1]["teamConsumers"], [])
        self.assertEqual(self.emp.call("GET", "/me/requests")[1], [])

    def test_briefs_etags_validation_and_the_lead_rule(self):
        s, b = self.emp.call("POST", "/briefs")
        self.assertEqual(s, 201); self.assertEqual(b["etag"], 'W/"1"')
        self.assertEqual(self.gk.call("GET", f"/briefs/{b['id']}")[0], 404)  # another person's draft
        self.assertEqual(Client(self.api, "mock.platform").call("GET", f"/briefs/{b['id']}")[0], 200)
        s, saved = self.emp.call("PATCH", f"/briefs/{b['id']}", {"currentStep": "model"}, {"If-Match": b["etag"]})
        self.assertEqual((s, saved["currentStep"], saved["etag"]), (200, "model", 'W/"2"'))
        self.assertEqual(self.emp.call("PATCH", f"/briefs/{b['id']}", {"currentStep": "outcome"}, {"If-Match": b["etag"]})[0], 409)
        s, p = self.emp.call("POST", f"/briefs/{b['id']}/file", None, {"If-Match": saved["etag"]})
        self.assertEqual(s, 422); self.assertIn("useCase.name", p["errors"])
        content = {"useCase": {"name": "Returns triage", "problem": "Returns are matched by hand every morning for two hours.", "channel": "operator", "teamId": "team-x"},
                   "people": {"businessOwner": "A", "productOwner": "B", "domainExpert": "C", "labellingHoursPerWeek": 2},
                   "dataAndTools": {"systems": [{"id": "cos", "name": "COS"}], "tools": [{"name": "cos.get", "tier": "R", "classes": ["internal"]}], "dataClasses": ["internal"], "tierCeiling": "R"},
                   "model": {"need": "workhorse", "classificationCeiling": "internal", "substitute": False},
                   "outcome": {"metric": "hours", "unit": "h/day", "baseline": 2, "target": 0.5, "measuredOn": "2026-09-01"}, "review": {"acknowledged": True}}
        s, saved = self.emp.call("PATCH", f"/briefs/{b['id']}", {"content": content}, {"If-Match": saved["etag"]})
        s, filed = self.emp.call("POST", f"/briefs/{b['id']}/file", None, {"If-Match": saved["etag"]})
        self.assertEqual((s, filed["status"], filed["road"]), (200, "filed", "R2"))
        self.assertEqual(self.emp.call("PATCH", f"/briefs/{b['id']}", {"currentStep": "model"})[0], 409)
        # a write profile needs a lead
        s, b2 = self.emp.call("POST", "/briefs")
        c2 = {**content, "dataAndTools": {**content["dataAndTools"], "tools": [{"name": "cos.note", "tier": "W1", "classes": ["internal"]}], "tierCeiling": "W1"}}
        s, saved = self.emp.call("PATCH", f"/briefs/{b2['id']}", {"content": c2})
        self.assertEqual(self.emp.call("POST", f"/briefs/{b2['id']}/file")[1]["code"], "brief.lead_required")
        self.assertEqual(self.gk.call("POST", f"/briefs/{b2['id']}/estimate", c2)[1]["reviewHours"], 3)
        self.assertEqual(self.gk.call("POST", f"/briefs/{b2['id']}/road", c2)[1]["selfService"], False)
        self.assertEqual(self.gk.call("POST", f"/briefs/{b2['id']}/road", {**c2, "useCase": {**c2["useCase"], "channel": "batch"}})[1]["road"], "R4")

    def test_conversations_stream_views_and_are_recorded(self):
        self.assertEqual(self.emp.call("POST", "/conversations", {"assistantId": "investigation-triage"})[0], 403)
        s, c = self.gk.call("POST", "/conversations", {"assistantId": "employee-assistant"})
        self.assertEqual(s, 201)
        s, events = self.gk.call("POST", f"/conversations/{c['id']}/turns", {"text": "cut-off for wires?"})
        self.assertEqual([e["view"]["kind"] for e in events], ["tool_call", "text", "text", "citation", "budget", "feedback"])
        self.assertTrue(all(events[i]["seq"] < events[i + 1]["seq"] for i in range(len(events) - 1)))
        conv = self.gk.call("GET", f"/conversations/{c['id']}")[1]
        self.assertEqual(len(conv["turns"]), 2); self.assertEqual(conv["title"], "cut-off for wires?")
        self.assertEqual(self.emp.call("GET", f"/conversations/{c['id']}")[0], 404)
        self.assertEqual(self.gk.call("POST", f"/conversations/{c['id']}/feedback", {"seq": events[-1]["seq"], "answered": True})[0], 204)
        self.assertEqual(self.gk.call("POST", f"/conversations/{c['id']}/handoff")[1]["route"], "human")
        self.assertEqual([x["id"] for x in self.gk.call("GET", "/conversations")[1]], [c["id"]])

    def test_shelf_sign_offs_owner_by_name_security_by_role(self):
        shelf = self.gk.call("GET", "/shelf")[1]
        self.assertTrue(shelf and all(e["youMaySign"] == ["owner"] for e in shelf))
        self.assertTrue(all(e["youMaySign"] == ["ai_security"] for e in self.sec.call("GET", "/shelf")[1]))
        name = shelf[0]["name"]
        self.assertEqual(self.emp.call("POST", f"/shelf/{name}/signoffs", {"role": "owner", "attest": ATTEST, "usedIn": "p"})[0], 403)
        self.assertEqual(self.gk.call("POST", f"/shelf/{name}/signoffs", {"role": "owner", "attest": {**ATTEST, "rulesRead": False}, "usedIn": "p"})[0], 422)
        self.assertEqual(self.gk.call("POST", f"/shelf/{name}/signoffs", {"role": "owner", "attest": ATTEST})[1]["errors"], {"usedIn": ["required"]})
        s, rec = self.gk.call("POST", f"/shelf/{name}/signoffs", {"role": "owner", "attest": ATTEST, "usedIn": "payments-ops"})
        self.assertEqual((s, rec["role"], rec["version"]), (201, "owner", shelf[0]["version"]))
        self.assertEqual(self.gk.call("POST", f"/shelf/{name}/signoffs", {"role": "owner", "attest": ATTEST, "usedIn": "x"})[0], 409)
        s, rec2 = self.sec.call("POST", f"/shelf/{name}/signoffs", {"role": "ai_security", "attest": ATTEST})
        self.assertEqual(s, 201)
        e = self.gk.call("GET", f"/shelf/{name}")[1]
        self.assertEqual(sorted(e["recorded"]), ["ai_security", "owner"]); self.assertIsNone(e["signoff"]["owner"])
        exp = self.gk.call("GET", "/shelf/signoffs/export")[1]
        self.assertEqual({x["role"] for x in exp["signoffs"]}, {"owner", "ai_security"}); self.assertIn("--apply-signoffs", exp["apply"])
        self.assertEqual(self.gk.call("GET", "/shelf/nope")[0], 404)


class OverHttp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "assets")); open(os.path.join(self.tmp, "index.html"), "w").write("<!doctype html><title>hub</title>"); open(os.path.join(self.tmp, "assets", "a.js"), "w").write("1")
        self.srv = HttpServer(make_api(), static_dir=self.tmp)

    def tearDown(self):
        self.srv.close()

    def test_json_problems_sse_and_the_static_spa(self):
        r = self.srv.request("GET", "/api/health", token=None); self.assertEqual(r.status, 200); self.assertEqual(json.loads(r.read())["status"], "ok")
        r = self.srv.request("GET", "/api/me", token=None); self.assertEqual(r.code, 401); self.assertEqual(r.headers["Content-Type"], "application/problem+json"); self.assertEqual(r.headers["WWW-Authenticate"], "Bearer")
        r = self.srv.request("GET", "/api/me"); self.assertEqual(json.loads(r.read())["id"], "u_gk")
        c = json.loads(self.srv.request("POST", "/api/conversations", {"assistantId": "employee-assistant"}, headers={"Idempotency-Key": "c1"}).read())
        r = self.srv.request("POST", f"/api/conversations/{c['id']}/turns", {"text": "hello"}, headers={"Accept": "text/event-stream"})
        self.assertEqual(r.headers["Content-Type"], "text/event-stream")
        kinds = [json.loads(l[5:])["view"]["kind"] for l in r.read().decode().splitlines() if l.startswith("data:")]
        self.assertEqual(kinds[0], "tool_call"); self.assertEqual(kinds[-1], "feedback")
        r = self.srv.request("GET", "/discover/tools/audit-chain", token=None); self.assertEqual(r.status, 200); self.assertIn("<title>hub</title>", r.read().decode())
        r = self.srv.request("GET", "/assets/a.js", token=None); self.assertIn("immutable", r.headers["Cache-Control"]); self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        r = self.srv.request("GET", "/../etc/passwd", token=None); self.assertEqual(r.status, 200)  # the SPA fallback, never a file outside dist
