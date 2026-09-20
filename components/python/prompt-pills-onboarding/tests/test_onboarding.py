import json, unittest
from onboarding import EXAMPLE, Pill


class Onboarding(unittest.TestCase):
    def test_pills_filtered_by_increment_and_role(self):
        self.assertEqual({p.tier for p in EXAMPLE.visible_pills([], 1)}, {"R"})
        self.assertIn("mitigate", [p.id for p in EXAMPLE.visible_pills([], 3)])
        b = EXAMPLE.__class__(**{**EXAMPLE.__dict__, "pills": EXAMPLE.pills + [Pill("comms", "Customer status", "update customer", "Act", "W1", needs=("communications",))]})
        self.assertNotIn("comms", [p.id for p in b.visible_pills(["operator"], 3)]); self.assertIn("comms", [p.id for p in b.visible_pills(["communications"], 3)])

    def test_welcome_card_is_valid_and_buttons_carry_the_command(self):
        card = EXAMPLE.welcome_card({"service": "payments-api", "incident": "inc_1"}, "https://app.example", roles=[], increment=2)
        json.dumps(card); self.assertEqual(card["type"], "AdaptiveCard")
        submits = [a for a in card["actions"] if a["type"] == "Action.Submit"]
        self.assertTrue(submits); self.assertTrue(all(a["data"]["incident"] == "inc_1" for a in submits))
        self.assertTrue(all("<" not in a["data"]["text"] for a in submits))                      # placeholders are hints, never buttons
        self.assertNotIn("mitigate", json.dumps(card)); self.assertIn("payments-api", card["body"][1]["text"])
        self.assertTrue(card["actions"][-1]["url"].endswith("/help")); self.assertLessEqual(len(submits), 6)

    def test_hint_and_guide(self):
        self.assertIn("@Bot help", EXAMPLE.first_time_hint("Dana"))
        g = EXAMPLE.guide_html()
        self.assertIn("a second person approves", g); self.assertIn("<h3>Read</h3>", g); self.assertIn("never changes production", g)
