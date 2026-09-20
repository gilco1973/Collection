"""The retriever (embed a question, query the index) and reciprocal rank fusion."""

from collections.abc import Collection, Iterable
from dataclasses import dataclass

from kb_librarian.retrieval.embedder import Embedder
from kb_librarian.retrieval.index import Hit, VectorIndex

RRF_K = 60


@dataclass
class Retriever:
    index: VectorIndex
    embedder: Embedder

    def search(self, query: str, limit: int, allowed_paths: Collection[str]) -> list[Hit]:
        """Best chunk per page for ``query`` among ``allowed_paths`` only — the caller's readable view,
        required on every call so no search can be wider than the reader's own catalog. A blank
        query embeds nothing and finds nothing."""
        if not query.strip():
            return []
        vector = self.embedder.embed([query.strip()])[0]
        return self.index.query(vector, limit, allowed_paths)


def rrf(keyword_paths: Iterable[str], semantic_paths: Iterable[str], k: int = RRF_K) -> list[str]:
    """Reciprocal rank fusion of two orders: every path scores ``sum(1 / (k + rank))`` over the lists
    it appears in (first occurrence per list), best first; ties keep first-seen order."""
    scores: dict[str, float] = {}
    for ranked in (keyword_paths, semantic_paths):
        seen: set[str] = set()
        for rank, path in enumerate(ranked, start=1):
            if path in seen:
                continue
            seen.add(path)
            scores[path] = scores.get(path, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda path: -scores[path])
