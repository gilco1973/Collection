"""Live example: the fake shaped for an incident agent, then the real client against a recording HTTP double.

    python3 example.py
"""
import time
from ado import AdoClient, AdoError, FakeAdo, handlers

fake = FakeAdo(); now = time.time()
fake.seed(42, [{"id": 4822, "name": "checkout 2.14.0", "state": "completed", "result": "succeeded", "created": "", "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 7 * 60)), "url": None},
               {"id": 4810, "name": "checkout 2.13.9", "state": "completed", "result": "succeeded", "created": "", "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 3600)), "url": None}])
h = handlers(fake, pipelines={"checkout": 42})
cred = {"audience": "deploys", "on_behalf_of": "u_dana"}
print("latest deploy:", h["recent"]({"service": "checkout", "trigger_ts": now}, cred))
try:
    h["recent"]({"service": "ledger"}, cred)
except AdoError as e:
    print("unknown service refused:", e)
print("rollback (W2, after the harness's dual control):", h["rollback"]({"service": "checkout", "run_id": 4822}, cred), "| requested by:", fake.started[-1]["by"])


class RecordingHttp:
    def __init__(self): self.calls = []
    def json(self, method, url, headers, payload=None):
        self.calls.append((method, url, headers.get("Authorization", "")[:6], payload))
        return {"value": [{"id": 1, "name": "n", "state": "completed", "result": "succeeded", "createdDate": "", "finishedDate": "2026-09-20T14:05:00Z", "_links": {"web": {"href": "https://dev.azure.example/run/1"}}}], "id": 2, "state": "inProgress"}


class Secrets:
    def get(self, name): return "PAT-FROM-" + name


http = RecordingHttp()
real = AdoClient(http, Secrets(), "https://dev.azure.com/ORG", "PROJECT", "agents/ado-pat")
print("real runs:", real.recent_runs(42)["runs"][0]["url"], "| url:", http.calls[-1][1])
print("PAT in any url:", any("PAT" in c[1] for c in http.calls), "| auth scheme:", http.calls[-1][2])
