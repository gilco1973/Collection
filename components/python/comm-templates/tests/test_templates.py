import unittest
import templates


class Templates(unittest.TestCase):
    def test_fields_only_and_escaped(self):
        r = templates.render("status_internal@1", {"incident": "PD1", "severity": "SEV2", "service": "x", "status": "assembled", "impact": "<b>i</b>", "next_update_in": "30 min"})
        self.assertIn("&lt;b&gt;", r["html"]); self.assertEqual(r["audience"], "internal"); self.assertIn("<b>i</b>", r["text"]); self.assertTrue(r["registry_hash"].startswith("sha256:"))

    def test_missing_and_unknown_fields_refused(self):
        with self.assertRaises(templates.TemplateError): templates.render("status_internal@1", {"incident": "PD1"})
        with self.assertRaises(templates.TemplateError): templates.render("customer_status@1", {"service_public_name": "P", "status": "s", "impact_public": "i", "next_update_in": "1h", "free_text": "x"})
        with self.assertRaises(templates.TemplateError): templates.render("nope@1", {})

    def test_customer_template_carries_the_disclosure_and_optional_fields_default(self):
        r = templates.render("customer_status@1", {"service_public_name": "P", "status": "s", "impact_public": "i", "next_update_in": "1h"})
        self.assertIn("No customer data is known to be affected", r["text"]); self.assertEqual(r["owner"], "compliance")
        r2 = templates.render("leadership@1", {"incident": "I", "severity": "S", "service": "x", "customer_impact": "none", "status": "s", "eta": "1h"})
        self.assertIn("Incident commander: —", r2["text"])
