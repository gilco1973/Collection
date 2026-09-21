import unittest
from jira import FakeJira, JiraClient, JiraError, handlers


class Recording:
    def __init__(self, reply=None): self.calls, self.reply = [], reply or {"key": "K-1", "id": "1", "fields": {"summary": "s", "status": {"name": "Open"}, "assignee": {"accountId": "a1"}, "labels": []}}
    def json(self, method, url, headers, payload=None):
        self.calls.append({"method": method, "url": url, "headers": headers, "payload": payload}); return self.reply


class S:
    def get(self, name): return "tok-" + name


class Client(unittest.TestCase):
    def test_basic_and_bearer_auth_and_shapes(self):
        http = Recording(); c = JiraClient(http, S(), "https://jira.example/", "jira/token", user="svc@example")
        i = c.get_issue("K-1")
        self.assertEqual((i["key"], i["status"], i["assignee"]), ("K-1", "Open", "a1"))
        self.assertTrue(http.calls[0]["headers"]["Authorization"].startswith("Basic ")); self.assertIn("/rest/api/2/issue/K-1", http.calls[0]["url"])
        b = JiraClient(http, S(), "https://jira.example", "jira/token", auth="bearer"); b.search("project = X")
        self.assertEqual(http.calls[-1]["headers"]["Authorization"], "Bearer tok-jira/token"); self.assertIn("jql=project%20%3D%20X", http.calls[-1]["url"])
        self.assertFalse(any("tok-" in x["url"] for x in http.calls))
        with self.assertRaises(JiraError):
            JiraClient(http, S(), "u", "t", auth="cookie")

    def test_writes_carry_the_acting_person(self):
        http = Recording({"id": 55, "key": "K-1"}); c = JiraClient(http, S(), "https://jira.example", "t", user="u")
        self.assertEqual(c.add_comment("K-1", "hi", "u_dana"), {"id": "55", "key": "K-1"}); self.assertIn("on behalf of u_dana", http.calls[-1]["payload"]["body"])
        c.create_issue("OPS", "s", "d", ["a"], "u_dana"); self.assertIn("on behalf of u_dana", http.calls[-1]["payload"]["fields"]["description"])


class Handlers(unittest.TestCase):
    def test_handlers_need_a_redeemed_reference_for_their_audience(self):
        f = FakeJira({"K-1": {"summary": "s"}}); h = handlers(f, "tickets")
        self.assertEqual(h["get"]({"key": "K-1"}, {"audience": "tickets", "on_behalf_of": "u"})["summary"], "s")
        for bad in (None, {}, {"audience": "other", "on_behalf_of": "u"}, {"audience": "tickets"}):
            with self.assertRaises(JiraError):
                h["comment"]({"key": "K-1", "body": "x"}, bad)
        self.assertEqual(f.comments, [])
        h["comment"]({"key": "K-1", "body": "x"}, {"audience": "tickets", "on_behalf_of": "u_dana"}); self.assertEqual(f.comments[0]["by"], "u_dana")
        f.down = True
        with self.assertRaises(JiraError):
            h["get"]({"key": "K-1"}, {"audience": "tickets", "on_behalf_of": "u"})


class Keys(unittest.TestCase):
    def test_an_issue_key_is_one_path_segment(self):
        http = Recording(); c = JiraClient(http, S(), "https://jira.example", "t", user="u")
        for bad in ("INC-7/../../myself", "INC-7?x=1", "inc-7", "", "INC", "INC-7/transitions"):
            with self.assertRaises(JiraError): c.get_issue(bad)
            with self.assertRaises(JiraError): c.add_comment(bad, "hi", "u_dana")
        self.assertEqual(http.calls, [])
        c.get_issue("OPS_2-42"); self.assertTrue(http.calls[-1]["url"].startswith("https://jira.example/rest/api/2/issue/OPS_2-42?"))
