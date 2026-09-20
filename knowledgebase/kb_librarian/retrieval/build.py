"""Build (and refresh) the embedding index from the catalog: ``kb-librarian index --embeddings``."""

from dataclasses import dataclass
from pathlib import Path

from kb_librarian.catalog.catalog import load_catalog
from kb_librarian.kbconfig import KbConfig
from kb_librarian.retrieval.chunks import chunk_document
from kb_librarian.retrieval.embedder import Embedder
from kb_librarian.retrieval.index import VectorIndex

INDEX_DIR = ".librarian/index"
INDEX_FILE = "embeddings.sqlite"


@dataclass(frozen=True)
class BuildStats:
    embedded: int  # chunks sent to the embedder (new or changed)
    unchanged: int  # chunks whose hash the index already held
    removed: int  # chunks pruned (page gone, section renamed or merged)
    pages: int  # pages chunked

    @property
    def line(self) -> str:
        return (
            f"embeddings: {self.embedded} embedded, {self.unchanged} unchanged, "
            f"{self.removed} removed, {self.pages} pages"
        )


def index_path(root: Path) -> Path:
    return root / INDEX_DIR / INDEX_FILE


def build_index(root: Path, config: KbConfig, embedder: Embedder, *, out: Path | None = None) -> BuildStats:
    """Chunk every page in the catalog — withheld ones included — embed the chunks whose text changed,
    and prune what is no longer there. Idempotent: a second run embeds nothing.

    Withholding is not decided at build time: a page's sensitive verdict can change with an audit or an
    edit without a rebuild, so the index holds every page and every query applies the caller's
    ``allowed_paths`` (``VectorIndex.query``). A model change (a different ``model_id``) starts the index
    over, since vectors from two models are not comparable.
    """
    target = out or index_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    index = VectorIndex(target)
    stored_model = index.stats().model_id
    if stored_model and stored_model != embedder.model_id:
        index.prune(set())
    catalog = load_catalog(root, config)
    chunks = [chunk for doc in catalog.documents for chunk in chunk_document(doc)]
    stale = index.stale(chunks)
    vectors = embedder.embed([chunk.text for chunk in stale]) if stale else []
    index.upsert(stale, vectors, embedder.model_id)
    removed = index.prune({chunk.path for chunk in chunks}, {chunk.id for chunk in chunks})
    return BuildStats(
        embedded=len(stale), unchanged=len(chunks) - len(stale), removed=removed, pages=len(catalog.documents)
    )
