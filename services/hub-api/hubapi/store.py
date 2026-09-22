"""The record: SQLite, one file, JSON documents in typed tables. A restart restores everything but the streams.

Briefs, requests, sign-offs, preferences, conversations and idempotency replays. Sign-offs recorded here are
requests until the shelf tool writes them into the manifests and the commit makes them a record; the export
endpoint hands them over.
"""
from __future__ import annotations
import json, sqlite3, threading, time

# The schema is versioned with SQLite's user_version. Each migration runs once, in order, inside a transaction; a
# record written by a newer build is refused rather than misread (fail closed), so a rollback needs a restore.
MIGRATIONS: list[str] = [
    """
CREATE TABLE IF NOT EXISTS docs (kind TEXT NOT NULL, id TEXT NOT NULL, owner TEXT, doc TEXT NOT NULL, updated REAL NOT NULL, PRIMARY KEY (kind, id));
CREATE INDEX IF NOT EXISTS docs_owner ON docs (kind, owner);
CREATE TABLE IF NOT EXISTS idempotency (key TEXT PRIMARY KEY, principal TEXT NOT NULL, status INTEGER NOT NULL, ctype TEXT NOT NULL, body BLOB NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS feedback (conversation TEXT NOT NULL, seq INTEGER NOT NULL, answered INTEGER NOT NULL, principal TEXT NOT NULL, at REAL NOT NULL);
""",
    "CREATE INDEX IF NOT EXISTS idempotency_created ON idempotency (created);",
    # Replays belong to one person and one call: the key alone was the primary key, so another person's key could evict yours.
    """CREATE TABLE idempotency_v2 (principal TEXT NOT NULL, key TEXT NOT NULL, route TEXT NOT NULL DEFAULT '', status INTEGER NOT NULL, ctype TEXT NOT NULL, body BLOB NOT NULL, created REAL NOT NULL, PRIMARY KEY (principal, key));
INSERT INTO idempotency_v2 (principal, key, status, ctype, body, created) SELECT principal, key, status, ctype, body, created FROM idempotency;
DROP TABLE idempotency;
ALTER TABLE idempotency_v2 RENAME TO idempotency;
CREATE INDEX IF NOT EXISTS idempotency_created ON idempotency (created);""",
]
SCHEMA_VERSION = len(MIGRATIONS)


class StoreError(Exception):
    pass


