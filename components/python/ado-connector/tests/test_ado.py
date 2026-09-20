import time, unittest
from ado import AdoClient, AdoError, FakeAdo, handlers


class Recording:
    def __init__(self):
        self.calls = []
        self.reply = {"value": [{"id": 7, "name": "r", "state": "completed", "result": "succeeded", "createdDate": "", "finishedDate": "2026-09-20T14:05:00Z"}], "id": 8, "state": "inProgress"}
    def json(self, method, url, headers, payload=None):
        self.calls.append({"method": method, "url": url, "headers": headers, "payload": payload}); return self.reply


class S:
    def get(self, name): return "pat-" + name


class Client(unittest.TestCase):
    def test_urls_auth_and_shapes(self):
        http = Recording(); c = AdoClient(http, S(), "https://dev.azure.com/org/", "My Project", "ado/pat")
        r = c.recent_runs(42, 5)
        self.assertEqual(r["runs"][0]["id"], 7); self.assertIn("/My%20Project/_apis/pipelines/42/runs?api-version=7.1&$top=5", http.calls[0]["url"])
        self.assertTrue(http.calls[0]["headers"]["Authorization"].startswith("Basic ")); self.assertNotIn("pat-", http.calls[0]["url"])
        http.reply = {"id": 7, "name": "r", "state": "completed", "result": "succeeded"}
        self.assertEqual(c.get_run(42, 7)["state"], "completed")
        http.reply = {"id": 8, "state": "inProgress"}
        out = c.run_pipeline(42, "u_dana", {"target_run": 4822}, "rollback")
        self.assertEqual(out, {"run_id": 8, "status": "inProgress"}); self.assertEqual(http.calls[-1]["payload"]["variables"]["requestedBy"], {"value": "u_dana"})

    def test_latest_deploy_is_minutes_before_the_trigger(self):
        f = FakeAdo(); now = time.time()
        f.seed(1, [{"id": 2, "result": "succeeded", "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 600)), "name": "b"}, {"id": 1, "result": "failed", "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 60)), "name": "a"}])
        d = f.latest_deploy(1, "svc", now)
        self.assertEqual((d["run_id"], d["service"], d["minutes_before_trigger"]), (2, "svc", 10))
        self.assertIsNone(FakeAdo().latest_deploy(9, "svc", now)["run_id"])


class Handlers(unittest.TestCase):
    def test_service_map_and_credential_rules(self):
        f = FakeAdo(); f.seed(42, [{"id": 4822, "result": "succeeded", "finished": "2026-09-20T14:00:00Z", "name": "x"}]); h = handlers(f, pipelines={"checkout": 42})
        cred = {"audience": "deploys", "on_behalf_of": "u"}
        self.assertEqual(h["recent"]({"service": "checkout", "trigger_ts": 1789999999}, cred)["run_id"], 4822)
        with self.assertRaises(AdoError):
            h["recent"]({"service": "ledger"}, cred)
        with self.assertRaises(AdoError):
            h["rollback"]({"service": "checkout", "run_id": 4822}, {"audience": "tickets", "on_behalf_of": "u"})
        self.assertEqual(f.started, [])
        h["rollback"]({"service": "checkout", "run_id": 4822}, cred); self.assertEqual(f.started[0]["by"], "u")
