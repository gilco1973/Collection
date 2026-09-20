"""The record: SQLite, one file, JSON documents in typed tables. A restart restores everything but the streams.

Briefs, requests, sign-offs, preferences, conversations and idempotency replays. Sign-offs recorded here are
requests until the shelf tool writes them into the manifests and the commit makes them a record; the export
endpoint hands them over.
"""
from __future__ import annotations
import json, sqlite3, threading, time

SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (kind TEXT NOT NULL, id TEXT NOT NULL, owner TEXT, doc TEXT NOT NULL, updated REAL NOT NULL, PRIMARY KEY (kind, id));
CREATE INDEX IF NOT EXISTS docs_owner ON docs (kind, owner);
CREATE TABLE IF NOT EXISTS idempotency (key TEXT PRIMARY KEY, principal TEXT NOT NULL, status INTEGER NOT NULL, ctype TEXT NOT NULL, body BLOB NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS feedback (conversation TEXT NOT NULL, seq INTEGER NOT NULL, answered INTEGER NOT NULL, principal TEXT NOT NULL, at REAL NOT NULL);
"""


class Store:
    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL") if path != ":memory:" else None
        self.conn.executescript(SCHEMA)
        self.lock = threading.RLock()

    # ---------------- documents ----------------
    def put(self, kind: str, id: str, doc: dict, owner: str | None = None) -> dict:
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO docs (kind, id, owner, doc, updated) VALUES (?, ?, ?, ?, ?)", (kind, id, owner, json.dumps(doc, ensure_ascii=False), time.time()))
        return doc

    def get(self, kind: str, id: str) -> dict | None:
        with self.lock:
            row = self.conn.execute("SELECT doc FROM docs WHERE kind = ? AND id = ?", (kind, id)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, kind: str, owner: str | None = None) -> list[dict]:
        with self.lock:
            rows = self.conn.execute("SELECT doc FROM docs WHERE kind = ? AND (? IS NULL OR owner = ?) ORDER BY updated DESC", (kind, owner, owner)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def delete(self, kind: str, id: str) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM docs WHERE kind = ? AND id = ?", (kind, id))

    def count(self, kind: str) -> int:
        with self.lock:
            return self.conn.execute("SELECT COUNT(*) FROM docs WHERE kind = ?", (kind,)).fetchone()[0]

    # ---------------- idempotency ----------------
    def replay(self, key: str, principal: str):
        with self.lock:
            row = self.conn.execute("SELECT status, ctype, body FROM idempotency WHERE key = ? AND principal = ?", (key, principal)).fetchone()
        return (row[0], row[1], row[2]) if row else None

    def remember(self, key: str, principal: str, status: int, ctype: str, body: bytes) -> None:
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO idempotency (key, principal, status, ctype, body, created) VALUES (?, ?, ?, ?, ?, ?)", (key, principal, status, ctype, body, time.time()))

    def feedback(self, conversation: str, seq: int, answered: bool, principal: str) -> None:
        with self.lock:
            self.conn.execute("INSERT INTO feedback (conversation, seq, answered, principal, at) VALUES (?, ?, ?, ?, ?)", (conversation, seq, int(answered), principal, time.time()))

    def close(self) -> None:
        self.conn.close()
