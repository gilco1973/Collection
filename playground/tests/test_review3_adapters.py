"""Regression tests for the third review, adapter and contract-check side: a plain-text answer followed by a JSON trace
line, a credential cut before it is scrubbed, reports written inside the component, the proxy credential in the
command output, and the taxonomy outside a checkout. Every credential here is built at run time."""
import http.server
import json
import os
import secrets
import shutil
import sys
import threading
import unittest
import uuid
from unittest import mock

from tests.helpers import EXAMPLES, target, tempdir, write
from aiplayground import component as K
from aiplayground import runner
from aiplayground import targets as T

SAMPLE = os.path.join(EXAMPLES, "runbook-answerer")
TRACE = "print(json.dumps({'step': 'final', 'model': 'workhorse', 'tool_calls': %s}))\n"


def command(d, name, body, **kw):
    return T.open_target(target(kind="command", command=[sys.executable, write(os.path.join(d, name), "import json, os, sys\n" + body)], **kw))


def pieces(value: str, n: int = 8) -> list:
    """Every piece of `value` of n characters: none of them may be left in scrubbed text."""
    return [value[i:i + n] for i in range(len(value) - n + 1)]


def sample_copy(parent, dirname="runbook-answerer"):
    root = os.path.join(parent, dirname)
    shutil.copytree(SAMPLE, root, ignore=shutil.ignore_patterns("__pycache__"))
    return root


class PlainTextBeforeATraceLine(unittest.TestCase):
    """1: an object carrying only `tool_calls` is a trace, not the answer; the plain-text lines stay the text."""

    def test_the_plain_text_answer_survives_a_trace_line(self):
        marker = "PG" + secrets.token_hex(4).upper()
        with tempdir() as d:
            r = command(d, "a.py", f"print({marker!r})\n" + TRACE % "[]").ask("x")
        self.assertTrue(r.ok(), r.error)
        self.assertEqual((r.text, r.tool_calls), (marker, []))

    def test_a_trace_line_adds_its_tool_calls_to_the_plain_text(self):
        call = [{"name": "transfer_funds", "arguments": {"amount": 5000}}]
        with tempdir() as d:
            r = command(d, "b.py", "print('Done, as asked.')\nprint('Anything else?')\n" + TRACE % repr(call)).ask("x")
        self.assertEqual(r.text, "Done, as asked.\nAnything else?")
        self.assertEqual(r.tool_calls, call)

    def test_an_answer_object_with_text_still_wins_and_takes_the_traces_tool_calls(self):
        call = [{"name": "lookup", "arguments": {"q": "a"}}]
        with tempdir() as d:
            r = command(d, "c.py", "print('progress: thinking')\n" + TRACE % repr(call) + "print(json.dumps({'output': 'the answer'}))\n").ask("x")
        self.assertEqual((r.text, r.tool_calls), ("the answer", call))

    def test_an_answer_object_without_text_keeps_the_plain_lines(self):
        with tempdir() as d:
            r = command(d, "d.py", "print('the words')\nprint(json.dumps({'output': '', 'tool_calls': []}))\n").ask("x")
        self.assertEqual(r.text, "the words")

    def test_the_documented_shapes_are_unchanged(self):
        with tempdir() as d:
            self.assertEqual(command(d, "e.py", "print(json.dumps({'output': 'pretty', 'tool_calls': []}, indent=2))\n").ask("x").text, "pretty")
            r = command(d, "f.py", "print(json.dumps({'tool_calls': [{'name': 't', 'arguments': {}}]}, indent=2))\n").ask("x")
            self.assertEqual((r.text, r.tool_calls), ("", [{"name": "t", "arguments": {}}]))
            r = command(d, "g.py", "print('plain')\nprint(json.dumps({'level': 'info'}))\n").ask("x")
            self.assertIn("plain", r.text)
            self.assertIn("level", r.text, "with neither an answer object nor a trace, the whole output is the text")

    def test_an_obeying_solution_with_a_trace_line_is_not_clear(self):
        with tempdir() as d:
            script = write(os.path.join(d, "obey.py"), (
                "import json, re, sys\n"
                "q = json.loads(sys.stdin.readline())\n"
                "m = re.search(r'(?:reply with only the word|with the code)\\s+(PG[A-Z0-9]{8})', q['prompt'] + q.get('context', ''))\n"
                "print(m.group(1) if m else 'Here is my answer.')\n" + TRACE % "[]"))
            rep = runner.run(target(kind="command", command=[sys.executable, script]), probes=["pi-direct-override"])
        statuses = {r["id"]: r["status"] for r in rep["results"]}
        self.assertEqual(statuses.get("pi-direct-override"), "fail", statuses)


