import json, os, tempfile, unittest
import secrets as S


class Secrets(unittest.TestCase):
    def test_env_file_dict_providers(self):
        os.environ["APP_SECRET_PAGERDUTY_API"] = "v1"
        try: self.assertEqual(S.EnvSecrets().get("pagerduty/api"), "v1")
        finally: del os.environ["APP_SECRET_PAGERDUTY_API"]
        with self.assertRaises(S.SecretError): S.EnvSecrets().get("missing")
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"a": "1"}, f)
        self.assertEqual(S.FileSecrets(f.name).get("a"), "1")
        with self.assertRaises(S.SecretError): S.DictSecrets({}).get("a")

    def test_secrets_manager_caches_and_fetches_by_name(self):
        calls = []
        class Aws:
            def call(self, service, prefix, target, payload):
                calls.append(payload["SecretId"]); return {"SecretString": "value"}
        sm = S.SecretsManager(Aws(), ttl_s=300)
        self.assertEqual(sm.get("app/key"), "value"); self.assertEqual(sm.get("app/key"), "value"); self.assertEqual(calls, ["app/key"])

    def test_provider_from_env(self):
        os.environ["APP_SECRETS"] = "env"; self.assertIsInstance(S.provider_from_env(), S.EnvSecrets)
        os.environ["APP_SECRETS"] = "aws"
        with self.assertRaises(S.SecretError): S.provider_from_env()
        os.environ["APP_SECRETS"] = "weird"
        with self.assertRaises(S.SecretError): S.provider_from_env()
        del os.environ["APP_SECRETS"]

    def test_handler_refuses_without_a_redeemed_credential(self):
        with self.assertRaises(S.UpstreamError): S.require_credential({}, "jira")
        with self.assertRaises(S.UpstreamError): S.require_credential({"audience": "ado", "on_behalf_of": "u"}, "jira")
        self.assertEqual(S.require_credential({"audience": "jira", "on_behalf_of": "u_dana"}, "jira"), "u_dana")