class Store:
    def __init__(self, path: str = ":memory:", idempotency_ttl_s: int = 86_400):
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL") if path != ":memory:" else None
        self.lock = threading.RLock()
        self.ttl = idempotency_ttl_s
        self._prunes = 0
        self.migrate()
        # One process owns the file: a placeholder (status 0) still here at start was claimed by a call that never
        # answered (the process died mid-call); left alone it would answer 409 in_progress until the TTL prunes it.
        with self.lock:
            self.conn.execute("DELETE FROM idempotency WHERE status = 0")

    def version(self) -> int:
        return int(self.conn.execute("PRAGMA user_version").fetchone()[0])

    def migrate(self) -> int:
        """Brings the record to this build's schema; returns the migrations applied."""
        v = self.version()
        if v > SCHEMA_VERSION:
            raise StoreError(f"the record is at schema version {v}; this build knows {SCHEMA_VERSION}. Restore the record or roll the build forward")
        applied = 0
        with self.lock:
            for i in range(v, SCHEMA_VERSION):
                # executescript commits anything pending first, then runs the script: the transaction lives inside it.
                self.conn.executescript(f"BEGIN;\n{MIGRATIONS[i]}\nPRAGMA user_version = {i + 1};\nCOMMIT;")
                applied += 1
        return applied

    def ping(self) -> None:
        """Proves the record is readable and writable; raises when it is not."""
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE"); self.conn.execute("ROLLBACK")

    def backup(self, path: str) -> int:
        """A consistent copy of the record at `path` (SQLite's online backup); returns the pages copied."""
        dest = sqlite3.connect(path)
        try:
            with self.lock:
                self.conn.backup(dest)
            return int(dest.execute("PRAGMA page_count").fetchone()[0])
        finally:
            dest.close()

    @staticmethod
    def backup_file(src_path: str, dest_path: str) -> int:
        """The backup command's copy: the source is opened read-only, so backing up never migrates (or creates) the
        live record; whatever schema version the file is at is what the copy carries. Returns the pages copied."""
        src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
        try:
            dest = sqlite3.connect(dest_path)
            try:
                src.backup(dest)
                return int(dest.execute("PRAGMA page_count").fetchone()[0])
            finally:
                dest.close()
        finally:
            src.close()

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
            row = self.conn.execute("SELECT status, ctype, body, route FROM idempotency WHERE principal = ? AND key = ?", (principal, key)).fetchone()
        return (row[0], row[1], row[2], row[3]) if row else None

    def reserve(self, key: str, principal: str, route: str = "") -> bool:
        """Claims a key before its call runs (status 0 marks the answer as pending); False when the key is already held."""
        with self.lock:
            return self.conn.execute("INSERT OR IGNORE INTO idempotency (principal, key, route, status, ctype, body, created) VALUES (?, ?, ?, 0, '', X'', ?)", (principal, key, route, time.time())).rowcount == 1

    def forget(self, key: str, principal: str) -> None:
        """Releases a reserved key whose call produced no answer to replay (a problem, a defect, a stream)."""
        with self.lock:
            self.conn.execute("DELETE FROM idempotency WHERE principal = ? AND key = ?", (principal, key))

    def abandon(self, key: str, principal: str, older_than_s: float, now: float | None = None) -> bool:
        """Releases a placeholder claimed more than `older_than_s` ago and never answered: the call that held it died
        (a crash between reserve and remember or forget). True when the key is free again; False when a call still holds it."""
        with self.lock:
            cur = self.conn.execute("DELETE FROM idempotency WHERE principal = ? AND key = ? AND status = 0 AND created < ?", (principal, key, (now or time.time()) - older_than_s))
            return cur.rowcount == 1

    def remember(self, key: str, principal: str, status: int, ctype: str, body: bytes, route: str = "") -> None:
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO idempotency (principal, key, route, status, ctype, body, created) VALUES (?, ?, ?, ?, ?, ?, ?)", (principal, key, route, status, ctype, body, time.time()))
            self._prunes += 1
            if self._prunes % 100 == 0:
                self.prune()

    def prune_docs(self, kind: str, older_than_s: float, now: float | None = None) -> int:
        """Deletes documents of a kind not updated within the window, and the feedback rows of a conversation with them."""
        cutoff = (now or time.time()) - older_than_s
        with self.lock:
            if kind == "conversation":
                self.conn.execute("DELETE FROM feedback WHERE conversation IN (SELECT id FROM docs WHERE kind = ? AND updated < ?)", (kind, cutoff))
            return self.conn.execute("DELETE FROM docs WHERE kind = ? AND updated < ?", (kind, cutoff)).rowcount

    def prune(self, now: float | None = None) -> int:
        """Forgets replays older than the TTL; a client that retries a day later gets a fresh answer, not a stale one."""
        with self.lock:
            cur = self.conn.execute("DELETE FROM idempotency WHERE created < ?", ((now or time.time()) - self.ttl,))
            return cur.rowcount

    def feedback_for(self, conversation: str) -> list[dict]:
        """What was answered on this conversation, by view sequence (the last answer per view)."""
        with self.lock:
            rows = self.conn.execute("SELECT seq, answered FROM feedback WHERE conversation = ? ORDER BY at", (conversation,)).fetchall()
        latest: dict[int, bool] = {}
        for seq, answered in rows: latest[int(seq)] = bool(answered)
        return [{"seq": s, "answered": a} for s, a in sorted(latest.items())]

    def feedback(self, conversation: str, seq: int, answered: bool, principal: str) -> None:
        with self.lock:
            self.conn.execute("INSERT INTO feedback (conversation, seq, answered, principal, at) VALUES (?, ?, ?, ?, ?)", (conversation, seq, int(answered), principal, time.time()))

    def close(self) -> None:
        self.conn.close()
