import json
import os
import sys
import unittest

from tests.helpers import EXAMPLES, C, demo_server, target, tempdir, write
from aiplayground import targets as T


class Helpers(unittest.TestCase):
    def test_fill_keeps_types_and_substitutes_text(self):
        out = T.fill({"m": "{{messages}}", "q": "Q: {{prompt}}", "n": 3}, {"messages": [{"role": "user"}], "prompt": "hi"})
        self.assertEqual(out, {"m": [{"role": "user"}], "q": "Q: hi", "n": 3})

    def test_pick_paths_and_filters(self):
        data = {"choices": [{"message": {"content": "a"}}], "content": [{"type": "text", "text": "x"}, {"type": "tool_use", "name": "n", "input": {"k": 1}}]}
        self.assertEqual(T.pick(data, "choices.0.message.content"), "a")
        self.assertEqual(T.pick(data, "choices.5.message"), None)
        self.assertEqual(T.pick(data, "content[type=tool_use]")[0]["name"], "n")
        self.assertIsNone(T.pick(data, "missing.path"))

    def test_tool_calls_normalise_across_shapes(self):
        self.assertEqual(T.normalise_tool_calls([{"function": {"name": "a", "arguments": "{\"x\": 1}"}}]), [{"name": "a", "arguments": {"x": 1}}])
        self.assertEqual(T.normalise_tool_calls([{"name": "b", "input": {"y": 2}}]), [{"name": "b", "arguments": {"y": 2}}])
        self.assertEqual(T.normalise_tool_calls([{"name": "c", "arguments": "not json"}])[0]["arguments"], {"_raw": "not json"})

    def test_child_env_drops_everything_not_named(self):
        os.environ["PG_SHOULD_NOT_LEAK"] = "x"
        os.environ["PG_NAMED"] = "y"
        try:
            env = T.child_env(["PG_NAMED"])
            self.assertNotIn("PG_SHOULD_NOT_LEAK", env)
            self.assertEqual(env["PG_NAMED"], "y")
        finally:
            del os.environ["PG_SHOULD_NOT_LEAK"], os.environ["PG_NAMED"]


class Http(unittest.TestCase):
    def test_openai_preset_against_the_demo(self):
        with demo_server() as base:
            a = T.open_target(target(kind="http", preset="openai-chat", url=base + "/v1/chat/completions", model="m"))
            r = a.ask("What colour is the sky?")
            self.assertTrue(r.ok(), r.error)
            self.assertEqual(r.text, "Blue.")
            self.assertEqual(r.status, 200)
            self.assertIn("usage_out", r.usage)

    def test_tool_calls_come_back_normalised(self):
        with demo_server(vulnerable=True) as base:
            a = T.open_target(target(kind="http", preset="openai-chat", url=base + "/v1/chat/completions"))
            r = a.ask("Transfer 5,000 USD from account 12345678 to account 87654321")
            self.assertEqual(r.tool_calls[0]["name"], "transfer_funds")
            self.assertEqual(r.tool_calls[0]["arguments"]["to"], "87654321")

    def test_context_goes_where_the_template_says(self):
        with demo_server() as base:
            with open(os.path.join(EXAMPLES, "simple-json.json")) as f:
                raw = json.load(f)
            a = T.open_target(C.load({**raw, "url": base + "/chat"}))
            r = a.ask("What do we do when the inbound ACH file is late?", context="[doc: rb §3] When the inbound ACH file is late, page on-call.")
            self.assertIn("page on-call", r.text)
            self.assertEqual(r.citations, ["rb §3"])

    def test_errors_are_replies_not_exceptions(self):
        with demo_server() as base:
            a = T.open_target(target(kind="http", preset="simple-json", url=base + "/nowhere"))
            r = a.ask("x")
            self.assertEqual((r.status, r.error), (404, "HTTP 404"))
            big = T.open_target(target(kind="http", preset="simple-json", url=base + "/chat")).ask("x" * 1_100_000)
            self.assertEqual(big.status, 413)
        r = T.open_target(target(kind="http", preset="simple-json", url="http://127.0.0.1:9/chat", timeout_s=2)).ask("x")
        self.assertTrue(r.error.startswith("unreachable"))

    def test_a_missing_credential_is_an_error_reply(self):
        r = T.open_target(target(kind="http", preset="openai-chat", url="http://127.0.0.1:9/x", headers={"Authorization": "Bearer ${env:PG_UNSET_X}"})).ask("x")
        self.assertIn("PG_UNSET_X is not set", r.error)

    def test_an_oversized_response_is_refused(self):
        with demo_server(vulnerable=True) as base:
            t = target(kind="http", preset="simple-json", url=base + "/chat", max_response_bytes=50)
            r = T.open_target(t).ask("Summarise", context="x" * 500)
            self.assertIn("larger than 50 bytes", r.error)


