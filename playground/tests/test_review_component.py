"""Regression tests for the contract check's review findings: containment of the candidate's commands, agreement
with the shelf tool's manifest rules, the import and secret scans, and symlinks."""
import glob
import json
import os
import shutil
import time
import unittest

from tests.helpers import EXAMPLES, tempdir, write
from aiplayground import component as K

SAMPLE = os.path.join(EXAMPLES, "runbook-answerer")
COMPONENTS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "components")
VALID_SPEC = {"document": "a design specification", "sections": ["4.5"], "requirements": ["PLT-DATA-3"],
              "replacement_test": "the platform's data guard passes the same tests"}
LINUX_PROC = os.path.isdir("/proc/self")


def by_id(results):
    return {r.id.split("/", 1)[1]: r for r in results}


def candidate(parent, name="cand", manifest=None, files=None, checkout=True):
    """The sample component, made valid for the shelf (a real spec), under `parent`; a checkout's taxonomy beside it."""
    root = os.path.join(parent, name)
    with open(os.path.join(SAMPLE, "component.json"), encoding="utf-8") as f:
        m = json.load(f)
    if checkout:
        write(os.path.join(parent, "tools", "kb-taxonomy.json"), {"tags": ["rag", "security", "agents"]})
    m["name"] = name
    m["spec"] = dict(VALID_SPEC)
    m.update(manifest or {})
    write(os.path.join(root, "component.json"), m)
    for f in ("README.md", "WALKTHROUGH.md", "answerer.py", "example.py", "tests/__init__.py", "tests/test_answerer.py"):
        with open(os.path.join(SAMPLE, f), encoding="utf-8") as src:
            write(os.path.join(root, f), src.read())
    for path, content in (files or {}).items():
        write(os.path.join(root, path), content)
    return root


def manifest_of(root, change):
    path = os.path.join(root, "component.json")
    with open(path, encoding="utf-8") as f:
        m = json.load(f)
    change(m)
    write(path, m)
    return by_id(K.check(root, run=False))["manifest"]


def in_a_minute(path, seconds=3.0):
    """Wait long enough for a leftover process to have written `path`."""
    time.sleep(seconds)
    return os.path.exists(path)


