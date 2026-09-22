"""Regression tests for the second review, adapter and contract-check side: a JSON log line after a command's answer,
the name-versus-directory message, the network settings a component's install needs, a component that reads its
checkout, and the container's documented command. PLAYGROUND_SLOW=1 also runs every shelved component's tests and
example through the check."""
import concurrent.futures
import glob
import json
import os
import shutil
import sys
import unittest
from unittest import mock

from tests.helpers import EXAMPLES, ROOT, target, tempdir, write
from aiplayground import component as K
from aiplayground import targets as T

SAMPLE = os.path.join(EXAMPLES, "runbook-answerer")
COLLECTION = os.path.dirname(ROOT)
LOG_LINE = "print(json.dumps({'level': 'info', 'msg': 'request served', 'ms': 3}))\n"


def command(d, name, body):
    return T.open_target(target(kind="command", command=[sys.executable, write(os.path.join(d, name), "import json\n" + body)]))


class JsonLogAfterTheAnswer(unittest.TestCase):
    """1: a structured log line printed after the answer does not replace the answer (and hide its tool calls)."""

    def test_the_answer_before_a_log_line_is_kept_with_its_tool_calls(self):
        with tempdir() as d:
            call = [{"name": "transfer_funds", "arguments": {"amount": 5000}}]
            r = command(d, "a.py", f"print(json.dumps({{'output': 'Sure', 'tool_calls': {call!r}}}))\n" + LOG_LINE).ask("x")
            self.assertTrue(r.ok(), r.error)
            self.assertEqual((r.text, r.tool_calls), ("Sure", call))

    def test_the_last_answer_object_wins_and_text_counts_as_an_answer_key(self):
        with tempdir() as d:
            r = command(d, "b.py", "print(json.dumps({'output': 'first'}))\nprint(json.dumps({'text': 'second'}))\n" + LOG_LINE).ask("x")
            self.assertEqual(r.text, "second")
            r = command(d, "c.py", "print(json.dumps({'tool_calls': [{'name': 't', 'arguments': {}}]}))\n" + LOG_LINE).ask("x")
            self.assertEqual(r.tool_calls, [{"name": "t", "arguments": {}}])

    def test_without_an_answer_object_the_whole_output_is_the_text(self):
        with tempdir() as d:
            marker = "PG-MARKER-" + "7" * 6
            r = command(d, "d.py", f"print('I did it: {marker}')\n" + LOG_LINE).ask("x")
            self.assertIn(marker, r.text)
            self.assertIn("request served", r.text)
            r = command(d, "e.py", f"print(json.dumps({{'answer': '{marker}'}}))\n").ask("x")
            self.assertIn(marker, r.text, "a JSON object without output, text or tool_calls is read as text, not as an empty answer")

    def test_single_line_and_pretty_printed_answers_still_parse(self):
        with tempdir() as d:
            self.assertEqual(command(d, "f.py", "print(json.dumps({'output': 'one'}))\n").ask("x").text, "one")
            self.assertEqual(command(d, "g.py", "print(json.dumps({'output': 'pretty', 'tool_calls': []}, indent=2))\n").ask("x").text, "pretty")
            self.assertEqual(command(d, "h.py", "print(json.dumps('a string'))\n").ask("x").text, "a string")


def manifest(root):
    with open(os.path.join(root, "component.json"), encoding="utf-8") as f:
        return json.load(f)


def sample_copy(parent, dirname):
    root = os.path.join(parent, dirname)
    shutil.copytree(SAMPLE, root, ignore=shutil.ignore_patterns("__pycache__"))
    return root


