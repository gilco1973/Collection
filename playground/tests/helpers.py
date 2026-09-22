"""Shared fixtures: the demo servers on free ports, temporary directories, target files."""
import contextlib
import json
import os
import shutil
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXAMPLES = os.path.join(ROOT, "examples")
sys.path.insert(0, ROOT)

from aiplayground import config as C  # noqa: E402
from aiplayground import demo  # noqa: E402


@contextlib.contextmanager
def demo_server(vulnerable=False):
    httpd = demo.make_server(0, vulnerable)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def target(**kw):
    raw = {"name": "t", "environment": "sandbox"}
    raw.update(kw)
    return C.load(raw)


@contextlib.contextmanager
def tempdir():
    d = tempfile.mkdtemp(prefix="pgtest-")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content if isinstance(content, str) else json.dumps(content, indent=2))
    return path
