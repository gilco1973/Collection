"""The sixth round of hardening: preferences keep the values the hub can apply and merge over what the record holds,
and the http relay notices an upstream that dies mid-answer (a closed socket, a bad chunk, a body short of its
Content-Length) so the turn ends with a stop view and is recorded as such, never as a finished answer."""
import http.client, json, logging, threading, time, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from hubapi import app as A
from hubapi.assistant import HttpRelayAssistant, read_lines
from tests.support import Client, make_api

FRAME = b'event: view\ndata: {"seq": %d, "view": {"kind": "text", "provenance": "model", "text": "part %d"}}\n\n'


def quiet(test: unittest.TestCase):
    lg = logging.getLogger("hubapi"); level = lg.level; lg.setLevel(logging.CRITICAL)
    test.addCleanup(lg.setLevel, level)


class Upstream(BaseHTTPRequestHandler):
    """What it does depends on the turn's text: 'badchunk' ends with a chunk-size line that is not hex, 'cut' closes
    the socket inside a chunk, 'short' promises a Content-Length it never sends; otherwise a whole answer."""
    protocol_version = "HTTP/1.1"

    def log_message(self, *a): pass

    def do_POST(self):
        text = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}").get("text", "")
        frames = [FRAME % (i, i) for i in (1, 2, 3)]
        if "short" in text:
            body = b"".join(frames)
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Content-Length", str(len(body) + 500)); self.end_headers()
            self.wfile.write(frames[0]); self.wfile.flush(); self.close_connection = True; self.connection.close(); return
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Transfer-Encoding", "chunked"); self.end_headers()
        for f in frames[:2]:
            self.wfile.write(b"%x\r\n%s\r\n" % (len(f), f)); self.wfile.flush()
        if "badchunk" in text:
            self.wfile.write(b"zz\r\ngarbage\r\n"); self.wfile.flush(); self.close_connection = True; self.connection.close(); return
        if "cut" in text:
            self.wfile.write(b"%x\r\n%s" % (len(frames[2]), frames[2][:10])); self.wfile.flush(); self.close_connection = True; self.connection.close(); return
        self.wfile.write(b"%x\r\n%s\r\n0\r\n\r\n" % (len(frames[2]), frames[2])); self.wfile.flush()


class Secrets:
    def get(self, name): return "tok"


class P:
    id = "u_1"


