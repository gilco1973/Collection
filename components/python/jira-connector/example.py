"""Live example: the fake, then the real client against a recording HTTP double (the token never appears in a URL).

    python3 example.py
"""
import json
from jira import FakeJira, JiraClient, JiraError, handlers

fake = FakeJira({"INC-7": {"summary": "Checkout errors", "description": "5xx since 14:05", "status": "Open"}})
h = handlers(fake)
cred = {"audience": "tickets", "on_behalf_of": "u_dana"}
print("read:", h["get"]({"key": "INC-7"}, cred)["summary"])
print("comment:", h["comment"]({"key": "INC-7", "body": "First read posted."}, cred), "| by:", fake.comments[-1]["by"])
try:
    h["comment"]({"key": "INC-7", "body": "x"}, {"audience": "deploys", "on_behalf_of": "u_dana"})
except JiraError as e:
    print("wrong audience refused:", e)


class RecordingHttp:
    def __init__(self): self.calls = []
    def json(self, method, url, headers, payload=None):
        self.calls.append((method, url, headers.get("Authorization", "")[:6], payload))
        return {"key": "INC-7", "id": "10001", "fields": {"summary": "Checkout errors", "status": {"name": "Open"}, "labels": ["sev2"]}}


class Secrets:
    def get(self, name): return "TOKEN-FROM-" + name


http = RecordingHttp()
real = JiraClient(http, Secrets(), "https://jira.bank.example", "agents/jira-token", user="agents@bank.example")
print("real get:", real.get_issue("INC-7")["labels"], "| url:", http.calls[-1][1], "| auth scheme:", http.calls[-1][2])
real.add_comment("INC-7", "hello", "u_dana")
print("real comment payload names the person:", "on behalf of u_dana" in http.calls[-1][3]["body"])
print("token in any url:", any("TOKEN" in c[1] for c in http.calls))
