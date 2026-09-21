"""Unit tests for the shelf tool, the scaffolder and the knowledge-base publisher: the parts a bad manifest, a bad
sign-off export or a wrapped README line used to crash or slip through. Run from the repository root:
python3 -m unittest discover -s tools/tests -t .
"""
import io, json, os, shutil, subprocess, sys, tempfile, unittest
from contextlib import redirect_stdout

from tools import publish_kb, shelf

ROOT = shelf.ROOT


def first_manifest(category: str) -> dict:
    for path in shelf.find_manifests():
        m = shelf.load(path)
        if m["category"] == category:
            return m
    raise AssertionError(f"no {category} component to test with")


class Requires(unittest.TestCase):
    def test_missing_requires_is_reported_not_a_crash(self):
        m = dict(first_manifest("tool")); del m["requires"]
        self.assertIn("missing field `requires`", shelf.validate(m))

    def test_requires_must_be_a_list_of_names(self):
        m = dict(first_manifest("tool")); m["requires"] = "requests"
        self.assertTrue(any(p.startswith("requires must be a list") for p in shelf.validate(m)))
        m["requires"] = ["requests", 3]
        self.assertTrue(any(p.startswith("requires must be a list") for p in shelf.validate(m)))
        m["requires"] = []
        self.assertFalse(any(p.startswith("requires must be a list") for p in shelf.validate(m)))

    def test_hub_detail_survives_a_manifest_without_requires(self):
        m = dict(first_manifest("tool")); m.pop("requires", None)
        detail = shelf.hub_detail(m, shelf.hub_listing(m))
        note = next(t["note"] for t in detail["tiles"] if t["label"] == "Language")
        self.assertIn(note, ("standard library only", "no runtime dependency"))


class SkillChecklistHeading(unittest.TestCase):
    def test_skill_needs_the_checks_before_finishing_heading(self):
        m = first_manifest("skill")
        with tempfile.TemporaryDirectory() as tmp:
            d = os.path.join(tmp, m["name"]); shutil.copytree(m["_dir"], d, ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
            copy = dict(m, _dir=d, _rel="scratch/" + m["name"])
            self.assertFalse([p for p in shelf.validate(copy) if "Checks before finishing" in p])
            skill = os.path.join(d, "SKILL.md"); text = open(skill, encoding="utf-8").read()
            open(skill, "w", encoding="utf-8").write(text.replace(shelf.SKILL_CHECKS_HEADING, "## Checks before you are done"))
            self.assertTrue([p for p in shelf.validate(copy) if "Checks before finishing" in p])


class ApplySignoffs(unittest.TestCase):
    def test_non_object_entry_is_skipped_and_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "signoffs.json")
            json.dump({"signoffs": [42, "owner", None, {"component": "no-such-component", "role": "owner", "by": "A", "date": "2026-09-21", "version": "1.0.0"}]}, open(path, "w"))
            out = io.StringIO()
            with redirect_stdout(out):
                code = shelf.apply_signoffs([], path)
            self.assertEqual(code, 1)
            self.assertIn("signoffs[0]: not an object (int)", out.getvalue())
            self.assertIn("signoffs[2]: not an object (NoneType)", out.getvalue())
            self.assertIn("no-such-component · owner: unknown component", out.getvalue())
            self.assertIn("4 skipped", out.getvalue())


class OneLineLists(unittest.TestCase):
    def test_wrapped_items_are_joined_outside_code_fences(self):
        text = ("# T\n\n- first item that wraps\n  onto a second line\n  and a third\n- second\n  more\n1. numbered\n   continues\n\n"
                "paragraph after a blank line\n\n- nested\n  - child item\n    child wraps\n\n```\n- code\n  stays\n```\n")
        self.assertEqual(shelf.kb_one_line_lists(text),
                         "# T\n\n- first item that wraps onto a second line and a third\n- second more\n1. numbered continues\n\n"
                         "paragraph after a blank line\n\n- nested\n  - child item child wraps\n\n```\n- code\n  stays\n```\n")

    def test_a_table_or_heading_after_an_item_is_not_joined(self):
        text = "- item\n| a | b |\n- item2\n## H\n"
        self.assertEqual(shelf.kb_one_line_lists(text), text)

    def test_every_exported_page_has_one_line_items(self):
        ms = [shelf.load(p) for p in shelf.find_manifests()]
        for path, content in shelf.kb_outputs(ms).items():
            if path.endswith(".md") and os.sep + "docs" + os.sep in path:
                self.assertFalse([p for p in shelf.kb_page_problems("x/y.md", content) if "continues" in p], path)