class RelayMidStream(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def relay(self):
        return HttpRelayAssistant(self.base, Secrets(), "hub/assistant-token", timeout=5.0)

    def test_a_whole_answer_still_reads_every_frame(self):
        views = list(self.relay().stream({"id": "c1", "turns": []}, "hello", P()))
        self.assertEqual([v["text"] for v in views], ["part 1", "part 2", "part 3"])

    def test_line_iteration_would_end_silently_but_read1_raises(self):
        """The defect: `for line in resp` peeks the next chunk and swallows the IncompleteRead, so the stream just ends."""
        import urllib.request
        for text in ("badchunk", "cut", "short"):
            req = urllib.request.Request(f"{self.base}/conversations/c1/turns", data=json.dumps({"text": text}).encode(), headers={"Content-Type": "application/json"}, method="POST")
            resp = urllib.request.urlopen(req, timeout=5)
            got = []
            with self.assertRaises(http.client.HTTPException, msg=text):
                for line in read_lines(resp):
                    if line.startswith(b"data:"): got.append(line)
            self.assertGreaterEqual(len(got), 1, f"{text}: the frames before the failure are delivered")
        req = urllib.request.Request(f"{self.base}/conversations/c1/turns", data=json.dumps({"text": "badchunk"}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        resp = urllib.request.urlopen(req, timeout=5)
        lines = [l for l in resp]   # no exception: this is what the relay used to rely on
        self.assertEqual(sum(1 for l in lines if l.startswith(b"data:")), 2)

    def test_the_relay_raises_for_each_way_an_upstream_can_die(self):
        for text in ("badchunk", "cut", "short"):
            it = self.relay().stream({"id": "c1", "turns": []}, text, P())
            first = next(it)
            self.assertEqual(first["text"], "part 1")
            with self.assertRaises(http.client.HTTPException, msg=text):
                list(it)

    def test_through_the_api_the_turn_ends_with_a_stop_view_that_is_recorded(self):
        quiet(self)
        api = make_api(assistant=self.relay()); gk = Client(api, "mock.gk")
        s, c = gk.call("POST", "/conversations", {"assistantId": "employee-assistant"}); self.assertEqual(s, 201)
        for text in ("badchunk", "cut", "short"):
            s, events = gk.call("POST", f"/conversations/{c['id']}/turns", {"text": text})
            self.assertEqual(s, 200)
            kinds = [e["view"]["kind"] for e in events]
            self.assertEqual(kinds[-1], "stop", text)
            self.assertEqual(events[-1]["view"]["reason"], "upstream.error")
            self.assertGreaterEqual(kinds.count("text"), 1, "the frames that arrived are kept")
            self.assertEqual([e["seq"] for e in events], list(range(events[0]["seq"], events[0]["seq"] + len(events))), "one envelope, contiguous seq")
            s, rec = gk.call("GET", f"/conversations/{c['id']}")
            last = rec["turns"][-1]["views"]
            self.assertEqual(last[-1], A.UPSTREAM_STOP, "the record shows why the answer ended")
        s, events = gk.call("POST", f"/conversations/{c['id']}/turns", {"text": "fine again"})
        self.assertEqual([e["view"]["kind"] for e in events], ["text", "text", "text"], "the conversation is not stuck busy afterwards")


class PreferencesEnumsAndMerge(unittest.TestCase):
    def test_theme_and_density_outside_the_enum_are_422_and_never_stored(self):
        api = make_api(); gk = Client(api, "mock.gk")
        for body, key in (({"theme": "purple"}, "theme"), ({"density": "huge"}, "density"), ({"theme": "dark", "density": "x"}, "density")):
            s, p = gk.call("PUT", "/me/preferences", body)
            self.assertEqual(s, 422, body); self.assertEqual(p["code"], "validation"); self.assertIn(key, p["errors"])
        self.assertIsNone(api.store.get("prefs", "u_gk"), "a refused PUT writes nothing")
        self.assertEqual(gk.call("GET", "/me")[1]["preferences"]["theme"], "system")
        for theme in ("system", "light", "dark"):
            self.assertEqual(gk.call("PUT", "/me/preferences", {"theme": theme})[0], 200)
        for density in ("comfortable", "dense"):
            self.assertEqual(gk.call("PUT", "/me/preferences", {"density": density})[0], 200)

    def test_a_partial_put_merges_over_the_stored_record_not_only_the_defaults(self):
        api = make_api(); gk = Client(api, "mock.gk")
        s, me = gk.call("PUT", "/me/preferences", {"theme": "dark", "density": "dense", "locale": "en-GB", "noAssistant": True, "notifications": {"digest": True, "briefs": False}})
        self.assertEqual(s, 200)
        stored = {**A.DEFAULT_PREFS, "theme": "dark", "density": "dense", "locale": "en-GB", "noAssistant": True, "notifications": {"requests": True, "briefs": False, "digest": True}}
        self.assertEqual(me["preferences"], stored)
        # The second, partial PUT names one key: everything else keeps its stored value, not its default.
        s, me = gk.call("PUT", "/me/preferences", {"theme": "light"})
        self.assertEqual((s, me["preferences"]), (200, {**stored, "theme": "light"}))
        self.assertEqual(api.store.get("prefs", "u_gk"), {**stored, "theme": "light"})
        self.assertEqual(gk.call("GET", "/me")[1]["preferences"], {**stored, "theme": "light"})
        # notifications likewise: one flag named, the other two stay as stored.
        s, me = gk.call("PUT", "/me/preferences", {"notifications": {"requests": False}})
        self.assertEqual(me["preferences"]["notifications"], {"requests": False, "briefs": False, "digest": True})
        # An empty object sets nothing.
        s, me = gk.call("PUT", "/me/preferences", {})
        self.assertEqual(me["preferences"], {**stored, "theme": "light", "notifications": {"requests": False, "briefs": False, "digest": True}})
        # merge_prefs itself, over a base.
        self.assertEqual(A.merge_prefs({"theme": "dark"}, {"density": "dense", "notifications": {"digest": True}}), {**A.DEFAULT_PREFS, "theme": "dark", "density": "dense", "notifications": {**A.DEFAULT_PREFS["notifications"], "digest": True}})
        self.assertEqual(A.merge_prefs(None, None), A.DEFAULT_PREFS)


if __name__ == "__main__":
    unittest.main()
