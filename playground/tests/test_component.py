import json
import os
import unittest

from tests.helpers import EXAMPLES, tempdir, write
from aiplayground import component as K

SAMPLE = os.path.join(EXAMPLES, "runbook-answerer")


def by_id(results):
    return {r.id.split("/", 1)[1]: r for r in results}


def candidate(d, name="cand", manifest=None, files=None):
    root = os.path.join(d, name)
    with open(os.path.join(SAMPLE, "component.json"), encoding="utf-8") as f:
        m = json.load(f)
    write(os.path.join(d, "tools", "kb-taxonomy.json"), {"tags": ["rag", "security", "agents"]})   # as a checkout of the collection has
    m["name"] = name
    m.update(manifest or {})
    write(os.path.join(root, "component.json"), m)
    for f in ("README.md", "WALKTHROUGH.md", "answerer.py", "example.py", "tests/__init__.py", "tests/test_answerer.py"):
        with open(os.path.join(SAMPLE, f), encoding="utf-8") as src:
            write(os.path.join(root, f), src.read())
    for path, content in (files or {}).items():
        write(os.path.join(root, path), content)
    return root


class Contract(unittest.TestCase):
    def test_the_sample_component_meets_the_contract(self):
        got = by_id(K.check(SAMPLE, run=True, timeout=120))
        for k, r in got.items():
            self.assertEqual(r.status, "pass", f"{k}: {r.summary}")
        self.assertIn("tests", got)
        self.assertIn("example", got)

    def test_manifest_problems(self):
        with tempdir() as d:
            root = candidate(d, manifest={"version": "one", "category": "widget", "summary": "x" * 200, "tags": ["not-a-tag"], "test": ""})
            r = by_id(K.check(root, run=False))["manifest"]
            self.assertEqual(r.status, "fail")
            for words in ("semantic version", "category", "160", "taxonomy", "`test`"):
                self.assertIn(words, json.dumps(r.evidence))
            os.remove(os.path.join(root, "component.json"))
            self.assertIn("no component.json", by_id(K.check(root, run=False))["manifest"].summary)

    def test_readme_headings(self):
        with tempdir() as d:
            root = candidate(d, files={"README.md": "# cand\n\nLead.\n\n## Five-minute start\n\nx\n"})
            r = by_id(K.check(root, run=False))["readme"]
            self.assertEqual(r.status, "fail")
            self.assertIn("Known limits", r.summary)

    def test_handwritten_signoffs_go_to_a_person(self):
        with tempdir() as d:
            root = candidate(d, manifest={"signoff": {"owner": {"by": "Someone <s@example.com>", "date": "2026-01-01", "version": "0.1.0"}, "ai_security": None}})
            self.assertEqual(by_id(K.check(root, run=False))["signoffs"].status, "review")

    def test_imports_outside_the_component(self):
        with tempdir() as d:
            root = candidate(d, files={"extra.py": "import requests\nfrom ..elsewhere import thing\nimport sys\nsys.path.insert(0, '../shared')\ntry:\n    import yaml\nexcept ImportError:\n    yaml = None\n"})
            r = by_id(K.check(root, run=False))["self-contained"]
            self.assertEqual(r.status, "fail")
            text = json.dumps(r.evidence)
            self.assertIn("imports requests", text)
            self.assertIn("reaches outside", text)
            self.assertIn("parent directory", text)
            self.assertNotIn("yaml", text)
            root2 = candidate(d, name="cand2", manifest={"requires": ["requests>=2"]}, files={"extra.py": "import requests\n"})
            self.assertEqual(by_id(K.check(root2, run=False))["self-contained"].status, "pass")

    def test_secrets_real_ids_and_real_hosts(self):
        key = "AKIA" + "ABCDEFGHIJKLMNOP"
        pem = "-----BEGIN " + "RSA PRIVATE KEY-----"
        guid = "3f2b" + "9c41-7d6e-4a8b-9f10-2c3d4e5f6a7b"
        with tempdir() as d:
            root = candidate(d, files={"leak.py": f"KEY = '{key}'\nPEM = '''{pem}'''\nTENANT = '{guid}'\nURL = 'https://login.realbank.com/x'\nOK = 'https://idp.example.internal/'\nZERO = '00000000-0000-0000-0000-000000000000'\n"})
            got = by_id(K.check(root, run=False))
            self.assertEqual((got["secrets"].status, got["secrets"].severity), ("fail", "critical"))
            self.assertIn("AWS access key", got["secrets"].summary)
            self.assertEqual(got["real-ids"].status, "review")
            self.assertIn(guid, json.dumps(got["real-ids"].evidence))
            self.assertEqual(got["real-urls"].status, "review")
            self.assertIn("login.realbank.com", got["real-urls"].summary)
            self.assertNotIn("example.internal", got["real-urls"].summary)

    def test_failing_and_slow_tests(self):
        with tempdir() as d:
            root = candidate(d, files={"tests/test_answerer.py": "import unittest\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.fail('red')\n"})
            r = by_id(K.check(root, run=True, timeout=60))["tests"]
            self.assertEqual(r.status, "fail")
            self.assertIn("red", json.dumps(r.evidence))
            slow = candidate(d, name="slow", manifest={"test": "sleep 5"})
            self.assertIn("in time", by_id(K.check(slow, run=True, timeout=1))["tests"].summary)

    def test_tests_run_in_a_copy_without_the_testers_secrets(self):
        os.environ["PG_TESTER_SECRET"] = "must-not-be-seen"
        try:
            with tempdir() as d:
                root = candidate(d, manifest={"test": "env > seen.txt; touch created-here"})
                K.check(root, run=True, timeout=30)
                self.assertFalse(os.path.exists(os.path.join(root, "created-here")))
                probe = candidate(d, name="probe", manifest={"test": "env | grep -q PG_TESTER_SECRET && exit 1 || exit 0"})
                self.assertEqual(by_id(K.check(probe, run=True, timeout=30))["tests"].status, "pass")
        finally:
            del os.environ["PG_TESTER_SECRET"]

    def test_agents_carry_no_money_tool(self):
        tpl = "# Template\n\n```json\n" + json.dumps({"name": "a", "role": "r", "ladder": "L1", "stages": [], "never": ["x"], "budget": {},
                                                    "tools": [{"op": "pay_invoice", "tier": "MONEY"}]}) + "\n```\n"
        with tempdir() as d:
            root = candidate(d, manifest={"category": "agent", "agent": {"template": "TEMPLATE.md", "tools": [], "harness": "h"}}, files={"TEMPLATE.md": tpl})
            got = by_id(K.check(root, run=False))
            self.assertEqual((got["agent-money"].status, got["agent-money"].severity), ("fail", "critical"))
            self.assertEqual(got["agent-template"].status, "pass")

    def test_the_collections_own_components_pass_the_manifest_check(self):
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "components")
        if not os.path.isdir(base):
            self.skipTest("not inside a checkout of the collection")
        for group in os.listdir(base):
            for name in os.listdir(os.path.join(base, group)) if os.path.isdir(os.path.join(base, group)) else []:
                root = os.path.join(base, group, name)
                if os.path.exists(os.path.join(root, "component.json")) and not name.startswith("_"):
                    got = by_id(K.check(root, run=False))
                    self.assertEqual(got["manifest"].status, "pass", f"{name}: {got['manifest'].summary}")
                    self.assertEqual(got["secrets"].status, "pass", f"{name}: {got['secrets'].summary}")


if __name__ == "__main__":
    unittest.main()