class KbPageRules(unittest.TestCase):
    GOOD = "---\ntitle: T\nowner: team\nstatus: active\nreviewed: '2026-09-21'\ntags: [security, agents]\naudience: [engineer]\n---\n# T\n\n- one [link](../skills/README.md) and [there](#here)\n"

    def test_a_good_page_passes(self):
        self.assertEqual(shelf.kb_page_problems("components/x.md", self.GOOD), [])

    def test_frontmatter_keys_and_tags(self):
        bad = self.GOOD.replace("owner: team\n", "").replace("tags: [security, agents]", "tags: [security, not-a-tag]")
        p = shelf.kb_page_problems("components/x.md", bad)
        self.assertIn("frontmatter lacks `owner`", p)
        self.assertIn("tag `not-a-tag` is not in the knowledge base's taxonomy", p)
        self.assertEqual(shelf.kb_page_problems("components/x.md", "# no frontmatter\n"), ["no frontmatter (owner, status, reviewed, tags, audience)"])

    def test_links_must_stay_inside_docs(self):
        page = self.GOOD + "\n[out](../../README.md) [site](/kb/page/x.md) [web](https://example.invalid/x) [mail](mailto:a@b.c) [in](../onboarding/x.md)\n"
        p = [x for x in shelf.kb_page_problems("components/x.md", page) if "leaves docs/" in x]
        self.assertEqual(len(p), 4, p)
        self.assertTrue(all(x.startswith("line 13:") for x in p), p)

    def test_wrapped_list_item_and_length(self):
        page = self.GOOD + "- wraps\n  here\n\n" + "x\n" * 200
        p = shelf.kb_page_problems("components/x.md", page)
        self.assertEqual([x for x in p if "continues" in x], ["line 13: list item continues on the next line"])
        self.assertTrue(any(x.endswith("the knowledge base allows 200") for x in p), p)

    def test_the_repository_pages_pass(self):
        ms = [shelf.load(p) for p in shelf.find_manifests()]
        self.assertEqual(shelf.kb_problems(ms), [])


class SkillOwner(unittest.TestCase):
    def test_owner_comes_from_the_skill_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "SKILL.md"), "w").write("---\nname: s\nowner: some-team\n---\n# s\n")
            self.assertEqual(shelf.skill_owner({"_dir": tmp}), "some-team")
            open(os.path.join(tmp, "SKILL.md"), "w").write("---\nname: s\n---\n# s\n")
            self.assertEqual(shelf.skill_owner({"_dir": tmp}), shelf.KB_OWNER["skill"])

    def test_skill_rows_carry_each_skill_owner(self):
        ms = [shelf.load(p) for p in shelf.find_manifests()]
        rows = shelf.kb_skill_rows(ms).splitlines()
        skills = [m for m in ms if m["category"] == "skill"]
        self.assertEqual([r.split("|")[3].strip() for r in rows], [shelf.skill_owner(m) for m in skills])


class PublishKbConfig(unittest.TestCase):
    SNIPPET = "  - id: components\n    path: components\n"

    def test_section_goes_before_frontmatter_when_present(self):
        cfg = "sections:\n  - id: skills\nfrontmatter:\n  required: [owner]\n"
        self.assertEqual(publish_kb.config_with_section(cfg, self.SNIPPET), "sections:\n  - id: skills\n  - id: components\n    path: components\nfrontmatter:\n  required: [owner]\n")

    def test_section_is_appended_with_a_note_when_frontmatter_is_absent(self):
        out = io.StringIO()
        with redirect_stdout(out):
            new = publish_kb.config_with_section("sections:\n  - id: skills\n", self.SNIPPET)
        self.assertEqual(new, "sections:\n  - id: skills\n  - id: components\n    path: components\n")
        self.assertIn("no `frontmatter:` key", out.getvalue())
        self.assertEqual(publish_kb.config_with_section(new, self.SNIPPET), new)


class NewComponentAgents(unittest.TestCase):
    def test_agents_group_scaffolds_a_python_agent_with_its_agent_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "tools")); shutil.copy(os.path.join(ROOT, "tools", "new_component.py"), os.path.join(tmp, "tools"))
            shutil.copytree(os.path.join(ROOT, "components", "_template"), os.path.join(tmp, "components", "_template"))
            r = subprocess.run([sys.executable, os.path.join(tmp, "tools", "new_component.py"), "agents", "my-agent", "--category", "agent", "--summary", "One line"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            d = os.path.join(tmp, "components", "agents", "my-agent")
            m = json.load(open(os.path.join(d, "component.json")))
            self.assertEqual(m["agent"], {"template": "TEMPLATE.md", "tools": ["untrusted-input-guard"], "harness": "governed-action-loop"})
            self.assertEqual((m["language"], m["example"]["path"], m["example"]["run"]), ("python", "example.py", "python3 example.py"))
            self.assertEqual(m["test"], "python3 -m unittest discover -s tests -t . -v")
            for f in ("TEMPLATE.md", "README.md", "WALKTHROUGH.md", "example.py", os.path.join("tests", "test_smoke.py")):
                self.assertTrue(os.path.exists(os.path.join(d, f)), f)


if __name__ == "__main__":
    unittest.main()
