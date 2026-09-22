"""Regression tests for the adapter defects found in review: secrets resolved from prompt text, redirects followed,
stdout noise hiding the answer, line breaks in credentials, the 4 KB tools/list cut, a stuck MCP write, the response
cap on MCP, content blocks that are not text, and names with a trailing newline."""
import contextlib
import json
import os
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tests.helpers import C, target, tempdir, write
from aiplayground import targets as T


@contextlib.contextmanager
def http_server(handle):
    """A loopback server; `handle(h, body)` answers, every request is recorded in the yielded log."""
    log = []

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            log.append({"path": self.path, "headers": dict(self.headers), "body": body})
            handle(self, body)

        do_GET = do_POST

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}", log
    finally:
        httpd.shutdown()
        httpd.server_close()


def answer(h, code, payload, headers=None):
    b = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    h.send_response(code)
    for k, v in (headers or {}).items():
        h.send_header(k, v)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(b)))
    h.end_headers()
    h.wfile.write(b)


def echo(h, body):
    answer(h, 200, {"output": "ok", "got": json.loads(body or b"{}")})


def mcp_http(tools=None, big=0):
    """A JSON-RPC over HTTP handler: initialize, tools/list (the given tools), tools/call echoing its arguments."""
    def handle(h, body):
        m = json.loads(body)
        if "id" not in m:
            return answer(h, 202, b"")
        if m["method"] == "initialize":
            res = {"protocolVersion": T.MCP_PROTOCOL, "capabilities": {"tools": {}}, "serverInfo": {"name": "x", "version": "1"}}
        elif m["method"] == "tools/list":
            res = {"tools": tools or []}
        else:
            res = {"content": [{"type": "text", "text": "A" * big if big else json.dumps(m["params"])}]}
        answer(h, 200, {"jsonrpc": "2.0", "id": m["id"], "result": res})
    return handle


def many_tools(n=25):
    return [{"name": f"lookup_{i}", "description": f"Looks up record type {i} by its id and returns its status.",
             "inputSchema": {"type": "object", "properties": {"id": {"type": "string", "pattern": "^R-\\d{4}$"}}, "required": ["id"]},
             "annotations": {"readOnlyHint": True}} for i in range(n)]


STDIO_SERVER = r'''
import json, sys, time
MODE = sys.argv[1]
if MODE == "dies":
    sys.stderr.write("starting\nModuleNotFoundError: No module named 'widgets'\n"); sys.stderr.flush(); sys.exit(1)
TOOLS = [{"name": "lookup_%d" % i, "description": "Looks up record type %d by its id and returns its status." % i,
          "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}}} for i in range(25)]
while True:
    line = sys.stdin.buffer.readline(100000)
    if not line:
        break
    if not line.endswith(b"\n"):
        time.sleep(10**6)                      # stops reading for good
    m = json.loads(line)
    if "id" not in m:
        continue
    if m["method"] == "initialize":
        res = {"protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "x", "version": "1"}}
    elif m["method"] == "tools/list":
        res = {"tools": TOOLS}
    elif MODE == "flood" and m["params"].get("name") == "big":
        res = {"content": [{"type": "text", "text": "A" * 3000000}]}
    elif MODE == "flood" and m["params"].get("name") == "quit":
        sys.stderr.write("fatal: the index is corrupt\n"); sys.stderr.flush(); sys.exit(3)
    else:
        res = {"content": [{"type": "text", "text": "ok"}]}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": res}) + "\n"); sys.stdout.flush()
'''


def stdio_target(d, mode, **kw):
    script = write(os.path.join(d, "server.py"), STDIO_SERVER)
    return target(kind="mcp-stdio", command=[sys.executable, script, mode], **kw)


