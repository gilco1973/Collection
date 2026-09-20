"""An in-process hub API for the tests: mock personas, the example data, the fake assistant, a memory record."""
from __future__ import annotations
import json, os, threading, urllib.error, urllib.request
from hubapi.app import HubApi, serve
from hubapi.assistant import FakeAssistant
from hubapi.auth import MockAuth
from hubapi.catalog import Catalog
from hubapi.settings import SERVICE, Settings
from hubapi.store import Store

DATA = os.path.join(SERVICE, "data")


def make_api(auth=None, assistant=None, settings=None, guide=None) -> HubApi:
    from hubapi.guide import Corpus, Guide
    s = settings or Settings()
    catalog = Catalog.load(os.path.join(DATA, "consumers.example.json"), os.path.join(DATA, "collection.json"))
    personas = json.load(open(os.path.join(DATA, "examples.json")))["principals"]
    return HubApi(s, Store(":memory:"), catalog, auth or MockAuth(personas), assistant or FakeAssistant(), guide or Guide(Corpus.load(os.path.join(DATA, "guide-corpus.json"))))


class Client:
    """Calls `api.handle` directly: no socket, same code path as the server."""

    def __init__(self, api: HubApi, token: str | None):
        self.api, self.token = api, token

    def call(self, method: str, path: str, body=None, headers: dict | None = None):
        h = {"Content-Type": "application/json", **(headers or {})}
        if self.token: h["Authorization"] = f"Bearer {self.token}"
        res = self.api.handle(method, path, h, json.dumps(body).encode() if body is not None else b"")
        if hasattr(res, "events"):
            events = list(res.events); res.done(False)
            return 200, events
        status, _, raw = res
        return status, (json.loads(raw) if raw else None)


class HttpServer:
    def __init__(self, api: HubApi, static_dir: str = ""):
        self.httpd = serve(api, "127.0.0.1", 0, static_dir)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def request(self, method: str, path: str, body=None, token: str | None = "mock.gk", headers: dict | None = None):
        h = {"Content-Type": "application/json", **(headers or {})}
        if token: h["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None, headers=h, method=method)
        try:
            return urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError as e:
            return e

    def close(self):
        self.httpd.shutdown()
