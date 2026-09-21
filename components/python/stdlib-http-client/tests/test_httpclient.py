import unittest
import httpclient


class HttpClient(unittest.TestCase):
    def test_retries_then_succeeds_and_redacts(self):
        calls = {"n": 0}
        def route(m, u, b):
            calls["n"] += 1
            return (503, {"e": 1}) if calls["n"] < 3 else (200, {"ok": True})
        t = httpclient.RecordingTransport({("GET", "https://api.example/x"): route})
        h = httpclient.Http(t, retries=3, sleep=lambda s: None)
        self.assertEqual(h.json("GET", "https://api.example/x?token=SECRET", {"Authorization": "Bearer S"}), {"ok": True})
        self.assertEqual(calls["n"], 3); self.assertEqual(t.calls[0]["headers"]["Authorization"], "[secret]")

    def test_non_retryable_error_carries_no_query(self):
        t = httpclient.RecordingTransport({("GET", "https://api.example/y"): (403, {"error": "no"})})
        with self.assertRaises(httpclient.HttpError) as cm:
            httpclient.Http(t, sleep=lambda s: None).json("GET", "https://api.example/y?api_key=SECRET")
        self.assertNotIn("SECRET", str(cm.exception)); self.assertEqual(cm.exception.status, 403)

    def test_retries_are_bounded_and_form_posts_encode(self):
        t = httpclient.RecordingTransport({("GET", "https://api.example/z"): (503, {"e": 1}), ("POST", "https://api.example/token"): (200, {"access_token": "t"})})
        slept = []
        with self.assertRaises(httpclient.HttpError):
            httpclient.Http(t, retries=2, sleep=slept.append).json("GET", "https://api.example/z")
        self.assertEqual(slept, [0.5, 1.0])
        self.assertEqual(httpclient.Http(t).form("https://api.example/token", {"grant_type": "client_credentials"})["access_token"], "t")
        self.assertEqual(t.calls[-1]["body"], b"grant_type=client_credentials")

    def test_a_write_is_never_repeated_on_a_5xx(self):
        calls = {"n": 0}
        def route(m, u, b):
            calls["n"] += 1
            return (503, {"e": 1}) if calls["n"] < 2 else (200, {"id": 1})
        t = httpclient.RecordingTransport({("POST", "https://api.example/comment"): route, ("PUT", "https://api.example/doc"): route})
        with self.assertRaises(httpclient.HttpError):
            httpclient.Http(t, retries=3, sleep=lambda s: None).json("POST", "https://api.example/comment", payload={"x": 1})
        self.assertEqual(calls["n"], 1, "a POST that failed after taking effect would otherwise run twice")
        calls["n"] = 0
        self.assertEqual(httpclient.Http(t, retries=3, sleep=lambda s: None).json("PUT", "https://api.example/doc", payload={}), {"id": 1})
        self.assertEqual(calls["n"], 2, "an idempotent PUT is retried")