class EnvInjection(unittest.TestCase):
    """1: `${env:NAME}` is read from the target's own template only; prompt text is sent literally."""

    def setUp(self):
        os.environ["PG_REVIEW_TESTER_KEY"] = "tester-" + "private-" + "x" * 8
        os.environ["PG_REVIEW_GW"] = "gw-" + "y" * 10

    def tearDown(self):
        del os.environ["PG_REVIEW_TESTER_KEY"], os.environ["PG_REVIEW_GW"]

    def test_prompt_context_and_system_are_sent_literally(self):
        with http_server(echo) as (base, log):
            t = target(kind="http", url=base + "/chat", headers={"Authorization": "Bearer ${env:PG_REVIEW_GW}"},
                       body={"input": "{{prompt}}", "context": "{{context}}", "system": "{{system}}", "key": "${env:PG_REVIEW_GW}"},
                       response={"text": "output"})
            r = T.open_target(t).ask("a ${env:PG_REVIEW_TESTER_KEY} b", context="doc: ${env:PG_REVIEW_TESTER_KEY}",
                                     system="sys ${env:PG_UNSET_NEVER}")
            self.assertTrue(r.ok(), r.error)
            sent = log[-1]["body"].decode()
            self.assertNotIn(os.environ["PG_REVIEW_TESTER_KEY"], sent)
            got = json.loads(sent)
            self.assertEqual(got["input"], "a ${env:PG_REVIEW_TESTER_KEY} b")
            self.assertEqual(got["context"], "doc: ${env:PG_REVIEW_TESTER_KEY}")
            self.assertEqual(got["system"], "sys ${env:PG_UNSET_NEVER}")
            self.assertEqual(got["key"], os.environ["PG_REVIEW_GW"])                  # the template's own secret still resolves
            self.assertEqual(log[-1]["headers"]["Authorization"], "Bearer " + os.environ["PG_REVIEW_GW"])

    def test_a_prompt_that_mentions_the_syntax_is_not_an_error(self):
        with http_server(echo) as (base, _log):
            r = T.open_target(target(kind="http", preset="simple-json", url=base + "/chat")).ask("How do I write ${env:SOME_UNSET_VAR}?")
            self.assertIsNone(r.error)

    def test_mcp_http_call_arguments_are_sent_literally(self):
        with http_server(mcp_http()) as (base, log):
            a = T.open_target(target(kind="mcp-http", url=base + "/mcp", headers={"Authorization": "Bearer ${env:PG_REVIEW_GW}"}))
            r = a.call_tool("echo", {"text": "${env:PG_REVIEW_TESTER_KEY}"})
            self.assertTrue(r.ok(), r.error)
            self.assertIn("${env:PG_REVIEW_TESTER_KEY}", log[-1]["body"].decode())
            self.assertNotIn(os.environ["PG_REVIEW_TESTER_KEY"], log[-1]["body"].decode())
            self.assertEqual(log[-1]["headers"]["Authorization"], "Bearer " + os.environ["PG_REVIEW_GW"])


class Redirects(unittest.TestCase):
    """2: a 3xx is reported, never followed (it would carry the Authorization header to an unchecked host)."""

    def setUp(self):
        os.environ["PG_REVIEW_GW"] = "gw-" + "z" * 10

    def tearDown(self):
        del os.environ["PG_REVIEW_GW"]

    def test_http_and_mcp_http_do_not_follow(self):
        with http_server(echo) as (other, other_log):
            def redirect(h, body):
                h.send_response(302)
                h.send_header("Location", other.replace("127.0.0.1", "localhost") + "/elsewhere")
                h.send_header("Content-Length", "0")
                h.end_headers()
            with http_server(redirect) as (base, log):
                hdr = {"Authorization": "Bearer ${env:PG_REVIEW_GW}"}
                r = T.open_target(target(kind="http", preset="simple-json", url=base + "/chat", headers=hdr)).ask("hi")
                self.assertEqual(r.status, 302)
                self.assertEqual(r.error, "redirected to localhost: the playground does not follow redirects")
                self.assertEqual(r.text, "")
                m = T.open_target(target(kind="mcp-http", url=base + "/mcp", headers=hdr)).call_tool("x", {})
                self.assertEqual(m.status, 302)
                self.assertIn("does not follow redirects", m.error)
                self.assertEqual(len(log), 2)
            self.assertEqual(other_log, [])


