"""Live example: a war room on the in-memory Teams, a long answer chunked, and a transient failure that is never silent."""
from teams_graph import FakeTeams, UpstreamError, chunk
t = FakeTeams(); t.add_user("u_dana", ["g-oncall"])
print("gate:", t.check_member_groups("u_dana", ["g-oncall", "g-other"]))
room = t.create_channel("team-1", "inc-42 payments-api", "war room"); print("room:", room["channel_id"])
card = t.post_card("team-1", room["channel_id"], {"type": "AdaptiveCard", "body": [{"type": "TextBlock", "text": "SEV2 payments-api"}]}); t.pin_message("team-1", room["channel_id"], card["message_id"])
answer = "\n\n".join(f"Paragraph {i}: " + "the error rate rose after the deploy. " * 25 for i in range(6))
parts = chunk(answer); print(f"{len(answer)} characters -> {len(parts)} parts, each <= 4000; first starts with {parts[0][:6]!r}")
for p in parts: t.post_message("team-1", room["channel_id"], p)
print("messages in the room:", len(t.in_channel(room["channel_id"])), "| pinned:", len(t.pins))
t.fail_next = 1
try: t.post_message("team-1", room["channel_id"], "one more")
except UpstreamError as e: print("transient failure surfaced, not swallowed:", e)