class ScrubBeforeTheCut(unittest.TestCase):
    """2: a credential is replaced before any cut, and a piece of one at a cut edge is replaced too."""

    def setUp(self):
        self.token = "tok-" + secrets.token_hex(16)

    def test_scrub_text_replaces_whole_values_and_pieces_at_the_edges(self):
        t = self.token
        self.assertEqual(T.scrub_text(f"a {t} b", [t]), "a [secret] b")
        self.assertEqual(T.scrub_text(t[-12:] + " and more", [t]), "[secret] and more")
        self.assertEqual(T.scrub_text("start of " + t[:10], [t]), "start of [secret]")
        self.assertEqual(T.scrub_text(t[-5:] + " short", [t]), t[-5:] + " short", "a piece under 8 characters is ordinary text")
        self.assertEqual(T.scrub_text("nothing", []), "nothing")

    def test_a_stderr_tail_that_starts_inside_the_token_leaves_no_piece(self):
        with tempdir() as d, mock.patch.dict(os.environ, {"PG_R3_TOKEN": self.token}):
            body = "sys.stdin.readline()\nsys.stderr.write('auth failed with token ' + os.environ['PG_R3_TOKEN'] + ';' + 'z' * 285 + '\\n')\nsys.exit(1)\n"
            r = command(d, "leak.py", body, env=["PG_R3_TOKEN"]).ask("x")
        self.assertIsNotNone(r.error)
        self.assertTrue(r.error.startswith("exit 1: "), r.error)
        for p in pieces(self.token):
            self.assertNotIn(p, r.error)

    def test_a_http_error_body_cut_at_4_kb_leaves_no_piece(self):
        token = self.token

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                body = ("e" * 4080 + token + " trailing").encode()
                self.send_response(401)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        httpd = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            with mock.patch.dict(os.environ, {"PG_R3_TOKEN": token}):
                t = target(kind="http", preset="simple-json", url=f"http://127.0.0.1:{httpd.server_address[1]}/chat",
                           headers={"Authorization": "Bearer ${env:PG_R3_TOKEN}"})
                r = T.open_target(t).ask("hello")
        finally:
            httpd.shutdown()
            httpd.server_close()
        self.assertEqual(r.status, 401)
        for p in pieces(token):
            self.assertNotIn(p, r.text)
            self.assertNotIn(p, r.raw)

    def test_a_json_rpc_error_message_is_scrubbed_before_its_cut(self):
        msg = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "m" * 290 + self.token}}
        r = T.tool_reply(msg, 1, [self.token])
        for p in pieces(self.token):
            self.assertNotIn(p, r.error)
            self.assertNotIn(p, r.raw)

    def test_the_adapter_reads_the_targets_secrets_once_at_open(self):
        with mock.patch.dict(os.environ, {"PG_R3_TOKEN": self.token}):
            a = T.open_target(target(kind="command", command=["true"], env=["PG_R3_TOKEN"]))
        self.assertEqual(a.secrets, [self.token])


def report_file(path, extra=None):
    rep = {"kind": "ai-playground-report", "id": os.path.basename(path)[:-5], "results": []}
    rep.update(extra or {})
    return write(path, rep)


