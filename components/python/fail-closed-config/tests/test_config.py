import io, os, unittest
import config


class Config(unittest.TestCase):
    def test_fake_sandbox_is_valid_and_fake_production_is_not(self):
        self.assertEqual(config.Settings().validate(), [])
        self.assertIn("fake mode is refused in production", config.Settings(mode="fake", env="production").validate())

    def test_live_requires_every_gate_and_names_the_variable_not_the_value(self):
        p = config.Settings(mode="live", env="production").validate()
        for needle in ("APP_DB", "APP_PUBLIC_URL", "APP_IDP_ISSUER", "APP_TEAM_GATE_GROUP_IDS", "APP_OPERATOR_GROUP_ID", "APP_OBSERVABILITY_TARGETS"):
            self.assertTrue(any(needle in x for x in p), needle)
        with self.assertRaises(config.ConfigError): config.Settings(mode="live").require_valid()

    def test_live_complete_is_valid(self):
        s = config.Settings(mode="live", env="staging", db_path="/var/app/app.db", public_base_url="https://app.example", idp_issuer="https://idp", idp_audience="app",
                            team_gate_group_ids=("g1",), operator_group_id="g2", observability_targets=("newrelic",))
        self.assertEqual(s.validate(), []); self.assertIs(s.require_valid(), s)
        self.assertEqual(s.diagnostics()["team_gate_group_ids"], "set (1 items)"); self.assertNotIn("g2", str(s.diagnostics()))

    def test_from_env_and_check_config(self):
        env = {"APP_MODE": "live", "APP_ENV": "staging", "APP_DB": "/var/app/app.db", "APP_PUBLIC_URL": "https://x", "APP_IDP_ISSUER": "https://i", "APP_IDP_AUDIENCE": "a",
               "APP_TEAM_GATE_GROUP_IDS": "g1, g2", "APP_OPERATOR_GROUP_ID": "", "APP_OBSERVABILITY_TARGETS": "elastic"}
        os.environ.update(env)
        try:
            s = config.Settings.from_env(); self.assertEqual(s.team_gate_group_ids, ("g1", "g2")); self.assertEqual(s.operator_group_id, "")
            out = io.StringIO(); self.assertEqual(config.check_config(out=out), 2); self.assertIn("APP_OPERATOR_GROUP_ID", out.getvalue())
            os.environ["APP_OPERATOR_GROUP_ID"] = "g3"
            out = io.StringIO(); self.assertEqual(config.check_config(out=out), 0); self.assertEqual(out.getvalue().strip(), "config ok")
        finally:
            for k in env: os.environ.pop(k, None)
