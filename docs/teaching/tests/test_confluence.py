"""The teaching guide's Confluence pages: the conversion keeps every sentence and construct, and the uploader
creates, updates and skips pages and attachments against a stand-in Confluence.

    python3 -m unittest discover -s docs/teaching/tests -t .
"""
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
import threading
import unittest
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
TEACHING = os.path.dirname(HERE)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build = load("build_confluence", os.path.join(TEACHING, "build_confluence.py"))
upload = load("upload", os.path.join(TEACHING, "confluence", "upload.py"))


class Conversion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.files = build.build()
        cls.pages = {p["title"]: cls.files[p["storage"]].decode("utf-8") for p in cls.manifest["pages"]}

    def test_one_page_per_chapter_in_order_with_unique_titles(self):
        titles = [p["title"] for p in self.manifest["pages"]]
        self.assertEqual(len(titles), 17)
        self.assertEqual(titles[0], "The words you will meet")
        self.assertEqual([t.split(".")[0] for t in titles[1:]], [str(i) for i in range(1, 17)])
        self.assertEqual(len(set(titles)), len(titles))
        self.assertEqual(self.manifest["index"]["title"], "Teaching the Collection")

    def test_every_page_is_well_formed_storage_format_without_inline_images(self):
        for entry in [self.manifest["index"]] + self.manifest["pages"]:
            xml = self.files[entry["storage"]].decode("utf-8")
            self.assertNotIn("data:image", xml, entry["title"])
            self.assertNotIn('class="', xml, entry["title"])          # nothing that Confluence would drop silently
            ET.fromstring(f'<r xmlns:ac="urn:ac" xmlns:ri="urn:ri">{xml.replace("&nbsp;", "&#160;")}</r>')

    def test_every_referenced_attachment_exists_and_every_attachment_is_referenced(self):
        for entry in self.manifest["pages"]:
            xml = self.files[entry["storage"]].decode("utf-8")
            referenced = set(re.findall(r'ri:filename="([^"]+)"', xml))
            have = {os.path.basename(a) for a in entry["attachments"]}
            self.assertEqual(referenced, have, entry["title"])
            for a in entry["attachments"]:
                self.assertGreater(len(self.files[a]), 1000, a)

    def test_screenshots_are_the_page_images_byte_for_byte(self):
        import base64
        with open(os.path.join(TEACHING, "teaching-the-collection.html"), encoding="utf-8") as f:
            html = f.read()
        embedded = {hashlib.sha256(base64.b64decode(m)).hexdigest() for m in re.findall(r'src="data:image/\w+;base64,([^"]+)"', html)}
        shipped = {hashlib.sha256(data).hexdigest() for rel, data in self.files.items() if rel.endswith(".jpg")}
        self.assertEqual(embedded, shipped)

    def test_no_sentence_of_the_guide_is_lost(self):
        """Every on-screen string and every table cell of the source is on exactly the page of its chapter."""
        with open(os.path.join(TEACHING, "teaching-the-collection.html"), encoding="utf-8") as f:
            root = build.parse(f.read())
        for section, entry in zip(root.first("main").find_all("section"), self.manifest["pages"]):
            page = re.sub(r'<ac:parameter ac:name="colour">[^<]*</ac:parameter>', "", self.files[entry["storage"]].decode("utf-8"))
            plain = re.sub(r"<[^>]+>", "", page).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            for span in section.find_all("span"):
                if "t" in span.classes():
                    self.assertIn(build.squash(span.text()).strip(), plain, f"{entry['title']}: {span.text()!r}")
            for td in section.find_all("td"):
                text = build.squash(td.text()).strip()
                if text:
                    self.assertIn(text[:60], plain, f"{entry['title']}: {text[:60]!r}")

    def test_the_constructs_are_mapped_not_dropped(self):
        listing = self.pages["4. A listing page"]
        self.assertIn('ac:name="status"', listing)
        self.assertIn('<ac:parameter ac:name="colour">Red</ac:parameter><ac:parameter ac:name="title">W2</ac:parameter>', listing)
        self.assertIn('ac:name="info"', listing)
        signoffs = self.pages["8. Build: sign-offs"]
        self.assertIn('ac:name="warning"', signoffs)
        self.assertIn("<![CDATA[python3 tools/shelf.py --apply-signoffs shelf-signoffs.json", signoffs)
        self.assertIn("<h3>If you are an owner</h3>", signoffs)
        brief = self.pages["7. Build: the intake brief"]
        self.assertIn('ac:name="anchor"', brief)
        self.assertIn("<h2>The composer: build from what exists</h2>", brief)
        self.assertEqual(brief.count("<ri:attachment"), 5)
        processes = self.pages["15. The processes, end to end"]
        self.assertEqual(processes.count("<ri:attachment"), 4)
        self.assertEqual(processes.count('ac:name="expand"'), 4)
        self.assertIn("flowchart LR", processes)
        lesson = self.pages["16. A 45-minute first lesson"]
        self.assertIn("<th>Minutes</th>", lesson)
        self.assertIn('ac:name="tip"', lesson)
        words = self.pages["The words you will meet"]
        self.assertEqual(words.count("<tr>"), 16)   # fifteen terms and the header row
        index = self.files["pages/index.xml"].decode("utf-8")
        self.assertIn('ac:name="children"', index)

    def test_markdown_copies_carry_the_tables_and_the_images(self):
        md = self.files["markdown/01-signing-in.md"].decode("utf-8")
        self.assertTrue(md.startswith("# 1. Signing in\n"))
        self.assertIn("| You see | It means |", md)
        self.assertIn("![", md)
        self.assertIn("1. **Open the hub", md)
        self.assertIn("```mermaid", self.files["markdown/15-the-processes-end-to-end.md"].decode("utf-8"))

    def test_the_diagram_parser_reads_labels_shapes_and_back_edges(self):
        nodes, edges = build.parse_flowchart("flowchart LR\n  A[Start<br/>two lines] --> B{Ask?}\n  B -- yes --> C[Yes]\n  B -- no --> D\n  C -. later .-> A\n")
        self.assertEqual(nodes["A"], (["Start", "two lines"], "box"))
        self.assertEqual(nodes["B"][1], "diamond")
        self.assertEqual(nodes["D"], (["D"], "box"))
        self.assertEqual(edges, [("A", "B", "", False), ("B", "C", "yes", False), ("B", "D", "no", False), ("C", "A", "later", True)])
        png = build.draw_flowchart("flowchart LR\n  A[One] --> B[Two]\n  B -. back .-> A\n")
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")

    def test_the_written_tree_is_current(self):
        problems = build.check(build.OUT, self.files)
        self.assertEqual(problems, [], "run python3 docs/teaching/build_confluence.py")


