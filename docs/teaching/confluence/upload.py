#!/usr/bin/env python3
"""Upload the teaching guide's pages to a Confluence space through its REST API. Standard library only.

    export CONFLUENCE_EMAIL=you@example.com CONFLUENCE_API_TOKEN=...      # Confluence Cloud (an API token)
    export CONFLUENCE_TOKEN=...                                          # or Server / Data Center (a personal access token)
    python3 upload.py --base https://your-site.example.net/wiki --space DOCS [--parent-id 123456] [--title-prefix "Hub: "]
    python3 upload.py ... --dry-run                                      # says what it would create or update, sends nothing

Reads pages.json beside this script. The index page is created under --parent-id (or at the space root), every
chapter under the index, and each page's images are attached to it. Running it again updates the pages in place
(a new version each time) and replaces attachments whose bytes changed, so a corrected guide is one more run.
Pages are found by title within the space, so keep --title-prefix the same between runs.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))


class ConfluenceError(Exception):
    pass


class Confluence:
    def __init__(self, base: str, auth: str, dry_run: bool = False, opener=None):
        self.base = base.rstrip("/")
        self.auth = auth
        self.dry_run = dry_run
        self.open = opener or urllib.request.urlopen

    def call(self, method: str, path: str, body=None, headers: dict | None = None, retries: int = 4):
        url = self.base + path
        data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode("utf-8")
        h = {"Authorization": self.auth, "Accept": "application/json", "X-Atlassian-Token": "nocheck"}
        if isinstance(body, dict):
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        for attempt in range(retries + 1):
            req = urllib.request.Request(url, data=data, method=method, headers=h)
            try:
                with self.open(req, timeout=60) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                text = e.read().decode("utf-8", "replace")[:500]
                if e.code in (429, 502, 503, 504) and attempt < retries:
                    wait = float(e.headers.get("Retry-After") or 2 ** attempt)
                    time.sleep(min(wait, 30))
                    continue
                raise ConfluenceError(f"{method} {path} -> HTTP {e.code}: {text}") from None
            except urllib.error.URLError as e:
                if attempt < retries:
                    time.sleep(2 ** attempt)
                    continue
                raise ConfluenceError(f"{method} {path} -> {e.reason}") from None

    # pages --------------------------------------------------------------------------------------------------------
    def find_page(self, space: str, title: str):
        q = urllib.parse.urlencode({"spaceKey": space, "title": title, "expand": "version", "status": "current"})
        found = self.call("GET", f"/rest/api/content?{q}").get("results") or []
        return found[0] if found else None

    PROPERTY = "collection-teaching-sha256"   # a content property on each page: the hash of the storage it was last given

    def put_page(self, space: str, title: str, storage: str, parent_id: str | None) -> tuple:
        """Create or update; returns (id, 'created'|'updated'|'unchanged', webui link). Confluence rewrites the storage it
        is given (macro ids, whitespace), so a page is 'unchanged' by the hash recorded in its content property."""
        existing = self.find_page(space, title)
        digest = hashlib.sha256(storage.encode("utf-8")).hexdigest()
        body = {"type": "page", "title": title, "space": {"key": space}, "body": {"storage": {"value": storage, "representation": "storage"}}}
        if parent_id:
            body["ancestors"] = [{"id": str(parent_id)}]
        if existing:
            if self.dry_run:
                return existing["id"], "updated", ""
            prop = self.get_property(existing["id"])
            if prop and prop.get("value") == digest:
                return existing["id"], "unchanged", self.link(existing)
            body["version"] = {"number": existing["version"]["number"] + 1, "minorEdit": True}
            page = self.call("PUT", f"/rest/api/content/{existing['id']}", body)
            self.set_property(page["id"], digest, prop)
            return page["id"], "updated", self.link(page)
        if self.dry_run:
            return f"dry-{uuid.uuid4().hex[:8]}", "created", ""
        page = self.call("POST", "/rest/api/content", body)
        self.set_property(page["id"], digest, None)
        return page["id"], "created", self.link(page)

    def get_property(self, page_id: str):
        try:
            return self.call("GET", f"/rest/api/content/{page_id}/property/{self.PROPERTY}", retries=0)
        except ConfluenceError as e:
            if "HTTP 404" in str(e):
                return None
            raise

    def set_property(self, page_id: str, digest: str, existing) -> None:
        if existing:
            self.call("PUT", f"/rest/api/content/{page_id}/property/{self.PROPERTY}",
                      {"value": digest, "version": {"number": existing["version"]["number"] + 1}})
        else:
            self.call("POST", f"/rest/api/content/{page_id}/property", {"key": self.PROPERTY, "value": digest})

    def link(self, page: dict) -> str:
        links = page.get("_links") or {}
        return (links.get("base") or self.base) + (links.get("webui") or "")

    # attachments --------------------------------------------------------------------------------------------------
    def put_attachment(self, page_id: str, path: str) -> str:
        name = os.path.basename(path)
        with open(path, "rb") as f:
            data = f.read()
        q = urllib.parse.urlencode({"filename": name, "expand": "version,metadata,extensions"})
        found = (self.call("GET", f"/rest/api/content/{page_id}/child/attachment?{q}") if not self.dry_run else {}).get("results") or []
        digest = hashlib.sha256(data).hexdigest()
        comment = (found[0].get("metadata") or {}).get("comment") or (found[0].get("extensions") or {}).get("comment") if found else None
        if comment == f"sha256:{digest}":
            return "unchanged"
        if self.dry_run:
            return "updated" if found else "uploaded"
        body, ctype = multipart(name, data, {"minorEdit": "true", "comment": f"sha256:{digest}"})
        if found:
            self.call("POST", f"/rest/api/content/{page_id}/child/attachment/{found[0]['id']}/data", body, {"Content-Type": ctype})
            return "updated"
        self.call("POST", f"/rest/api/content/{page_id}/child/attachment", body, {"Content-Type": ctype})
        return "uploaded"


def multipart(filename: str, data: bytes, fields: dict) -> tuple:
    boundary = "----collection-" + uuid.uuid4().hex
    ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    parts = []
    for k, v in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode("utf-8"))
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: {ctype}\r\n\r\n".encode("utf-8"))
    parts.append(data)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def auth_header(env=os.environ) -> str:
    if env.get("CONFLUENCE_TOKEN"):
        return "Bearer " + env["CONFLUENCE_TOKEN"]
    if env.get("CONFLUENCE_EMAIL") and env.get("CONFLUENCE_API_TOKEN"):
        return "Basic " + base64.b64encode(f"{env['CONFLUENCE_EMAIL']}:{env['CONFLUENCE_API_TOKEN']}".encode()).decode()
    raise ConfluenceError("set CONFLUENCE_EMAIL and CONFLUENCE_API_TOKEN (Cloud) or CONFLUENCE_TOKEN (Server / Data Center)")


def run(a, api: Confluence, manifest: dict, root: str, out=sys.stdout) -> int:
    def storage_of(entry):
        with open(os.path.join(root, entry["storage"]), encoding="utf-8") as f:
            return f.read()

    index = manifest["index"]
    try:
        index_id, state, link = api.put_page(a.space, a.title_prefix + index["title"], storage_of(index), a.parent_id)
    except ConfluenceError as e:
        print(f"FAILED    {a.title_prefix + index['title']}: {e}\nnothing else was sent: the chapters go under the index page", file=out)
        return 2
    print(f"{state:9s} {a.title_prefix + index['title']}  {link}", file=out)
    failures = 0
    for entry in manifest["pages"]:
        title = a.title_prefix + entry["title"]
        try:
            page_id, state, link = api.put_page(a.space, title, storage_of(entry), index_id)
            print(f"{state:9s} {title}  {link}", file=out)
            for rel in entry["attachments"]:
                what = api.put_attachment(page_id, os.path.join(root, rel))
                print(f"  {what:9s} {os.path.basename(rel)}", file=out)
        except ConfluenceError as e:
            failures += 1
            print(f"FAILED    {title}: {e}", file=out)
    if failures:
        print(f"{failures} page(s) failed; run again once the cause is fixed (pages already uploaded are updated in place)", file=out)
    return 1 if failures else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True, help="the site, e.g. https://your-site.example.net/wiki (Cloud keeps /wiki; Server and Data Center do not)")
    ap.add_argument("--space", required=True, help="the space key")
    ap.add_argument("--parent-id", default=None, help="the page to put the index under; the space root when omitted")
    ap.add_argument("--title-prefix", default="", help="prefixed to every title, for a space that already has pages with these names")
    ap.add_argument("--manifest", default=os.path.join(HERE, "pages.json"))
    ap.add_argument("--dry-run", action="store_true", help="say what would be created or updated; send nothing")
    a = ap.parse_args(argv)
    try:
        auth = auth_header()
        with open(a.manifest, encoding="utf-8") as f:
            manifest = json.load(f)
        api = Confluence(a.base, auth, dry_run=a.dry_run)
        return run(a, api, manifest, os.path.dirname(os.path.abspath(a.manifest)))
    except ConfluenceError as e:
        print(f"upload: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"upload: missing file: {e.filename} (run python3 docs/teaching/build_confluence.py first)", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
