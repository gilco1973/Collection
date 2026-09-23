"""The two pages in pages/: the interface page is the current static/ replaying the recorded session, and
neither page reaches anything outside itself."""
import importlib.util
import json
import os
import re
import unittest

from tests.helpers import ROOT
from aiplayground import __version__
from aiplayground import probes as P

PAGES = os.path.join(ROOT, "pages")
TOOLS = os.path.join(ROOT, "tools", "pages")
URL = re.compile(r"https?://[^\s\"'<>)]+")
PLACEHOLDER_HOST = re.compile(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?(/|$)|^https?://([a-z0-9-]+\.)*example(\.[a-z]+)?(:\d+)?(/|$)")


def read(*path):
    with open(os.path.join(*path), encoding="utf-8") as f:
        return f.read()


class Pages(unittest.TestCase):
    def test_interface_page_is_built_from_the_current_static_files(self):
        spec = importlib.util.spec_from_file_location("pages_build", os.path.join(TOOLS, "build.py"))
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        self.assertEqual(read(PAGES, "interface.html"), build.build(),
                         "pages/interface.html is stale: run python3 tools/pages/build.py")

    def test_recorded_session_matches_this_playground(self):
        fx = json.loads(read(TOOLS, "fixtures.json"))
        self.assertEqual(fx["meta"]["version"], __version__, "record again: python3 tools/pages/record.py")
        self.assertEqual(fx["probes"], json.loads(json.dumps(P.catalog())), "record again: python3 tools/pages/record.py")

    def test_pages_link_only_to_each_other_and_placeholders(self):
        explainer = read(PAGES, "explainer.html")
        self.assertEqual(URL.findall(explainer), [])
        self.assertIn('href="interface.html"', explainer)
        for url in URL.findall(read(PAGES, "interface.html")):
            self.assertRegex(url, PLACEHOLDER_HOST)

    def test_pages_load_nothing_from_outside(self):
        for name in ("explainer.html", "interface.html"):
            page = read(PAGES, name)
            self.assertNotRegex(page, r"<(script|link|img|iframe)[^>]+(src|href)=\"(https?:)?//", name)
            self.assertIn('<meta charset="utf-8">', page, name)


if __name__ == "__main__":
    unittest.main()
