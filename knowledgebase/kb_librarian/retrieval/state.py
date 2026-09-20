"""Serving-side glue: a retriever for a root when its index file exists, and the API's semantic pass."""

import logging
import sqlite3
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

from kb_librarian.catalog.catalog import Catalog
from kb_librarian.config import LibrarianSettings
from kb_librarian.retrieval.build import index_path
from kb_librarian.retrieval.embedder import EmbedError, embedder_from_settings
from kb_librarian.retrieval.index import Hit, VectorIndex
from kb_librarian.retrieval.retriever import Retriever

API_SEMANTIC_LIMIT = 20
SEMANTIC_WINDOW_S, SEMANTIC_PER_WINDOW = 60.0, 30
log = logging.getLogger(__name__)


def retriever_for(root: Path, settings: LibrarianSettings) -> Retriever | None:
    """A retriever over ``.librarian/index/embeddings.sqlite``, or ``None`` when no index was built."""
    path = index_path(root)
    return Retriever(VectorIndex(path), embedder_from_settings(settings)) if path.is_file() else None


@dataclass
class RetrieverCache:
    """The API's lazily built retriever, re-created when the index file changes (the nightly build)."""

    _retriever: Retriever | None = None
    _mtime_ns: int | None = None

    def get(self, root: Path, settings: LibrarianSettings) -> Retriever | None:
        try:
            mtime_ns = index_path(root).stat().st_mtime_ns  # one call: no check-then-stat race with a rebuild
        except OSError:
            self._retriever, self._mtime_ns = None, None
            return None
        if self._retriever is None or mtime_ns != self._mtime_ns:
            self._retriever, self._mtime_ns = retriever_for(root, settings), mtime_ns
        return self._retriever


@dataclass
class SemanticThrottle:
    """Per-client ceiling on embedder calls from the search box (any role, unauthenticated). Beyond it a
    search is answered by keyword, never refused: the ceiling bounds what one caller can spend at the
    embedding provider, not whether they can search."""

    window_s: float = SEMANTIC_WINDOW_S
    limit: int = SEMANTIC_PER_WINDOW
    _windows: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def allow(self, client: str) -> bool:
        now = time.monotonic()
        with self._lock:
            idle = [k for k, w in self._windows.items() if k != client and (not w or now - w[-1] > self.window_s)]
            for key in idle:
                del self._windows[key]  # buckets never outlive their window, whatever the number of clients
            window = self._windows[client]
            while window and now - window[0] > self.window_s:
                window.popleft()
            if len(window) >= self.limit:
                return False
            window.append(now)
            return True


_throttle = SemanticThrottle()


def semantic_hits(
    retriever: Retriever | None, catalog: Catalog, query: str, withheld: set[str], client: str | None = None
) -> list[Hit] | None:
    """The semantic order for ``/api/search``: ``None`` when nothing semantic happened (no retriever, a
    blank query, a client over the throttle, an embedder or index failure — search then degrades to
    keyword and says so). The allowed paths are the catalog's readable pages: withheld ones are excluded
    inside the index query."""
    if retriever is None or not query.strip() or (client is not None and not _throttle.allow(client)):
        return None
    allowed = {doc.rel_path for doc in catalog.documents} - withheld
    try:
        return retriever.search(query, API_SEMANTIC_LIMIT, allowed)
    except EmbedError as exc:
        log.warning("semantic search unavailable, answering by keyword: %s", exc)
    except sqlite3.Error as exc:  # a rebuild in progress or a damaged file: the type says enough
        log.warning("embedding index unreadable, answering by keyword: %s", type(exc).__name__)
    return None