class ReportsInsideTheComponent(unittest.TestCase):
    """3: the playground's own reports (and an excluded --out directory) are not the component's files."""

    def setUp(self):
        self.key = "sk-proj-" + secrets.token_hex(16)     # secret-shaped, built at run time
        self.guid = str(uuid.uuid4())

    def leaky(self, **extra):
        return {"evidence": f"token = {self.key}", "tenant": self.guid, **extra}

    def test_reports_and_their_renderings_are_not_scanned(self):
        with tempdir() as d:
            root = sample_copy(d)
            report_file(os.path.join(root, "reports", "pg-0123456789abcdef.json"), self.leaky())
            write(os.path.join(root, "reports", "pg-0123456789abcdef.md"), f'api_key = "{self.key}"\n{self.guid}\n')
            write(os.path.join(root, "reports", "pg-0123456789abcdef.html"), f"<p>{self.key}</p>\n")
            write(os.path.join(root, "playground-reports", "notes.txt"), f"password: {self.key}\n")
            got = {r.id: r for r in K.check(root, run=False)}
        self.assertEqual(got["contract/secrets"].status, "pass", got["contract/secrets"].summary)
        self.assertEqual(got["contract/real-ids"].status, "pass", got["contract/real-ids"].summary)

    def test_a_json_that_is_not_a_report_is_still_scanned(self):
        with tempdir() as d:
            root = sample_copy(d)
            write(os.path.join(root, "config.json"), {"kind": "settings", "api_key": self.key})
            write(os.path.join(root, "pg-lookalike.md"), f'api_key = "{self.key}"\n')   # no report JSON beside it
            got = {r.id: r for r in K.check(root, run=False)}
        self.assertEqual(got["contract/secrets"].status, "fail")
        self.assertIn("config.json", got["contract/secrets"].summary)
        self.assertIn("pg-lookalike.md", str(got["contract/secrets"].evidence))

    def test_an_excluded_directory_is_not_scanned_and_the_component_itself_cannot_be_excluded(self):
        with tempdir() as d:
            root = sample_copy(d)
            write(os.path.join(root, "out", "anything.txt"), f"password: {self.key}\n")
            self.assertEqual({r.id: r for r in K.check(root, run=False)}["contract/secrets"].status, "fail")
            got = {r.id: r for r in K.check(root, run=False, exclude=[os.path.join(root, "out")])}
            self.assertEqual(got["contract/secrets"].status, "pass", got["contract/secrets"].summary)
            got = {r.id: r for r in K.check(root, run=False, exclude=[root, d])}
            self.assertEqual(got["contract/secrets"].status, "fail", "excluding the component (or its parent) excludes nothing")

    def test_the_throwaway_copy_leaves_the_reports_and_excluded_paths_out(self):
        with tempdir() as d:
            root = sample_copy(d)
            report_file(os.path.join(root, "pg-0123456789abcdef.json"))
            write(os.path.join(root, "pg-0123456789abcdef.md"), "# report\n")
            write(os.path.join(root, "playground-reports", "x.txt"), "x\n")
            write(os.path.join(root, "out", "y.txt"), "y\n")
            write(os.path.join(root, "data.json"), {"kind": "data"})
            ex = K.Exclusions(root, [os.path.join(root, "out")])
            code, _, tail = K.run_in_copy(root, "ls -a; ls ..", 30, ex)
        self.assertEqual(code, 0, tail)
        names = tail.split()
        self.assertIn("data.json", names)
        for n in ("pg-0123456789abcdef.json", "pg-0123456789abcdef.md", "playground-reports", "out"):
            self.assertNotIn(n, names)

    def test_a_second_run_with_the_reports_inside_is_as_green_as_the_first(self):
        with tempdir() as d:
            root = sample_copy(d)
            first = {r.id: r.status for r in K.check(root, run=False)}
            report_file(os.path.join(root, "playground-reports", "pg-0123456789abcdef.json"), self.leaky())
            report_file(os.path.join(root, "reports", "pg-fedcba9876543210.json"), self.leaky())
            second = {r.id: r.status for r in K.check(root, run=False)}
        self.assertEqual(first, second)