class Containment(unittest.TestCase):
    def test_the_time_limit_kills_what_the_command_started(self):
        with tempdir() as d:
            root = candidate(d)
            flag = os.path.join(d, "late.txt")
            code, secs, _ = K.run_in_copy(root, f"(sleep 1.5; echo alive > '{flag}') & sleep 30", timeout=1)
            self.assertIsNone(code)
            self.assertLess(secs, 5)
            self.assertFalse(in_a_minute(flag), "a child of the command outlived the time limit")

    def test_nothing_it_started_outlives_a_clean_exit(self):
        with tempdir() as d:
            root = candidate(d)
            flag = os.path.join(d, "late.txt")
            code, secs, _ = K.run_in_copy(root, f"(sleep 1; echo alive > '{flag}') & exit 0", timeout=30)
            self.assertEqual(code, 0)
            self.assertLess(secs, 3)
            self.assertFalse(in_a_minute(flag, 2.0), "a background job outlived the command")

    @unittest.skipUnless(LINUX_PROC and shutil.which("setsid"), "needs /proc and setsid")
    def test_a_process_that_leaves_the_group_is_still_killed(self):
        with tempdir() as d:
            root = candidate(d)
            flag = os.path.join(d, "late.txt")
            K.run_in_copy(root, f"(setsid sh -c \"sleep 1; echo alive > '{flag}'\" &); exit 0", timeout=30)
            self.assertFalse(in_a_minute(flag, 2.0), "a setsid child outlived the command")

    def test_home_tmp_and_xdg_point_into_the_throwaway_directory(self):
        with tempdir() as d:
            root = candidate(d)
            code, _, tail = K.run_in_copy(root, "pwd; env | tr '\\n' '\\t'", timeout=30)   # one line: the output keeps 25
            self.assertEqual(code, 0, tail)
            lines = tail.splitlines()
            work = lines[0][: lines[0].index(os.sep, lines[0].index(os.sep + "playground-") + 1)]   # the throwaway root (mkdtemp's)
            env = dict(item.split("=", 1) for item in lines[1].split("\t") if "=" in item)
            for k in ("HOME", "TMPDIR", "TEMP", "TMP", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR", "npm_config_cache"):
                self.assertTrue(env.get(k, "").startswith(work + os.sep), f"{k}={env.get(k)}")
            if os.environ.get("HOME"):
                self.assertNotIn("=" + os.environ["HOME"] + "\t", lines[1])
            allowed = {"PATH", "LANG", "LC_ALL", "SYSTEMROOT", "PYTHONDONTWRITEBYTECODE", K.RUN_MARKER, "PWD", "SHLVL", "_", "OLDPWD",
                       "HOME", "TMPDIR", "TEMP", "TMP", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR",
                       "npm_config_cache", *K.NETWORK_VARS}   # the proxy and CA settings pass through (review 2)
            self.assertEqual(set(env) - allowed, set())
            self.assertFalse(os.path.exists(work), "the throwaway directory is removed")

    def test_the_command_does_not_see_the_testers_arguments_or_source_path(self):
        with tempdir() as d:
            root = candidate(d)
            code, _, tail = K.run_in_copy(root, "env; pwd", timeout=30)
            self.assertEqual(code, 0, tail)
            self.assertNotIn(root, tail)

    def test_output_of_both_streams_is_kept(self):
        with tempdir() as d:
            root = candidate(d)
            code, _, tail = K.run_in_copy(root, "echo to-out; echo to-err >&2; exit 3", timeout=30)
            self.assertEqual(code, 3)
            self.assertIn("to-out", tail)
            self.assertIn("to-err", tail)


class ManifestAgreesWithTheShelf(unittest.TestCase):
    """Each case: what tools/shelf.py's validate() decides, and so what the manifest check must say."""

    CASES = {
        "the valid base": (lambda m: None, "pass"),
        "a pre-release version": (lambda m: m.update(version="1.2.0-rc.1"), "fail"),
        "a version that is not text": (lambda m: m.update(version=1), "fail"),
        "an empty spec": (lambda m: m.update(spec={}), "fail"),
        "a spec without a replacement test": (lambda m: m["spec"].pop("replacement_test"), "fail"),
        "a requirement id not PLT-<family>-<n>": (lambda m: m["spec"].update(requirements=["DATA-3"]), "fail"),
        "a sign-off written by hand as text": (lambda m: m["signoff"].update(owner="approved"), "fail"),
        "a sign-off without a date": (lambda m: m["signoff"].update(owner={"by": "A Person <a@example.com>", "version": "0.1.0"}), "fail"),
        "a sign-off with a malformed date": (lambda m: m["signoff"].update(owner={"by": "A <a@example.com>", "date": "1/2/2026", "version": "0.1.0"}), "fail"),
        "a well-formed sign-off": (lambda m: m["signoff"].update(owner={"by": "A <a@example.com>", "date": "2026-01-02", "version": "0.1.0"}), "pass"),
        "a sign-off entry with an extra key": (lambda m: m["signoff"].update(note=None), "pass"),
        "a sign-off without ai_security": (lambda m: m["signoff"].pop("ai_security"), "fail"),
        "a code component's example without run": (lambda m: m["example"].pop("run"), "fail"),
        "an example path that does not exist": (lambda m: m["example"].update(path="nowhere.py"), "fail"),
        "requires with an empty entry": (lambda m: m.update(requires=[""]), "fail"),
        "requires with a number": (lambda m: m.update(requires=[3]), "fail"),
        "requires naming a package": (lambda m: m.update(requires=["requests>=2"]), "pass"),
        "a non-agent carrying agent": (lambda m: m.update(agent={"template": "x"}), "fail"),
        "used_in with a number": (lambda m: m.update(used_in=[1]), "fail"),
        "used_in with an empty name": (lambda m: m.update(used_in=[" "]), "fail"),
        "used_in naming a project": (lambda m: m.update(used_in=["a-project"]), "pass"),
        "no used_in at all": (lambda m: m.pop("used_in"), "pass"),
        "source with only project": (lambda m: m.update(source={"project": "p"}), "pass"),
        "source without project": (lambda m: m.update(source={"path": "p"}), "fail"),
        "an empty owner (the shelf asks only for the field)": (lambda m: m.update(owner=""), "pass"),
        "a missing owner": (lambda m: m.pop("owner"), "fail"),
        "a missing requires": (lambda m: m.pop("requires"), "fail"),
        "a missing test field": (lambda m: m.pop("test"), "fail"),
        "an empty test on a code component": (lambda m: m.update(test=""), "fail"),
        "a summary of 161 characters": (lambda m: m.update(summary="x" * 161), "fail"),
        "a tag outside the taxonomy": (lambda m: m.update(tags=["not-a-tag"]), "fail"),
        "no tags": (lambda m: m.update(tags=[]), "fail"),
        "a walkthrough that does not exist": (lambda m: m.update(walkthrough="NOPE.md"), "fail"),
        "vendored entries that are not {path, from}": (lambda m: m.update(vendored=[{"path": "answerer.py"}]), "fail"),
        "pairs_with that is not a list": (lambda m: m.update(pairs_with=3), "fail"),
    }

    def test_each_rule_as_the_shelf_decides_it(self):
        with tempdir() as d:
            for label, (change, want) in self.CASES.items():
                with self.subTest(label):
                    root = candidate(d, name="cand")
                    r = manifest_of(root, change)
                    self.assertEqual(r.status, want, f"{label}: {r.summary}")
                    shutil.rmtree(root)

    def test_a_skill_needs_skill_md_with_its_checklist_heading(self):
        skill = {"category": "skill", "language": "markdown", "test": "", "example": {"path": "example.py"}}
        with tempdir() as d:
            root = candidate(d, name="noskill", manifest=skill)
            self.assertIn("SKILL.md", by_id(K.check(root, run=False))["manifest"].summary)
            root = candidate(d, name="nohead", manifest=skill, files={"SKILL.md": "# Skill\n\n## Checks\n\n- [ ] one\n"})
            r = by_id(K.check(root, run=False))["manifest"]
            self.assertEqual(r.status, "fail")
            self.assertIn("Checks before finishing", r.summary)
            root = candidate(d, name="good", manifest=skill, files={"SKILL.md": "# Skill\r\n\r\n## Checks before finishing\r\n\r\n- [ ] one\r\n"})
            self.assertEqual(by_id(K.check(root, run=False))["manifest"].status, "pass")

    def _checkout(self, d):
        """A checkout of the collection: a taxonomy, a harness, a tool, a skill and a vendored source."""
        write(os.path.join(d, "tools", "kb-taxonomy.json"), {"tags": ["rag", "security", "agents"]})
        for name, cat in (("the-harness", "harness"), ("the-tool", "tool"), ("the-skill", "skill")):
            write(os.path.join(d, "components", "python", name, "component.json"), {"name": name, "category": cat})
        write(os.path.join(d, "components", "python", "the-tool", "shared.py"), "X = 1\n")
        return os.path.join(d, "components", "agents")

    def test_an_agent_names_a_harness_and_tools_that_exist(self):
        tpl = "# Template\n\n```json\n" + json.dumps({"name": "a", "role": "r", "ladder": "L1", "stages": [], "tools": [], "never": ["x"],
                                                    "budget": {}}) + "\n```\n"

        def agent(tools, harness):
            return {"category": "agent", "agent": {"template": "TEMPLATE.md", "tools": tools, "harness": harness}}
        with tempdir() as d:
            parent = self._checkout(d)
            os.makedirs(parent)
            ok = candidate(parent, name="ok", manifest=agent(["the-tool"], "the-harness"), files={"TEMPLATE.md": tpl}, checkout=False)
            self.assertEqual(by_id(K.check(ok, run=False))["manifest"].status, "pass")
            for name, tools, harness, words in (("unknown", ["no-such"], "the-harness", "unknown component"),
                                                ("skilltool", ["the-skill"], "the-harness", "is a skill"),
                                                ("notharness", ["the-tool"], "the-tool", "must name a harness"),
                                                ("notools", [], "the-harness", "needs all three")):
                root = candidate(parent, name=name, manifest=agent(tools, harness), files={"TEMPLATE.md": tpl}, checkout=False)
                r = by_id(K.check(root, run=False))["manifest"]
                self.assertEqual(r.status, "fail", name)
                self.assertIn(words, json.dumps(r.evidence), name)
            badtpl = candidate(parent, name="badtpl", manifest=agent(["the-tool"], "the-harness"), files={"TEMPLATE.md": "# no json\n"}, checkout=False)
            self.assertIn("```json block", by_id(K.check(badtpl, run=False))["manifest"].summary)
        with tempdir() as d:      # outside a checkout the names cannot be looked up: not a failure, a note
            root = candidate(d, name="away", manifest=agent(["the-tool"], "the-harness"), files={"TEMPLATE.md": tpl}, checkout=False)
            r = by_id(K.check(root, run=False))["manifest"]
            self.assertEqual(r.status, "pass", r.summary)
            self.assertIn("not checked", r.summary)

    def test_vendored_files_and_pairs_with_inside_a_checkout(self):
        with tempdir() as d:
            parent = self._checkout(d)
            os.makedirs(parent)
            vend = {"vendored": [{"path": "shared.py", "from": "components/python/the-tool/shared.py"}], "pairs_with": ["the-tool"]}
            same = candidate(parent, name="same", manifest=vend, files={"shared.py": "X = 1\n"}, checkout=False)
            self.assertEqual(by_id(K.check(same, run=False))["manifest"].status, "pass")
            drift = candidate(parent, name="drift", manifest=vend, files={"shared.py": "X = 2\n"}, checkout=False)
            self.assertIn("differs", by_id(K.check(drift, run=False))["manifest"].summary)
            unknown = candidate(parent, name="unknownpair", manifest={"pairs_with": ["no-such"]}, checkout=False)
            self.assertIn("unknown component", by_id(K.check(unknown, run=False))["manifest"].summary)

    def test_every_shelved_component_passes_the_manifest_check(self):
        if not os.path.isdir(COMPONENTS):
            self.skipTest("not inside a checkout of the collection")
        seen = []
        for root in sorted(glob.glob(os.path.join(COMPONENTS, "*", "*"))):
            if not os.path.isfile(os.path.join(root, "component.json")):
                continue
            seen.append(os.path.basename(root))
            got = by_id(K.check(root, run=False))
            with self.subTest(os.path.relpath(root, COMPONENTS)):
                self.assertEqual(got["manifest"].status, "pass", got["manifest"].summary)
                self.assertEqual(got["self-contained"].status, "pass", got["self-contained"].summary)
                self.assertEqual(got["secrets"].status, "pass", got["secrets"].summary)
                self.assertEqual(got["symlinks"].status, "pass", got["symlinks"].summary)
                self.assertNotEqual(got["readme"].status, "fail", got["readme"].summary)
        self.assertTrue(seen, "no component found under components/")


class ReadmeHeadings(unittest.TestCase):
    FULL = ["What it is for", "Five-minute start", "What is inside", "How to reuse it", "Rules it enforces", "Where it came from", "Known limits"]

    def readme(self, d, headings, lead=""):
        text = "# cand\n\n" + (lead + "\n\n" if lead else "") + "".join(f"## {h}\n\ntext\n\n" for h in headings)
        return by_id(K.check(candidate(d, name=f"c{len(os.listdir(d))}", files={"README.md": text}), run=False))["readme"]

    def test_how_much_a_missing_heading_costs(self):
        with tempdir() as d:
            self.assertEqual(self.readme(d, self.FULL).status, "pass")
            r = self.readme(d, [h for h in self.FULL if h != "Rules it enforces"])
            self.assertEqual((r.status, r.severity), ("review", "low"))
            r = self.readme(d, [h for h in self.FULL if h not in ("Rules it enforces", "What it is for")])
            self.assertEqual((r.status, r.severity), ("review", "low"))
            self.assertIn("What it is for", r.summary)
            r = self.readme(d, [h for h in self.FULL if h not in ("Rules it enforces", "What it is for")], lead="A lead paragraph.")
            self.assertEqual((r.status, r.severity), ("review", "low"))
            self.assertNotIn("What it is for", r.summary)
            r = self.readme(d, [h for h in self.FULL if h != "How to reuse it"])
            self.assertEqual((r.status, r.severity), ("review", "medium"))
            for missing in ("Five-minute start", "Known limits"):
                r = self.readme(d, [h for h in self.FULL if h not in (missing, "Rules it enforces")])
                self.assertEqual((r.status, r.severity), ("fail", "medium"), missing)
                self.assertIn(missing, r.summary)


class ImportScan(unittest.TestCase):
    def status(self, files):
        with tempdir() as d:
            root = os.path.join(d, "cand")
            os.makedirs(root)
            for name, text in files.items():
                write(os.path.join(root, name), text)
            return K.check_self_contained(root, {"requires": []})

    def test_dynamic_imports_go_to_a_person(self):
        for src in ("import importlib\nrequests = importlib.import_module('requests')\n", "boto3 = __import__('boto3')\n",
                    "from importlib import import_module\nm = import_module(name='yaml')\n", "import importlib, sys\nm = importlib.import_module(sys.argv[1])\n",
                    "m = __import__('.'.join(['a', 'b']))\n", "import importlib\nm = importlib.import_module('.sibling', 'pkg')\n"):
            with self.subTest(src):
                r = self.status({"mod.py": src})
                self.assertEqual(r.status, "review", r.summary)
        self.assertEqual(self.status({"mod.py": "t = __import__('time').time()\nimport importlib\nj = importlib.import_module('json')\n"}).status, "pass")
        self.assertEqual(self.status({"mod.py": "try:\n    import importlib\n    y = importlib.import_module('yaml')\nexcept ImportError:\n    y = None\n"}).status, "pass")
        r = self.status({"mod.py": "import requests\nx = __import__('boto3')\n"})
        self.assertEqual(r.status, "fail")
        self.assertIn("boto3", json.dumps(r.evidence))

    def test_a_relative_import_outside_is_a_finding_even_when_guarded(self):
        r = self.status({"mod.py": "try:\n    from ... import shared_helpers\nexcept ImportError:\n    shared_helpers = None\n"})
        self.assertEqual(r.status, "fail")
        self.assertIn("reaches outside", r.summary)
        self.assertEqual(self.status({"pkg/__init__.py": "", "pkg/a.py": "from . import b\nfrom .b import c\n", "pkg/b.py": "c = 1\n"}).status, "pass")

    def test_typescript_relative_and_dynamic_imports(self):
        self.assertEqual(self.status({"src/a.ts": 'const m = await import("../../other/x");\n'}).status, "fail")
        self.assertEqual(self.status({"src/a.ts": 'const m = require("../../other/x");\n'}).status, "fail")
        self.assertEqual(self.status({"src/a.ts": 'export * from "../../other/x";\n'}).status, "fail")
        self.assertEqual(self.status({"src/a.ts": 'const m = await import("./b");\nimport { c } from "../lib/c";\n'}).status, "pass")

    def test_a_sibling_directory_sharing_the_prefix_is_outside(self):
        r = self.status({"a.ts": 'import x from "../cand2/x";\n'})
        self.assertEqual(r.status, "fail", "the old prefix comparison took /d/cand2 for part of /d/cand")

    def test_test_data_does_not_make_an_import_local(self):
        self.assertEqual(self.status({"mod.py": "import requests\n", "tests/fixtures/requests/a.json": "{}"}).status, "fail")
        self.assertEqual(self.status({"mod.py": "import requests\n", "tests/fixtures/requests.py": ""}).status, "fail")
        self.assertEqual(self.status({"mod.py": "import requests\n", "tests/requests/data.json": "{}"}).status, "fail")
        self.assertEqual(self.status({"mod.py": "import mypkg\nimport helper\n", "mypkg/__init__.py": "", "tools/helper.py": ""}).status, "pass")

    def test_sys_path_to_a_parent_is_a_finding_even_when_guarded(self):
        r = self.status({"mod.py": "import sys\ntry:\n    sys.path.insert(0, '../shared')\n    import shared\nexcept ImportError:\n    pass\n"})
        self.assertEqual(r.status, "fail")
        self.assertIn("parent directory", r.summary)


class SecretScan(unittest.TestCase):
    VALUE = "Zq" + "8vT3mN6pR1wX4yB7" + "cD0eF2gH5jK9"     # secret-shaped, assembled at runtime

    def status(self, name, text):
        with tempdir() as d:
            root = os.path.join(d, "cand")
            os.makedirs(root)
            write(os.path.join(root, name), text)
            return K.check_secrets(root)[0].status

    def test_credentials_written_as_values(self):
        v = self.VALUE
        for name, text in ((".env", f"DB_PASSWORD={v}\n"), (".env", f"export API_SECRET={v}\n"), (".env.local", f"GITHUB_TOKEN={v}\n"),
                           ("settings.json", f'{{"password": "{v}"}}\n'), ("config.yaml", f"client_secret: {v}\n"),
                           ("config.yml", f"  api_key: '{v}'\n"), ("creds.py", f'aws_secret_access_key = "{v}/{v}"\n'),
                           ("client.py", f'auth_token = "{v}"\n'), ("client.py", f"connect(token='{v}')\n"), ("conf.ini", f"password = {v}\n"),
                           ("app.ts", f'const apiKey = "{v}";\n'), ("conf.py", f'password = "{v}"\n')):
            with self.subTest(name=name, text=text):
                self.assertEqual(self.status(name, text), "fail")

    def test_visible_placeholders_and_descriptions_are_not_secrets(self):
        for name, text in ((".env", "DB_PASSWORD=XXXXXXXXXXXX\n"), (".env", "DB_PASSWORD=<your-password>\n"), (".env", "API_TOKEN=${API_TOKEN}\n"),
                           ("config.yaml", "client_secret: changeme-please\n"), ("settings.json", '{"password": "example-password-1"}\n'),
                           ("conf.py", 'password = "your-password-here"\n'), ("conf.py", 'api_key = "************"\n'),
                           ("README.md", "export KEY=sk-ant-" + "X" * 32 + "\n"), ("README.md", "AKIA" + "X" * 16 + "\n"),
                           ("conf.py", 'secret_name = "app/pagerduty-api"\n'), ("a.py", 'call({"SecretId": "app/pagerduty-api"})\n'),
                           ("conf.py", 'token_url = "https://idp.example.com/token"\n'), ("README.md", "The token: authenticates the caller.\n"),
                           ("conf.py", 'password = os.environ["DB_PASSWORD"]\n'), ("conf.py", "token = get_token(name)\n"),
                           ("conf.py", 'PASSWORD_HEADER = "x_password_header"\n'), ("config.yaml", "max_tokens: 1024\n")):
            with self.subTest(name=name, text=text):
                self.assertEqual(self.status(name, text), "pass")


class Symlinks(unittest.TestCase):
    def test_a_dangling_link_does_not_abort_the_check(self):
        with tempdir() as d:
            root = candidate(d)
            os.symlink("build/latest-output", os.path.join(root, "latest"))
            got = by_id(K.check(root, run=False))
            self.assertEqual(got["symlinks"].status, "pass", got["symlinks"].summary)
            self.assertEqual(got["secrets"].status, "pass")

    def test_a_dangling_link_is_copied_as_a_link(self):
        with tempdir() as d:
            root = candidate(d)
            os.symlink("build/latest-output", os.path.join(root, "latest"))
            code, _, tail = K.run_in_copy(root, "test -L latest && ! test -e latest", timeout=30)
            self.assertEqual(code, 0, tail)

    def test_links_out_of_the_component_go_to_a_person(self):
        with tempdir() as d:
            root = candidate(d)
            write(os.path.join(d, "outside.txt"), "password = 'not scanned through a link'\n")
            os.symlink(os.path.join(d, "outside.txt"), os.path.join(root, "absolute"))
            os.symlink(os.path.join("..", "outside.txt"), os.path.join(root, "relative"))
            os.symlink(d, os.path.join(root, "parentdir"))
            os.symlink("answerer.py", os.path.join(root, "inside"))
            got = by_id(K.check(root, run=False))
            r = got["symlinks"]
            self.assertEqual((r.status, r.severity), ("review", "medium"))
            text = json.dumps(r.evidence)
            for name in ("absolute", "relative", "parentdir"):
                self.assertIn(name, text)
            self.assertNotIn("inside", text)
            self.assertEqual(got["secrets"].status, "pass", "links are not followed by the scans")


if __name__ == "__main__":
    unittest.main()