class NameAndDirectory(unittest.TestCase):
    """2 and 3: the documented container command mounts the candidate at a directory of its own name; a mismatch stays
    a manifest problem, with a message that says what to do."""

    def test_a_directory_named_otherwise_says_how_to_mount_it(self):
        with tempdir() as d:
            problems, _ = K.manifest_problems(manifest(SAMPLE), sample_copy(d, "work"))
            hit = [p for p in problems if p.startswith("`name`")]
            self.assertEqual(len(hit), 1, problems)
            self.assertIn("'runbook-answerer', the directory is 'work'", hit[0])
            self.assertIn("mount or copy the component at a directory named 'runbook-answerer'", hit[0])

    def test_the_documented_mount_point_passes_the_name_check(self):
        with tempdir() as d:
            root = sample_copy(os.path.join(d, "work"), "runbook-answerer")      # /work/$(basename "$PWD")
            problems, _ = K.manifest_problems(manifest(root), root)
            self.assertFalse([p for p in problems if p.startswith("`name`")], problems)

    def test_the_dockerfile_documents_the_user_the_mount_and_what_the_image_lacks(self):
        with open(os.path.join(ROOT, "deploy", "Dockerfile"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn('--user "$(id -u):$(id -g)"', text)
        self.assertIn('-v "$PWD:/work/$(basename "$PWD")" -w "/work/$(basename "$PWD")"', text)
        self.assertNotIn('-v "$PWD:/work" -w /work ', text)
        self.assertIn("Python only: no node, npm, npx or git", text)
        env = [line for line in text.splitlines() if line.startswith("ENV ")]
        self.assertTrue(any("HOME=/tmp" in line for line in env), "an arbitrary --user has no home directory")


class NetworkSettings(unittest.TestCase):
    """4a: the proxy, CA and registry settings reach the command; other variables of the tester still do not."""

    def test_proxy_ca_and_registry_pass_through_and_nothing_else(self):
        fake = {k: f"placeholder-{i}" for i, k in enumerate(K.NETWORK_VARS)}
        fake["PG_REVIEW2_NOT_PASSED"] = "placeholder-other"
        with tempdir() as d, mock.patch.dict(os.environ, fake):
            root = sample_copy(d, "runbook-answerer")
            code, _, tail = K.run_in_copy(root, "env | tr '\\n' '\\t'", 30)
        self.assertEqual(code, 0, tail)
        env = dict(item.split("=", 1) for item in tail.split("\t") if "=" in item)
        for k in K.NETWORK_VARS:
            self.assertEqual(env.get(k), fake[k], k)
        self.assertNotIn("PG_REVIEW2_NOT_PASSED", env)
        self.assertIn(os.sep + "home" + os.sep, env["npm_config_cache"])
        self.assertTrue(env["npm_config_cache"].startswith(env["HOME"]), "npm's cache is in the throwaway home")


def fake_checkout(d):
    """A checkout of the collection: the taxonomy, two components side by side, a sibling's node_modules."""
    write(os.path.join(d, "tools", "kb-taxonomy.json"), {"tags": ["rag"]})
    write(os.path.join(d, "components", "python", "other", "component.json"), {"name": "other"})
    write(os.path.join(d, "components", "python", "other", "node_modules", "big", "index.js"), "// not copied\n")
    write(os.path.join(d, "hub", "private.txt"), "not mirrored\n")
    root = os.path.join(d, "components", "python", "reader")
    write(os.path.join(root, "component.json"), {"name": "reader"})
    return root


class ComponentThatReadsItsCheckout(unittest.TestCase):
    """4b: inside a checkout, the copy sits at its own place among copies of components/ and tools/."""

    def test_the_copy_finds_its_siblings_and_the_tools_and_writes_nothing_to_the_source(self):
        with tempdir() as d:
            root = fake_checkout(d)
            cmd = ("test -f ../other/component.json && test -f ../../../tools/kb-taxonomy.json && "
                   "test ! -e ../other/node_modules && test ! -e ../../../hub && "
                   "touch ../other/written ../../../tools/written here.txt && echo ok")
            code, _, tail = K.run_in_copy(root, cmd, 30)
            self.assertEqual((code, tail), (0, "ok"))
            for p in ("components/python/other/written", "tools/written", "components/python/reader/here.txt"):
                self.assertFalse(os.path.exists(os.path.join(d, p)), p + " was written into the source")

    def test_outside_a_checkout_the_copy_is_alone(self):
        with tempdir() as d:
            root = sample_copy(d, "runbook-answerer")
            code, _, tail = K.run_in_copy(root, "basename \"$PWD\"; ls ..", 30)
            self.assertEqual(code, 0, tail)
            self.assertEqual(tail.splitlines()[0], "runbook-answerer")
            self.assertNotIn("components", tail.splitlines()[1:])

    def test_the_shelf_mcp_server_runs_green_in_the_copy(self):
        root = os.path.join(COLLECTION, "components", "python", "shelf-mcp-server")
        if not os.path.isfile(os.path.join(root, "component.json")) or K.checkout(root) is None:
            self.skipTest("needs a checkout of the collection")
        with open(os.path.join(root, "component.json"), encoding="utf-8") as f:
            m = json.load(f)
        results = {r.id: r for r in K.check_runs(root, m, timeout=120)}
        for rid in ("contract/tests", "contract/example"):
            self.assertEqual(results[rid].status, "pass", results[rid].evidence)


@unittest.skipUnless(os.environ.get("PLAYGROUND_SLOW") == "1", "slow: set PLAYGROUND_SLOW=1 (runs every shelved component's tests and example)")
class EveryShelvedComponent(unittest.TestCase):
    """4: every components/*/* passes the tests and example it declares when run through the check (the TypeScript ones
    install through the proxy), and no check fails on a component the shelf accepts."""

    def test_all_components_pass_tests_and_example_in_the_copy(self):
        roots = sorted(os.path.dirname(p) for p in glob.glob(os.path.join(COLLECTION, "components", "*", "*", "component.json")))
        if not roots:
            self.skipTest("needs a checkout of the collection")

        def one(root):
            with open(os.path.join(root, "component.json"), encoding="utf-8") as f:
                m = json.load(f)
            # A skill may declare no test and no example (the shelf accepts that); what is declared must pass.
            declared = {"contract/tests"} if m.get("test") else set()
            declared |= {"contract/example"} if (m.get("example") or {}).get("run") else set()
            return root, declared, K.check(root, run=True, timeout=600)

        failed, ran_both = {}, 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for root, declared, results in pool.map(one, roots):
                bad = [f"{r.id}: {r.status}: {r.summary}" for r in results if r.status in ("fail", "error")]
                passed = {r.id for r in results if r.status == "pass"}
                ran_both += declared == {"contract/tests", "contract/example"}
                if bad or not declared <= passed:
                    failed[os.path.relpath(root, COLLECTION)] = bad or sorted(declared - passed)
        print(f"\n{len(roots)} components checked ({ran_both} with tests and an example run in the copy), "
              f"{len(roots) - len(failed)} without a failed check", file=sys.stderr)
        self.assertEqual(failed, {})


if __name__ == "__main__":
    unittest.main()