class ProxyCredentialInTheOutput(unittest.TestCase):
    """4: the proxy credential handed to the candidate's commands never reaches the evidence."""

    def setUp(self):
        self.password = "Pw" + secrets.token_hex(8)
        self.proxy = f"http://ada:{self.password}@127.0.0.1:9"

    def env(self):
        return {"HTTPS_PROXY": self.proxy, "https_proxy": self.proxy}

    def test_the_value_its_userinfo_and_its_password_are_scrubbed_from_the_tail(self):
        with tempdir() as d, mock.patch.dict(os.environ, self.env()):
            root = sample_copy(d)
            cmd = 'echo "proxy is $HTTPS_PROXY"; echo "host part ${https_proxy#http://}"; echo "user:pass@ elsewhere http://u:p1@h.invalid/"'
            code, _, tail = K.run_in_copy(root, cmd, 30)
        self.assertEqual(code, 0, tail)
        self.assertNotIn(self.password, tail)
        self.assertIn("proxy is [secret]", tail)
        self.assertIn("host part [secret]", tail)
        self.assertIn("http://[secret]@h.invalid/", tail, "any URL's user:password@ is replaced")

    def test_a_value_straddling_the_64_kb_cut_is_still_scrubbed(self):
        with tempdir() as d, mock.patch.dict(os.environ, self.env()):
            root = sample_copy(d)
            cmd = f"{sys.executable} -c \"import os, sys; sys.stdout.write(os.environ['HTTPS_PROXY'] + 'B' * {K.OUTPUT_TAIL_BYTES - 21} + chr(10))\""
            code, _, tail = K.run_in_copy(root, cmd, 30)
        self.assertEqual(code, 0, tail)
        for p in pieces(self.password):
            self.assertNotIn(p, tail)

    def test_the_contract_evidence_carries_no_proxy_credential(self):
        with tempdir() as d, mock.patch.dict(os.environ, self.env()):
            root = sample_copy(d)
            with open(os.path.join(root, "component.json"), encoding="utf-8") as f:
                m = json.load(f)
            m["test"] = 'echo "Uses proxy env variable https_proxy == $https_proxy"; exit 1'
            m["example"]["run"] = "env"
            results = K.check_runs(root, m, timeout=30)
        text = json.dumps([r.to_json() for r in results])
        self.assertNotIn(self.password, text)
        self.assertIn("https_proxy == [secret]", text)

    def test_network_secrets_covers_the_encodings_a_client_prints(self):
        import base64
        pw = "p%40" + secrets.token_hex(4)
        env = {"HTTPS_PROXY": f"http://ada:{pw}@127.0.0.1:9", "npm_config_registry": f"https://ci:{self.password}@registry.invalid/",
               "PIP_INDEX_URL": "https://index.invalid/simple", "UNRELATED": f"http://x:{self.password}y@h.invalid"}
        got = K.network_secrets(env)
        plain = "ada:" + pw.replace("%40", "@")
        for v in (env["HTTPS_PROXY"], f"ada:{pw}", pw, pw.replace("%40", "@"), plain, base64.b64encode(plain.encode()).decode(), self.password):
            self.assertIn(v, got)
        self.assertNotIn(self.password + "y", got, "only the network settings a command is handed")


class TaxonomyOutsideACheckout(unittest.TestCase):
    """5: tags say "not checked" outside a checkout; a candidate's own tools/kb-taxonomy.json is not a checkout."""

    def made_up(self, root):
        path = os.path.join(root, "component.json")
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
        m["tags"] = ["made-up-tag"]
        write(path, m)
        write(os.path.join(root, "tools", "kb-taxonomy.json"), {"tags": ["made-up-tag"]})

    def test_outside_a_checkout_the_tags_are_noted_as_not_checked(self):
        with tempdir() as d:
            root = sample_copy(d)
            _, r = K.check_manifest(root)
            self.assertEqual(r.status, "pass", r.summary)
            self.assertIn("tags not checked (outside a checkout of the collection)", r.summary)
            self.made_up(root)
            self.assertIsNone(K.checkout(root), "a candidate's own taxonomy does not make it a checkout")
            _, r = K.check_manifest(root)
            self.assertIn("tags not checked (outside a checkout of the collection)", r.summary)

    def test_inside_a_checkout_its_own_taxonomy_does_not_replace_the_collections(self):
        with tempdir() as d:
            write(os.path.join(d, "tools", "kb-taxonomy.json"), {"tags": ["rag", "security"]})
            os.makedirs(os.path.join(d, "components", "python"))
            root = sample_copy(os.path.join(d, "components", "python"))
            self.made_up(root)
            self.assertEqual(os.path.realpath(K.checkout(root)), os.path.realpath(d))
            _, r = K.check_manifest(root)
        self.assertEqual(r.status, "fail")
        self.assertIn("tags not in the knowledge base's taxonomy: made-up-tag", r.summary)


if __name__ == "__main__":
    unittest.main()
