import unittest
from teams_graph import AppToken, FakeTeams, GraphClient, MAX_MESSAGE, UpstreamError, chunk


class Chunk(unittest.TestCase):
    def test_short_text_untouched_and_long_text_numbered(self):
        self.assertEqual(chunk("hello"), ["hello"])
        paras = "\n\n".join(f"paragraph {i} " + "x" * 900 for i in range(10))
        parts = chunk(paras)
        self.assertGreater(len(parts), 1); self.assertTrue(all(len(p) <= MAX_MESSAGE for p in parts))
        self.assertTrue(parts[0].startswith("(1/")); self.assertTrue(parts[-1].startswith(f"({len(parts)}/{len(parts)})"))
        self.assertEqual("".join(p.split(") ", 1)[1] for p in parts).replace("\n\n", "").replace("\n", ""), paras.replace("\n\n", "").replace("\n", ""))

    def test_hard_cut_when_one_paragraph_exceeds_the_limit(self):
        parts = chunk("y" * 9000)
        self.assertEqual(len(parts), 3); self.assertTrue(all(len(p) <= MAX_MESSAGE for p in parts))


class Fake(unittest.TestCase):
    def test_room_lifecycle_and_failures_are_loud(self):
        t = FakeTeams(); t.add_user("u1", ["g-team"])
        self.assertEqual(t.check_member_groups("u1", ["g-team", "g-other"]), ["g-team"])
        ch = t.create_channel("team", "inc-1 payments-api", "war room")
        m = t.post_message("team", ch["channel_id"], "<b>hi</b>", mentions=[{"id": "u1", "name": "Dana"}])
        t.pin_message("team", ch["channel_id"], m["message_id"]); t.post_card("team", ch["channel_id"], {"type": "AdaptiveCard"})
        self.assertEqual(len(t.in_channel(ch["channel_id"])), 2); self.assertEqual(t.pins, [(ch["channel_id"], m["message_id"])])
        t.fail_next = 1
        with self.assertRaises(UpstreamError): t.post_message("team", ch["channel_id"], "x")
        t.post_message("team", ch["channel_id"], "x")                                            # transient: the next call works
        t.down = True
        with self.assertRaises(UpstreamError): t.create_channel("team", "n", "d")


class Live(unittest.TestCase):
    """The live client against a recording HTTP double: the token is fetched once and cached, calls hit the Graph URLs."""
    class Http:
        def __init__(self): self.calls = []
        def form(self, url, fields, headers=None):
            self.calls.append(("form", url)); return {"access_token": "tok", "expires_in": 3600}
        def json(self, method, url, headers=None, payload=None, expect=None):
            self.calls.append((method, url, headers.get("Authorization"), payload)); return {"id": "42", "webUrl": "https://teams.example/x", "value": ["g1"]}
    class Secrets:
        def get(self, name): return "client-secret"

    def test_token_cached_and_graph_calls_shaped(self):
        http = self.Http(); tok = AppToken(http, self.Secrets(), "tenant", "app", "bot/app-secret"); g = GraphClient(http, tok)
        ch = g.create_channel("team", "inc-1", "room"); g.post_message("team", ch["channel_id"], "<b>x</b>"); g.pin_message("team", ch["channel_id"], "42")
        self.assertEqual(sum(1 for c in http.calls if c[0] == "form"), 1)
        self.assertEqual(http.calls[1][1], "https://graph.microsoft.com/v1.0/teams/team/channels"); self.assertEqual(http.calls[1][2], "Bearer tok")
        self.assertEqual(g.check_member_groups("u1", ["g1"]), ["g1"])
        with self.assertRaises(UpstreamError): g.reply_via_connector("https://smba", "conv", {})    # no bot token configured
