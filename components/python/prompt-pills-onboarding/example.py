"""Live example: the how-to card for an increment-2 room, the first-time hint, and the guide's command table."""
import json
from onboarding import EXAMPLE
card = EXAMPLE.welcome_card({"service": "payments-api", "incident": "inc_42"}, "https://app.example", roles=["operator"], increment=2)
print("card blocks:", len(card["body"]), "| buttons:", [a["title"] for a in card["actions"] if a["type"] == "Action.Submit"])
print("W2 pill hidden at increment 2:", "mitigate" not in json.dumps(card))
print(EXAMPLE.first_time_hint("Dana"))
print("guide has", EXAMPLE.guide_html().count("<tr><td><code>"), "command rows")