# --- a stand-in Confluence -----------------------------------------------------------------------------------------

class FakeConfluence(BaseHTTPRequestHandler):
    pages: dict = {}          # id -> {title, version, body, ancestors, properties: {key: {value, version}}}
    attachments: dict = {}    # page id -> {filename: {id, comment, bytes}}
    calls: list = []
    fail_next: list = []      # status codes to answer before behaving
    fail_title: str = ""      # a page whose create is refused with 403, once

    def log_message(self, *a):
        pass

    def send(self, code, payload=None):
        body = json.dumps(payload or {}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def do_GET(self):
        FakeConfluence.calls.append(("GET", self.path))
        if self.headers.get("Authorization") != "Bearer test-token":
            return self.send(401, {"message": "no"})
        path, _, query = self.path.partition("?")
        q = dict(urllib.parse.parse_qsl(query))
        if path == "/rest/api/content":
            hits = [dict(id=i, title=p["title"], version={"number": p["version"]}) for i, p in self.pages.items() if p["title"] == q.get("title")]
            return self.send(200, {"results": hits})
        m = re.match(r"/rest/api/content/(\w+)/property/([\w-]+)$", path)
        if m:
            prop = self.pages.get(m.group(1), {}).get("properties", {}).get(m.group(2))
            return self.send(200, {"key": m.group(2), "value": prop["value"], "version": {"number": prop["version"]}}) if prop else self.send(404, {"message": "no property"})
        m = re.match(r"/rest/api/content/(\w+)/child/attachment$", path)
        if m:
            atts = self.attachments.get(m.group(1), {})
            hit = atts.get(q.get("filename"))
            return self.send(200, {"results": [{"id": hit["id"], "metadata": {"comment": hit["comment"]}}] if hit else []})
        return self.send(404, {"message": "unknown"})

    def do_POST(self):
        FakeConfluence.calls.append(("POST", self.path))
        if self.fail_next:
            return self.send(self.fail_next.pop(0), {"message": "later"})
        raw = self.body()
        if self.path == "/rest/api/content":
            data = json.loads(raw)
            if data["title"] == FakeConfluence.fail_title:
                FakeConfluence.fail_title = ""
                return self.send(403, {"message": "you may not create pages here"})
            pid = str(1000 + len(self.pages))
            self.pages[pid] = {"title": data["title"], "version": 1, "body": data["body"]["storage"]["value"],
                               "ancestors": [a["id"] for a in data.get("ancestors", [])], "properties": {}}
            return self.send(200, {"id": pid, "title": data["title"], "version": {"number": 1}, "_links": {"base": "http://fake", "webui": f"/pages/{pid}"}})
        m = re.match(r"/rest/api/content/(\w+)/property$", self.path)
        if m:
            data = json.loads(raw)
            self.pages[m.group(1)]["properties"][data["key"]] = {"value": data["value"], "version": 1}
            return self.send(200, data)
        m = re.match(r"/rest/api/content/(\w+)/child/attachment(?:/(\w+)/data)?$", self.path)
        if m:
            if self.headers.get("X-Atlassian-Token") != "nocheck" or not self.headers.get("Content-Type", "").startswith("multipart/form-data"):
                return self.send(403, {"message": "XSRF"})
            filename = re.search(rb'filename="([^"]+)"', raw).group(1).decode()
            comment = re.search(rb'name="comment"\r\n\r\n([^\r]+)', raw).group(1).decode()
            file_bytes = raw.split(b"\r\n\r\n", 3)[3].rsplit(b"\r\n--", 1)[0]
            atts = self.attachments.setdefault(m.group(1), {})
            aid = m.group(2) or f"att{len(atts) + 1}"
            atts[filename] = {"id": aid, "comment": comment, "bytes": file_bytes}
            return self.send(200, {"results": [{"id": aid}]})
        return self.send(404, {"message": "unknown"})

    def do_PUT(self):
        FakeConfluence.calls.append(("PUT", self.path))
        data = json.loads(self.body())
        m = re.match(r"/rest/api/content/(\w+)/property/([\w-]+)$", self.path)
        if m:
            self.pages[m.group(1)]["properties"][m.group(2)] = {"value": data["value"], "version": data["version"]["number"]}
            return self.send(200, data)
        m = re.match(r"/rest/api/content/(\w+)$", self.path)
        if m and m.group(1) in self.pages:
            page = self.pages[m.group(1)]
            if data["version"]["number"] != page["version"] + 1:
                return self.send(409, {"message": "version conflict"})
            page.update(version=data["version"]["number"], body=data["body"]["storage"]["value"], title=data["title"])
            return self.send(200, {"id": m.group(1), "version": {"number": page["version"]}, "_links": {"base": "http://fake", "webui": f"/pages/{m.group(1)}"}})
        return self.send(404, {"message": "unknown"})


class Uploader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeConfluence)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.tmp = tempfile.mkdtemp()
        _manifest, files = build.build()
        build.write(cls.tmp, files)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        FakeConfluence.pages, FakeConfluence.attachments, FakeConfluence.calls, FakeConfluence.fail_next = {}, {}, [], []
        FakeConfluence.fail_title = ""

    def args(self, **kw):
        d = dict(space="DOCS", parent_id="77", title_prefix="")
        d.update(kw)
        return type("A", (), d)

    def run_upload(self, **kw):
        import io
        out = io.StringIO()
        with open(os.path.join(self.tmp, "pages.json")) as f:
            manifest = json.load(f)
        api = upload.Confluence(self.base, "Bearer test-token", dry_run=kw.pop("dry_run", False))
        code = upload.run(self.args(**kw), api, manifest, self.tmp, out=out)
        return code, out.getvalue()

    def test_first_run_creates_the_index_the_chapters_under_it_and_every_attachment(self):
        code, out = self.run_upload()
        self.assertEqual(code, 0, out)
        titles = {p["title"]: p for p in FakeConfluence.pages.values()}
        self.assertEqual(len(titles), 18)
        index = titles["Teaching the Collection"]
        self.assertEqual(index["ancestors"], ["77"])
        index_id = next(i for i, p in FakeConfluence.pages.items() if p is index)
        for title, page in titles.items():
            if title != "Teaching the Collection":
                self.assertEqual(page["ancestors"], [index_id], title)
        self.assertIn("<ri:attachment", titles["1. Signing in"]["body"])
        signin_id = next(i for i, p in FakeConfluence.pages.items() if p["title"] == "1. Signing in")
        att = FakeConfluence.attachments[signin_id]["01-signing-in-01.jpg"]
        with open(os.path.join(self.tmp, "attachments/01-signing-in/01-signing-in-01.jpg"), "rb") as f:
            self.assertEqual(att["bytes"], f.read())
        self.assertEqual(sum(len(a) for a in FakeConfluence.attachments.values()), 25)
        self.assertEqual(out.count("created"), 18)
        self.assertEqual(out.count("uploaded"), 25)

    def test_second_run_changes_nothing_and_a_corrected_page_gets_one_new_version(self):
        self.run_upload()
        code, out = self.run_upload()
        self.assertEqual(code, 0)
        self.assertEqual(out.count("unchanged"), 18 + 25)
        self.assertTrue(all(p["version"] == 1 for p in FakeConfluence.pages.values()))
        path = os.path.join(self.tmp, "pages/13-search.xml")
        with open(path, "a", encoding="utf-8") as f:
            f.write("<p>A correction.</p>")
        try:
            code, out = self.run_upload()
        finally:
            _m, files = build.build()
            with open(path, "wb") as f:
                f.write(files["pages/13-search.xml"])
        self.assertEqual(code, 0)
        search = next(p for p in FakeConfluence.pages.values() if p["title"] == "13. Search")
        self.assertEqual(search["version"], 2)
        self.assertIn("A correction.", search["body"])
        self.assertEqual(out.count("updated"), 1)

    def test_a_changed_attachment_is_replaced_in_place_not_added_beside_the_old_one(self):
        self.run_upload()
        path = os.path.join(self.tmp, "attachments/01-signing-in/01-signing-in-01.jpg")
        with open(path, "rb") as f:
            original = f.read()
        with open(path, "wb") as f:
            f.write(original + b"\x00")
        try:
            code, out = self.run_upload()
        finally:
            with open(path, "wb") as f:
                f.write(original)
        self.assertEqual(code, 0)
        signin_id = next(i for i, p in FakeConfluence.pages.items() if p["title"] == "1. Signing in")
        self.assertEqual(list(FakeConfluence.attachments[signin_id]), ["01-signing-in-01.jpg"])
        self.assertEqual(FakeConfluence.attachments[signin_id]["01-signing-in-01.jpg"]["bytes"], original + b"\x00")
        self.assertIn("  updated   01-signing-in-01.jpg", out)

    def test_title_prefix_and_a_transient_503_are_handled(self):
        FakeConfluence.fail_next = [503]
        code, out = self.run_upload(title_prefix="AI hub: ")
        self.assertEqual(code, 0, out)
        self.assertTrue(all(p["title"].startswith("AI hub: ") for p in FakeConfluence.pages.values()))

    def test_dry_run_sends_no_write(self):
        code, out = self.run_upload(dry_run=True)
        self.assertEqual(code, 0)
        self.assertEqual(FakeConfluence.pages, {})
        self.assertEqual([c for c in FakeConfluence.calls if c[0] != "GET"], [])
        self.assertEqual(out.count("created"), 18)

    def test_a_refused_page_is_reported_and_the_rest_still_go_up(self):
        FakeConfluence.fail_title = "2. The top bar and the footer"   # 403 is final, not retried
        code, out = self.run_upload()
        self.assertEqual(code, 1)
        self.assertIn("FAILED    2. The top bar and the footer", out)
        self.assertIn("HTTP 403", out)
        self.assertEqual(len(FakeConfluence.pages), 17)
        self.assertIn("1 page(s) failed", out)
        code, out = self.run_upload()   # the next run creates the one that failed and leaves the rest alone
        self.assertEqual(code, 0)
        self.assertEqual(len(FakeConfluence.pages), 18)
        self.assertEqual(out.count("created"), 1)

    def test_a_refused_index_stops_the_run_before_any_chapter(self):
        FakeConfluence.fail_title = "Teaching the Collection"
        code, out = self.run_upload()
        self.assertEqual(code, 2)
        self.assertEqual(FakeConfluence.pages, {})
        self.assertIn("nothing else was sent", out)

    def test_auth_header_forms(self):
        self.assertEqual(upload.auth_header({"CONFLUENCE_TOKEN": "pat"}), "Bearer pat")
        self.assertTrue(upload.auth_header({"CONFLUENCE_EMAIL": "a@example.com", "CONFLUENCE_API_TOKEN": "t"}).startswith("Basic "))
        with self.assertRaises(upload.ConfluenceError):
            upload.auth_header({})


if __name__ == "__main__":
    unittest.main()