class ShimStdout(unittest.TestCase):
    """3: what reaches fd 1 directly (os.write, a child process) cannot hide the answer."""

    def test_fd1_writes_and_child_processes_go_to_stderr(self):
        with tempdir() as d:
            write(os.path.join(d, "agent.py"),
                  "import os, subprocess, sys\n"
                  "def answer(prompt, context=''):\n"
                  "    os.write(1, b'raw fd write\\n')\n"
                  "    subprocess.run([sys.executable, '-c', 'print(\"child noise\")'])\n"
                  "    print('print noise')\n"
                  "    return {'output': 'done', 'tool_calls': [{'name': 'delete_records', 'arguments': {'scope': 'all'}}]}\n")
            r = T.open_target(target(kind="python", path=d, callable="agent:answer")).ask("x", context="c")
            self.assertTrue(r.ok(), r.error)
            self.assertEqual(r.text, "done")
            self.assertEqual(r.tool_calls, [{"name": "delete_records", "arguments": {"scope": "all"}}])

    def test_a_command_answer_after_noise_is_read_from_the_last_line(self):
        with tempdir() as d:
            noisy = write(os.path.join(d, "n.py"), "import json\nprint('log: starting')\nprint(json.dumps({'output': 'the answer', 'tool_calls': [{'name': 't', 'arguments': {}}]}))\n")
            r = T.open_target(target(kind="command", command=[sys.executable, noisy])).ask("x")
            self.assertEqual((r.text, r.tool_calls), ("the answer", [{"name": "t", "arguments": {}}]))
            pretty = write(os.path.join(d, "p.py"), "import json\nprint(json.dumps({'output': 'pretty'}, indent=2))\n")
            self.assertEqual(T.open_target(target(kind="command", command=[sys.executable, pretty])).ask("x").text, "pretty")
            text = write(os.path.join(d, "t.py"), "print('line one')\nprint('42')\n")
            self.assertEqual(T.open_target(target(kind="command", command=[sys.executable, text])).ask("x").text, "line one\n42")


class LineBreakInCredential(unittest.TestCase):
    """4: a credential with CR/LF is refused by name; no error carries a header value."""

    def setUp(self):
        self.value = "gw-live-" + "9" * 9
        os.environ["PG_REVIEW_CRLF"] = self.value + "\r"

    def tearDown(self):
        del os.environ["PG_REVIEW_CRLF"]

    def test_resolve_secrets_names_the_variable_not_the_value(self):
        with self.assertRaises(C.ConfigError) as cm:
            C.resolve_secrets({"Authorization": "Bearer ${env:PG_REVIEW_CRLF}"})
        self.assertIn("PG_REVIEW_CRLF contains a line break", str(cm.exception))
        self.assertNotIn(self.value, str(cm.exception))
        with self.assertRaises(C.ConfigError):
            C.resolve_secrets("${env:X}", {"X": "a\nb"})

    def test_adapters_answer_with_an_error_reply(self):
        hdr = {"Authorization": "Bearer ${env:PG_REVIEW_CRLF}"}
        r = T.open_target(target(kind="http", preset="openai-chat", url="http://127.0.0.1:9/v1", headers=hdr)).ask("hi")
        self.assertIn("PG_REVIEW_CRLF contains a line break", r.error)
        self.assertNotIn(self.value, r.error)
        m = T.open_target(target(kind="mcp-http", url="http://127.0.0.1:9/mcp", headers=hdr)).call_tool("x", {})
        self.assertIn("PG_REVIEW_CRLF contains a line break", m.error)

    def test_an_invalid_literal_header_does_not_print_its_value(self):
        with http_server(echo) as (base, log):
            literal = {"X-Key": self.value + "\r\nX-Injected: 1"}
            r = T.open_target(target(kind="http", preset="simple-json", url=base + "/chat", headers=literal)).ask("hi")
            self.assertIsNotNone(r.error)
            self.assertNotIn(self.value, r.error)
            m = T.open_target(target(kind="mcp-http", url=base + "/mcp", headers=literal)).call_tool("x", {})
            self.assertIsNotNone(m.error)
            self.assertNotIn(self.value, m.error)
            self.assertEqual(log, [])


class McpBigToolList(unittest.TestCase):
    """5: tools/list is read from the parsed answer, not from Reply.raw (cut to 4 KB)."""

    def test_stdio(self):
        with tempdir() as d:
            a = T.open_target(stdio_target(d, "plain"))
            try:
                tools = a.tools()
                self.assertEqual(len(tools), 25)
                r = a.raw("tools/list", {})
                self.assertGreater(len(json.dumps(r.result)), 4096)
                self.assertNotIn("result", r.to_json())
            finally:
                a.close()

    def test_http(self):
        with http_server(mcp_http(many_tools())) as (base, _log):
            self.assertEqual(len(T.open_target(target(kind="mcp-http", url=base + "/mcp")).tools()), 25)


