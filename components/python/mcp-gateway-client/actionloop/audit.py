"""Audit chain: hash-chained records in SQLite, one format for every consumer.

Each record carries whatever fields the caller passes (chain, tool, tier, decision, model context, taint,
traceparent, session, trace and span ids), plus `prev` and `hash`. `verify()` walks the chain; `export()`
writes JSON lines with the chain head as the evidence export for an operate report.
"""
from __future__ import annotations
import hashlib, json, sqlite3, time
from dataclasses import dataclass


class AuditError(Exception):
    pass


GENESIS = "sha256:" + "0" * 64


class AuditChain:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        conn.execute("""CREATE TABLE IF NOT EXISTS audit (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, prev TEXT NOT NULL, hash TEXT NOT NULL, ts REAL NOT NULL,
            consumer TEXT, env TEXT, event TEXT, tool TEXT, tier TEXT, decision TEXT, deny_code TEXT,
            body TEXT NOT NULL)""")
        conn.commit()

    def head(self) -> str:
        row = self.conn.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        return row[0] if row else GENESIS

    def record(self, **fields) -> int:
        """Append one record. Returns its seq. Everything not a column goes into the JSON body."""
        prev = self.head()
        body = {k: v for k, v in fields.items()}
        body["ts"] = time.time()
        body["prev"] = prev
        h = "sha256:" + hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
        cur = self.conn.execute(
            "INSERT INTO audit(prev,hash,ts,consumer,env,event,tool,tier,decision,deny_code,body) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (prev, h, body["ts"], fields.get("consumer"), fields.get("env"), fields.get("event"), fields.get("tool"),
             fields.get("tier"), fields.get("decision"), fields.get("deny_code"), json.dumps(body, sort_keys=True, default=str)))
        self.conn.commit()
        return cur.lastrowid

    def verify(self) -> int:
        """Walk the chain; raise AuditError on the first broken link; return the number of records."""
        prev, n = GENESIS, 0
        for seq, p, h, body in self.conn.execute("SELECT seq, prev, hash, body FROM audit ORDER BY seq"):
            if p != prev:
                raise AuditError(f"record {seq}: prev does not match the chain")
            if "sha256:" + hashlib.sha256(body.encode()).hexdigest() != h:
                raise AuditError(f"record {seq}: hash does not match its body")
            prev, n = h, n + 1
        return n

    def query(self, **where) -> list[dict]:
        cols = [k for k in where if k in ("consumer", "env", "event", "tool", "tier", "decision", "deny_code")]
        sql = "SELECT body FROM audit" + (" WHERE " + " AND ".join(f"{c}=?" for c in cols) if cols else "") + " ORDER BY seq"
        rows = self.conn.execute(sql, [where[c] for c in cols]).fetchall()
        out = [json.loads(r[0]) for r in rows]
        for k, v in where.items():
            if k not in cols:
                out = [o for o in out if o.get(k) == v]
        return out

    def export(self, path: str) -> dict:
        n = self.verify()
        with open(path, "w", encoding="utf-8") as f:
            for (body,) in self.conn.execute("SELECT body FROM audit ORDER BY seq"):
                f.write(body + "\n")
        return {"records": n, "head": self.head(), "path": path, "signed": False, "note": "unsigned evidence export; anchor the head with a KMS signature in production"}
