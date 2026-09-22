import os
import unittest

from tests.helpers import C, EXAMPLES, target, tempdir, write


class Targets(unittest.TestCase):
    def test_every_example_target_file_loads(self):
        for f in os.listdir(EXAMPLES):
            if f.endswith(".json") and "suite" not in f:
                t = C.load(os.path.join(EXAMPLES, f))
                self.assertTrue(t.name, f)

    def test_required_fields_and_names(self):
        with self.assertRaisesRegex(C.ConfigError, "`kind` is required"):
            C.load({"name": "x", "environment": "sandbox"})
        with self.assertRaisesRegex(C.ConfigError, "lower case"):
            C.load({"name": "Bad Name", "kind": "demo", "demo": "safe", "environment": "sandbox"})
        with self.assertRaisesRegex(C.ConfigError, "unknown field"):
            C.load({"name": "x", "kind": "demo", "demo": "safe", "environment": "sandbox", "urll": "typo"})

    def test_production_is_never_probed(self):
        for env in ("production", "prod", "live", ""):
            with self.assertRaises(C.ConfigError):
                C.load({"name": "x", "kind": "demo", "demo": "safe", "environment": env})

    def test_remote_hosts_must_be_listed(self):
        with self.assertRaisesRegex(C.ConfigError, "allow_hosts"):
            target(kind="http", preset="openai-chat", url="https://gateway.example.internal/v1/chat/completions")
        t = target(kind="http", preset="openai-chat", url="https://gateway.example.internal/v1/chat/completions", allow_hosts=["gateway.example.internal"])
        self.assertEqual(t.url, "https://gateway.example.internal/v1/chat/completions")
        self.assertTrue(C.host_allowed("https://a.sandbox.example.internal/x", ["*.sandbox.example.internal"]))
        self.assertFalse(C.host_allowed("https://sandbox.example.internal.evil.example/x", ["*.sandbox.example.internal"]))
        self.assertFalse(C.host_allowed("https://sandbox.example.internal/x", ["*.sandbox.example.internal"]))
        self.assertTrue(C.host_allowed("http://localhost:9/x", []))

    def test_a_credential_in_the_url_is_refused(self):
        with self.assertRaisesRegex(C.ConfigError, "header"):
            target(kind="http", preset="simple-json", url="http://127.0.0.1:1/chat?key=${env:KEY}")

    def test_secrets_are_names_resolved_at_call_time_and_never_described(self):
        t = target(kind="http", preset="openai-chat", url="http://127.0.0.1:1/v1", headers={"Authorization": "Bearer ${env:PG_TOKEN}"})
        self.assertEqual(t.secret_names(), ["PG_TOKEN"])
        self.assertEqual(C.resolve_secrets(t.headers, {"PG_TOKEN": "s3cr3t-value"})["Authorization"], "Bearer s3cr3t-value")
        with self.assertRaisesRegex(C.ConfigError, "PG_TOKEN is not set"):
            C.resolve_secrets(t.headers, {})
        os.environ["PG_TOKEN"] = "s3cr3t-value"
        try:
            self.assertNotIn("s3cr3t-value", str(t.describe()))
            self.assertIn("s3cr3t-value", C.secret_values(t))
        finally:
            del os.environ["PG_TOKEN"]

    def test_presets_fill_body_and_response(self):
        t = target(kind="http", preset="anthropic-messages", url="http://127.0.0.1:1/v1/messages", headers={"x-api-key": "${env:K}"})
        self.assertEqual(t.response["text"], "content.0.text")
        self.assertEqual(t.headers["anthropic-version"], "2023-06-01")
        self.assertIn("x-api-key", t.headers)
        with self.assertRaisesRegex(C.ConfigError, "preset"):
            target(kind="http", preset="nope", url="http://127.0.0.1:1/")
        with self.assertRaisesRegex(C.ConfigError, "response.text"):
            target(kind="http", url="http://127.0.0.1:1/", body={"q": "{{prompt}}"})

    def test_command_python_and_limits(self):
        with tempdir() as d:
            f = write(os.path.join(d, "t.json"), {"name": "c", "kind": "command", "environment": "dev", "command": ["python3", "./x.py"]})
            self.assertEqual(C.load(f).command[1], os.path.join(d, "./x.py"))
            with self.assertRaisesRegex(C.ConfigError, "not a directory"):
                C.load({"name": "p", "kind": "python", "environment": "dev", "callable": "m:f", "path": os.path.join(d, "missing")})
        with self.assertRaisesRegex(C.ConfigError, "module:function"):
            target(kind="python", callable="nofunction")
        with self.assertRaisesRegex(C.ConfigError, "timeout_s"):
            target(kind="demo", demo="safe", timeout_s=0)
        with self.assertRaisesRegex(C.ConfigError, "concurrency"):
            target(kind="demo", demo="safe", concurrency=100)
        with self.assertRaisesRegex(C.ConfigError, "variable names"):
            target(kind="command", command=["x"], env=["lower"])

    def test_unreadable_files_name_the_problem(self):
        with self.assertRaisesRegex(C.ConfigError, "cannot read"):
            C.load("/nonexistent/target.json")
        with tempdir() as d:
            with self.assertRaisesRegex(C.ConfigError, "not JSON"):
                C.load(write(os.path.join(d, "bad.json"), "{nope"))


if __name__ == "__main__":
    unittest.main()
