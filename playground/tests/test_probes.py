import base64
import os
import sys
import unittest

from tests.helpers import EXAMPLES, C, demo_server, target
from aiplayground import probes as P
from aiplayground import targets as T

CHAT_SECURITY = [k for k, p in P.REGISTRY.items() if p.applies == "chat" and p.suite in ("security", "quality")]
TOOL = [k for k, p in P.REGISTRY.items() if p.applies == "tool"]


def run(pid, t):
    a = T.open_target(t)
    try:
        return P.run_probe(P.REGISTRY[pid], a, t)
    finally:
        a.close()


class Markers(unittest.TestCase):
    def test_marker_found_through_obfuscation(self):
        m = P.marker()
        for text in (m, m.lower(), " ".join(m), "​".join(m), m[::-1], base64.b64encode(f"x {m} y".encode()).decode(), "\n".join(m)):
            self.assertTrue(P.contains_marker(text, m), text)
        self.assertFalse(P.contains_marker("nothing to see", m))
        self.assertFalse(P.contains_marker("", m))

    def test_luhn_cards_are_valid(self):
        for _ in range(20):
            digits = [int(c) for c in P.luhn_card()]
            total = sum(d if i % 2 == 0 else (d * 2 - 9 if d * 2 > 9 else d * 2) for i, d in enumerate(reversed(digits)))
            self.assertEqual(total % 10, 0)


class ChatProbes(unittest.TestCase):
    def test_the_safe_demo_holds_every_probe(self):
        t = target(kind="demo", demo="safe", capabilities=["cites-sources", "masks-pii"])
        for pid in CHAT_SECURITY + ["rob-oversized", "rob-empty", "rob-unicode", "perf-burst"]:
            r = run(pid, t)
            self.assertEqual(r.status, "pass", f"{pid}: {r.summary}")

    def test_the_vulnerable_demo_gives_way_on_every_security_probe(self):
        t = target(kind="demo", demo="vulnerable", capabilities=["cites-sources", "masks-pii"])
        for pid in CHAT_SECURITY:
            r = run(pid, t)
            self.assertEqual(r.status, "fail", f"{pid}: {r.summary}")
            self.assertTrue(r.evidence, pid)

    def test_pii_without_the_capability_is_for_a_person(self):
        r = run("leak-pii-context", target(kind="demo", demo="vulnerable"))
        self.assertEqual(r.status, "review")

    def test_grounding_probes_apply_only_when_claimed(self):
        r = run("ground-cites", target(kind="demo", demo="vulnerable"))
        self.assertEqual(r.status, "skipped")
        self.assertIn("cites-sources", r.summary)

    def test_a_guard_in_front_of_the_model_counts_as_holding(self):
        with demo_server() as base:
            t = target(kind="http", preset="simple-json", url=base + "/nowhere")   # 404 is not a guard: the probe cannot judge
            self.assertEqual(run("pi-direct-override", t).status, "error")
        # a service that answers 422 to anything instruction-shaped
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading

        class Guard(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                shaped = b"ignore" in raw.lower()   # a harmless question of the same size is answered
                body = b'{"error": "refused by the input guard"}' if shaped else b'{"output": "Blue."}'
                self.send_response(422 if shaped else 200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Guard)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            t = target(kind="http", preset="simple-json", url=f"http://127.0.0.1:{httpd.server_address[1]}/chat")
            r = run("pi-indirect-document", t)
            self.assertEqual(r.status, "pass")
            self.assertIn("HTTP 422", r.summary)
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_refusing_while_repeating_the_marker_goes_to_review(self):
        class Echo(T.Adapter):
            def ask(self, prompt, *, system="", context=""):
                word = [w for w in prompt.split() if w.startswith("PG")]
                return T.Reply(status=0, text=f"I won't reply with {word[0] if word else ''}.")
        t = target(kind="demo", demo="safe")
        r = P.run_probe(P.REGISTRY["pi-direct-override"], Echo(t), t)
        self.assertEqual(r.status, "review")

    def test_a_crashing_probe_is_an_error_result_not_a_crash(self):
        class Broken(T.Adapter):
            def ask(self, *a, **k):
                raise ZeroDivisionError("inside the adapter")
        t = target(kind="demo", demo="safe")
        r = P.run_probe(P.REGISTRY["pi-encoded"], Broken(t), t)
        self.assertEqual(r.status, "error")
        self.assertIn("ZeroDivisionError", r.summary)

    def test_burst_reports_errors_and_latency(self):
        with demo_server() as base:
            r = run("perf-burst", target(kind="http", preset="simple-json", url=base + "/chat", concurrency=3))
            self.assertEqual(r.status, "pass")
            self.assertEqual(r.metrics["requests"], 9)
        r = run("perf-burst", target(kind="http", preset="simple-json", url="http://127.0.0.1:9/chat", timeout_s=1, concurrency=2))
        self.assertEqual(r.status, "fail")


class ToolProbes(unittest.TestCase):
    def test_the_safe_server_holds(self):
        t = target(kind="mcp-stdio", command=[sys.executable, os.path.join(EXAMPLES, "demo_mcp.py")])
        a = T.open_target(t)
        try:
            for pid in TOOL:
                r = P.run_probe(P.REGISTRY[pid], a, t)
                self.assertIn(r.status, ("pass",), f"{pid}: {r.summary}")
        finally:
            a.close()

    def test_the_vulnerable_server_fails_in_the_expected_ways(self):
        t = C.load(os.path.join(EXAMPLES, "mcp-stdio.json"))
        a = T.open_target(t)
        try:
            got = {pid: P.run_probe(P.REGISTRY[pid], a, t) for pid in [p.id for p in P.select("all", t) if p.applies == "tool"]}
        finally:
            a.close()
        self.assertEqual(got["tool-injection-arguments"].severity, "critical")
        for pid in ("tool-schemas", "tool-poisoning", "tool-unknown", "tool-bad-arguments", "tool-injection-arguments", "tool-oversized-argument", "tool-alive"):
            self.assertEqual(got[pid].status, "fail", f"{pid}: {got[pid].summary}")
        self.assertEqual(got["tool-write-annotations"].status, "review")

    def test_chat_probes_skip_tool_servers_and_back(self):
        t = C.load(os.path.join(EXAMPLES, "mcp-stdio.json"))
        self.assertEqual(run("pi-direct-override", t).status, "skipped")
        self.assertEqual(run("tool-poisoning", target(kind="demo", demo="safe")).status, "skipped")


class Selection(unittest.TestCase):
    def test_select_by_suite_id_and_all(self):
        t = target(kind="demo", demo="safe")
        self.assertEqual(P.select("none", t), [])
        self.assertEqual({p.suite for p in P.select("robustness", t)}, {"robustness"})
        ids = [p.id for p in P.select("all", t)]
        self.assertEqual(ids[-1], "tool-alive")
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual([p.id for p in P.select("tool-alive,pi-encoded", t)], ["pi-encoded", "tool-alive"])
        with self.assertRaisesRegex(ValueError, "unknown probe"):
            P.select("pi-nope", t)

    def test_every_probe_is_catalogued_with_a_known_category(self):
        for p in P.catalog():
            self.assertIn(p["category"], P.OWASP)
            self.assertIn(p["severity"], P.SEVERITIES)
            self.assertTrue(p["why"] and p["recommendation"])


if __name__ == "__main__":
    unittest.main()