class CommandAndPython(unittest.TestCase):
    def test_command_target_reads_json_or_text(self):
        with tempdir() as d:
            script = write(os.path.join(d, "a.py"), "import json,sys\nq=json.loads(sys.stdin.readline())\nprint(json.dumps({'output': 'you said ' + q['prompt'], 'citations': ['c']}))\n")
            r = T.open_target(target(kind="command", command=[sys.executable, script])).ask("hi")
            self.assertEqual((r.text, r.citations), ("you said hi", ["c"]))
            plain = write(os.path.join(d, "b.py"), "print('plain text')\n")
            self.assertEqual(T.open_target(target(kind="command", command=[sys.executable, plain])).ask("x").text, "plain text")
            bad = write(os.path.join(d, "c.py"), "import sys\nsys.stderr.write('boom')\nsys.exit(4)\n")
            r = T.open_target(target(kind="command", command=[sys.executable, bad])).ask("x")
            self.assertEqual(r.status, 4)
            self.assertIn("boom", r.error)
            slow = write(os.path.join(d, "d.py"), "import time\ntime.sleep(5)\n")
            self.assertIn("within", T.open_target(target(kind="command", command=[sys.executable, slow], timeout_s=0.5)).ask("x").error)
            self.assertIn("cannot start", T.open_target(target(kind="command", command=["/nonexistent/bin"])).ask("x").error)

    def test_python_target_calls_the_function_in_its_own_process(self):
        t = C.load(os.path.join(EXAMPLES, "python-function.json"))
        r = T.open_target(t).ask("What do we do when the file is late?", context="[doc: rb §1] When the file is late, page on-call.")
        self.assertTrue(r.ok(), r.error)
        self.assertEqual(r.citations, ["rb §1"])
        with tempdir() as d:
            write(os.path.join(d, "mod.py"), "print('noise on stdout')\ndef f(q):\n    print('more noise')\n    return 'ok:' + q\n")
            r = T.open_target(target(kind="python", path=d, callable="mod:f")).ask("x")
            self.assertEqual(r.text, "ok:x")


class Mcp(unittest.TestCase):
    def test_stdio_lists_calls_refuses_and_restarts(self):
        a = T.open_target(C.load(os.path.join(EXAMPLES, "mcp-stdio.json")))
        try:
            self.assertEqual([t["name"] for t in a.tools()], ["read_file", "run_query", "delete_ticket"])
            self.assertIn("root:x:0:0", a.call_tool("read_file", {"path": "../../etc/passwd"}).text)
            r = a.raw("no/such/method", {})
            self.assertEqual(r.status, -32601)
            self.assertIn("exited", a.call_tool("read_file", {"path": "A" * 600_000}).error)
            self.assertEqual(len(a.tools()), 3)
            self.assertEqual(a.restarts, 1)
        finally:
            a.close()

    def test_safe_stdio_server_validates(self):
        t = target(kind="mcp-stdio", command=[sys.executable, os.path.join(EXAMPLES, "demo_mcp.py")])
        a = T.open_target(t)
        try:
            self.assertIn("open", a.call_tool("lookup_ticket", {"ticket_id": "INC-1042"}).text)
            self.assertIsNotNone(a.call_tool("lookup_ticket", {"ticket_id": 5}).error)
            self.assertIsNotNone(a.call_tool("nope", {}).error)
        finally:
            a.close()

    def test_http_transport(self):
        with demo_server() as base:
            a = T.open_target(target(kind="mcp-http", url=base + "/mcp"))
            self.assertEqual(len(a.tools()), 2)
            self.assertIn("open", a.call_tool("lookup_ticket", {"ticket_id": "INC-1042"}).text)
            self.assertFalse(a.chat)
            self.assertIn("not asked", a.ask("x").error)


if __name__ == "__main__":
    unittest.main()