class McpStuckWrite(unittest.TestCase):
    """6: a server that stops reading cannot block a call past its timeout; it is killed and started again."""

    def test_write_is_bounded_by_the_timeout(self):
        with tempdir() as d:
            a = T.open_target(stdio_target(d, "plain", timeout_s=1))
            try:
                self.assertEqual(len(a.tools()), 25)
                start = time.monotonic()
                r = a.call_tool("lookup_1", {"id": "A" * 1_000_000})
                self.assertLess(time.monotonic() - start, 6)
                self.assertEqual(r.error, "no answer within 1 s")
                self.assertEqual(a.call_tool("lookup_1", {"id": "R-0001"}).text, "ok")
                self.assertEqual(a.restarts, 1)
            finally:
                a.close()


class McpResponseCap(unittest.TestCase):
    """7: max_response_bytes holds for MCP answers too."""

    def test_stdio(self):
        with tempdir() as d:
            a = T.open_target(stdio_target(d, "flood", max_response_bytes=10_000))
            try:
                r = a.call_tool("big", {})
                self.assertEqual(r.error, "the answer is larger than 10000 bytes")
                self.assertEqual(r.text, "")
                self.assertEqual(a.call_tool("small", {}).text, "ok")   # the rest of the long line was discarded
                self.assertEqual(a.restarts, 0)
            finally:
                a.close()

    def test_http(self):
        with http_server(mcp_http(big=50_000)) as (base, _log):
            r = T.open_target(target(kind="mcp-http", url=base + "/mcp", max_response_bytes=10_000)).call_tool("big", {})
            self.assertEqual(r.error, "the answer is larger than 10000 bytes")


class ContentBlocks(unittest.TestCase):
    """8: a block whose text is not a string is shown, not a crash; None is skipped."""

    def test_as_text(self):
        self.assertEqual(T.as_text([{"type": "text", "text": None}, {"text": 5}, "x", None, {"type": "image"}, {"text": [1]}]), "5x[1]")
        self.assertEqual(T.as_text([{"type": "text", "text": None}]), "")

    def test_a_command_answering_with_null_text(self):
        with tempdir() as d:
            s = write(os.path.join(d, "b.py"), "import json, sys\nsys.stdin.readline()\nprint(json.dumps({'output': [{'type': 'text', 'text': None}, {'type': 'text', 'text': 7}]}))\n")
            r = T.open_target(target(kind="command", command=[sys.executable, s])).ask("x")
            self.assertEqual((r.error, r.text), (None, "7"))


class NamesAndStderr(unittest.TestCase):
    """9: names cannot end in a newline; a stdio server's last stderr line explains why it exited."""

    def test_trailing_newline_is_refused(self):
        with self.assertRaises(C.ConfigError):
            target(name="demo\n", kind="demo", demo="safe")
        with self.assertRaises(C.ConfigError):
            target(kind="command", command=["x"], env=["PG_X\n"])
        self.assertIsNone(C.NAME.match("demo\n"))
        self.assertIsNone(C.NAME.match("demo/../x"))

    def test_initialize_failure_shows_the_last_stderr_line(self):
        with tempdir() as d:
            a = T.open_target(stdio_target(d, "dies"))
            try:
                with self.assertRaises(RuntimeError) as cm:
                    a.tools()
                self.assertIn("initialize failed", str(cm.exception))
                self.assertIn("ModuleNotFoundError: No module named 'widgets'", str(cm.exception))
            finally:
                a.close()

    def test_exit_mid_run_shows_the_last_stderr_line(self):
        with tempdir() as d:
            a = T.open_target(stdio_target(d, "flood"))
            try:
                r = a.call_tool("quit", {})
                self.assertIn("the server has exited", r.error)
                self.assertIn("fatal: the index is corrupt", r.error)
            finally:
                a.close()


if __name__ == "__main__":
    unittest.main()
