"""Chunk vectors in one sqlite file, cosine similarity in pure Python.

A knowledge base of a few thousand chunks needs no vector database; the interface (``upsert``,
``stale``, ``prune``, ``query``, ``stats``) allows one later. Every operation opens its own
connection, so the index is safe to share between threadpool workers without a lock.
"""

import math
import sqlite3
from array import array
from collections.abc import Collection, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from kb_librarian.retrieval.chunks import Chunk

EXCERPT_CHARS = 300
_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY, path TEXT NOT NULL, heading TEXT NOT NULL, excerpt TEXT NOT NULL,
  hash TEXT NOT NULL, model TEXT NOT NULL, dim INTEGER NOT NULL, vector BLOB NOT NULL);
CREATE INDEX IF NOT EXISTS chunks_path ON chunks (path);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    path: str
    heading: str
    excerpt: str
    score: float


@dataclass(frozen=True)
class IndexStats:
    chunks: int
    pages: int
    model_id: str
    updated_at: str | None


def excerpt_of(text: str) -> str:
    return " ".join(text.split())[:EXCERPT_CHARS]


def _cosine(query: list[float], query_norm: float, blob: bytes) -> float:
    stored = array("f")
    stored.frombytes(blob)
    if len(stored) != len(query):  # a vector from another model: never comparable
        return 0.0
    norm = math.sqrt(sum(v * v for v in stored))
    if not norm:
        return 0.0
    return sum(q * v for q, v in zip(query, stored, strict=True)) / (query_norm * norm)


class VectorIndex:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def _connect(self, write: bool = False) -> Iterator[sqlite3.Connection]:
        fresh = not self.path.is_file()
        connection = sqlite3.connect(self.path)
        try:
            if write or fresh:  # a reader never runs the schema script (a write statement)
                connection.executescript(_SCHEMA)
            yield connection
            connection.commit()
        finally:
            connection.close()

    def upsert(self, chunks: list[Chunk], vectors: list[list[float]], model_id: str) -> None:
        rows = [
            (c.id, c.path, c.heading, excerpt_of(c.text), c.hash, model_id, len(v), array("f", v).tobytes())
            for c, v in zip(chunks, vectors, strict=True)
        ]
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        with self._connect(write=True) as connection:
            connection.executemany("INSERT OR REPLACE INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
            meta = [("model_id", model_id), ("updated_at", stamp)]
            connection.executemany("INSERT OR REPLACE INTO meta VALUES (?, ?)", meta)

    def stale(self, chunks: list[Chunk]) -> list[Chunk]:
        """The chunks whose id is unknown or whose stored hash differs: the ones to embed."""
        if not self.path.is_file():
            return list(chunks)
        with self._connect() as connection:
            known = dict(connection.execute("SELECT id, hash FROM chunks"))
        return [c for c in chunks if known.get(c.id) != c.hash]

    def prune(self, keep_paths: Collection[str], keep_ids: Collection[str] | None = None) -> int:
        """Remove every chunk whose page is not in ``keep_paths`` (and, when given, whose id is not in
        ``keep_ids`` — a section that was renamed or merged). Returns the number of chunks removed."""
        with self._connect(write=True) as connection:
            connection.execute("CREATE TEMP TABLE keep_path (path TEXT PRIMARY KEY)")
            connection.executemany("INSERT OR IGNORE INTO keep_path VALUES (?)", [(p,) for p in keep_paths])
            where = "path NOT IN (SELECT path FROM keep_path)"
            if keep_ids is not None:
                connection.execute("CREATE TEMP TABLE keep_id (id TEXT PRIMARY KEY)")
                connection.executemany("INSERT OR IGNORE INTO keep_id VALUES (?)", [(i,) for i in keep_ids])
                where += " OR id NOT IN (SELECT id FROM keep_id)"
            return connection.execute(f"DELETE FROM chunks WHERE {where}").rowcount

    def query(self, vector: list[float], limit: int, allowed_paths: Collection[str]) -> list[Hit]:
        """At most one hit per page (its best chunk), best first, only among ``allowed_paths`` — the
        restriction is a join inside the query, never a filter over a wider result. A zero or
        negative similarity is not a hit."""
        query_norm = math.sqrt(sum(v * v for v in vector))
        if not query_norm or not allowed_paths or not self.path.is_file():
            return []
        best: dict[str, Hit] = {}
        with self._connect() as connection:
            connection.execute("CREATE TEMP TABLE allowed (path TEXT PRIMARY KEY)")
            connection.executemany("INSERT OR IGNORE INTO allowed VALUES (?)", [(p,) for p in allowed_paths])
            rows = connection.execute(
                "SELECT c.id, c.path, c.heading, c.excerpt, c.vector FROM chunks c JOIN allowed a ON a.path = c.path"
            )
            for chunk_id, path, heading, excerpt, blob in rows:
                score = _cosine(vector, query_norm, blob)
                if score > 0 and (path not in best or score > best[path].score):
                    best[path] = Hit(chunk_id, path, heading, excerpt, score)
        return sorted(best.values(), key=lambda hit: (-hit.score, hit.path))[:limit]

    def stats(self) -> IndexStats:
        if not self.path.is_file():
            return IndexStats(chunks=0, pages=0, model_id="", updated_at=None)
        with self._connect() as connection:
            chunks, pages = connection.execute("SELECT COUNT(*), COUNT(DISTINCT path) FROM chunks").fetchone()
            meta = dict(connection.execute("SELECT key, value FROM meta"))
        return IndexStats(chunks, pages, model_id=meta.get("model_id", ""), updated_at=meta.get("updated_at"))
