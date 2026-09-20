"""kb_librarian/retrieval: chunker, embedders, sqlite vector index, retriever and rank fusion (fakes only)."""

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from kb_librarian.catalog.catalog import Document
from kb_librarian.config import LibrarianSettings
from kb_librarian.retrieval.build import build_index, index_path
from kb_librarian.retrieval.chunks import chunk_document
from kb_librarian.retrieval.embedder import EmbedError, HashEmbedder, HttpEmbedder, embedder_from_settings
from kb_librarian.retrieval.index import VectorIndex
from kb_librarian.retrieval.retriever import Retriever, rrf

URL = "https://embed.example.test/v1/embeddings"


def _doc(path: str, body: str) -> Document:
    return Document(rel_path=path, path=Path(path), meta={"title": "T"}, body=body, section_id=None, raw=body)


class RecordingEmbedder(HashEmbedder):
    """The hash embedder, remembering every text it was asked to embed."""

    def __init__(self, dim: int = 1024):
        super().__init__(dim)
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return super().embed(texts)


def test_chunker_is_deterministic_and_heading_bounded():
    body = "Preamble line.\n\n# Title\n\nIntro text.\n## Getting credentials\nAsk the team.\n#### deep\n"
    body += "### Rotation\nYearly.\n"
    chunks = chunk_document(_doc("p.md", body))
    assert [c.id for c in chunks] == ["p.md#intro", "p.md#title", "p.md#getting-credentials", "p.md#rotation"]
    assert [c.heading for c in chunks] == ["T", "Title", "Getting credentials", "Rotation"]
    assert chunks[2].text == "## Getting credentials\nAsk the team.\n#### deep"  # a level-4 heading is not a boundary
    assert all(c.hash == hashlib.sha256(f"{c.heading}\n{c.text}".encode()).hexdigest() for c in chunks)
    retitled = _doc("p.md", body)
    retitled.meta["title"] = "Other"
    assert chunk_document(retitled)[0].hash != chunks[0].hash  # a title-only edit changes the intro chunk
    assert chunks == chunk_document(_doc("p.md", body))
    assert chunk_document(_doc("empty.md", "\n\n")) == []
    twice = chunk_document(_doc("d.md", "## Setup\none\n## Setup\ntwo\n"))
    assert [c.id for c in twice] == ["d.md#setup", "d.md#setup-2"]  # duplicate headings stay unique
    code = "## Install\n```bash\n# deps\npoetry install\n```\n~~~\n## not one\n~~~\n## Run\ngo\n"
    fenced = chunk_document(_doc("f.md", code))
    assert [c.id for c in fenced] == ["f.md#install", "f.md#run"]  # a heading-looking line in a code fence is code


def test_chunker_splits_an_over_long_section_at_paragraph_boundaries():
    paragraphs = [f"paragraph {n} " + "x" * 880 for n in range(5)]
    chunks = chunk_document(_doc("p.md", "## Big\n" + "\n\n".join(paragraphs)), max_chars=2000)
    assert [c.id for c in chunks] == ["p.md#big", "p.md#big-2", "p.md#big-3"]
    assert all(len(c.text) <= 2000 for c in chunks) and chunks[0].text.startswith("## Big\nparagraph 0")
    assert "\n\n".join(c.text for c in chunks) == "## Big\n" + "\n\n".join(paragraphs)
    hard = chunk_document(_doc("p.md", "## Wall\n" + "y" * 4500), max_chars=2000)
    assert [len(c.text) for c in hard] == [2000, 2000, 508]


def test_hash_embedder_is_normalised_deterministic_and_offline():
    embedder = HashEmbedder(dim=32)
    assert embedder.dim == 32 and embedder.model_id == "hash-32"
    one, same, other, empty = embedder.embed(["Api KEY rotation", "api key ROTATION", "unrelated words", ""])
    assert one == same and one != other and len(one) == 32
    assert abs(sum(x * x for x in one) - 1.0) < 1e-9 and empty == [0.0] * 32
    assert one == HashEmbedder(dim=32).embed(["api key rotation"])[0]  # a fresh process gives the same vector


def test_index_upsert_stale_prune_query_and_stats(tmp_path: Path):
    index, embedder = VectorIndex(tmp_path / "e.sqlite"), HashEmbedder(dim=256)
    assert index.stats().chunks == 0 and index.stats().model_id == "" and not (tmp_path / "e.sqlite").exists()
    chunks = chunk_document(_doc("a.md", "# A\napi credentials here\n## More\nrotation policy")) + chunk_document(
        _doc("b.md", "# B\nunrelated text about lunch")
    )
    assert index.stale(chunks) == chunks
    index.upsert(chunks, embedder.embed([c.text for c in chunks]), "hash-256")
    assert index.stale(chunks) == []
    stats = index.stats()
    assert (stats.chunks, stats.pages, stats.model_id) == (3, 2, "hash-256") and stats.updated_at
    changed = chunk_document(_doc("a.md", "# A\napi credentials here\n## More\nrotation policy changed"))
    assert [c.id for c in index.stale(changed)] == ["a.md#more"]
    query = embedder.embed(["api credentials"])[0]
    hits = index.query(query, 5, {"a.md", "b.md"})
    assert [h.path for h in hits] == ["a.md"] and hits[0].chunk_id == "a.md#a" and 0 < hits[0].score <= 1
    assert hits[0].excerpt == "# A api credentials here" and hits[0].heading == "A"
    assert index.query(query, 5, {"b.md"}) == [] and index.query(query, 5, set()) == []  # filtered inside the query
    assert len(index.query(embedder.embed(["api rotation lunch"])[0], 5, {"a.md", "b.md"})) == 2  # one hit per page
    assert index.query(embedder.embed(["nothing"])[0], 5, {"a.md", "b.md"}) == []  # no overlap: no hit
    assert index.prune({"b.md"}) == 2 and index.stats().pages == 1
    assert index.prune({"b.md"}, keep_ids=set()) == 1 and index.stats().chunks == 0


def test_build_index_embeds_only_changed_chunks_and_keeps_withheld_pages_indexed(kb_root: Path, kb_config):
    embedder = RecordingEmbedder()
    stats = build_index(kb_root, kb_config, embedder)
    assert (stats.embedded, stats.unchanged, stats.removed, stats.pages) == (4, 0, 0, 4)
    assert index_path(kb_root).is_file() and len(embedder.calls) == 1 and len(embedder.calls[0]) == 4
    assert build_index(kb_root, kb_config, embedder).embedded == 0 and len(embedder.calls) == 1  # idempotent
    page = kb_root / "docs/governance/README.md"
    page.write_text(page.read_text() + "\n## Reviews\nEvery quarter.\n", encoding="utf-8")
    stats = build_index(kb_root, kb_config, embedder)
    assert (stats.embedded, stats.unchanged) == (1, 4) and embedder.calls[-1] == ["## Reviews\nEvery quarter."]
    (kb_root / "docs/onboarding/README.md").unlink()
    stats = build_index(kb_root, kb_config, embedder)
    assert (stats.removed, stats.pages) == (1, 3) and VectorIndex(index_path(kb_root)).stats().pages == 3
    # the withheld page is in the index (withholding is enforced by allowed_paths on every query)
    index = VectorIndex(index_path(kb_root))
    fake_key = embedder.embed(["fake key flagged"])[0]
    assert [h.path for h in index.query(fake_key, 5, {"onboarding/stale.md"})] == ["onboarding/stale.md"]
    assert index.query(fake_key, 5, {"governance/README.md", "index.md"}) == []


def test_build_index_starts_over_when_the_model_changes(kb_root: Path, kb_config):
    build_index(kb_root, kb_config, RecordingEmbedder(dim=16))
    other = RecordingEmbedder(dim=24)
    assert build_index(kb_root, kb_config, other).embedded == 4 and len(other.calls) == 1
    assert VectorIndex(index_path(kb_root)).stats().model_id == "hash-24"


def test_http_embedder_batches_authenticates_and_reports_errors():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = json.loads(request.content)
        if body["model"] == "boom":
            return httpx.Response(500, text="server error")
        if body["model"] == "junk":
            return httpx.Response(200, text="not json")
        if body["model"] == "short":
            return httpx.Response(200, json={"data": [{"embedding": [1.0, 0.0]}]})
        return httpx.Response(200, json={"data": [{"embedding": [1.0, 2.0, 3.0]} for _ in body["input"]]})

    transport = httpx.MockTransport(handler)
    embedder = HttpEmbedder(URL, "text-embed-1", "sk-very-secret", transport)
    vectors = embedder.embed([f"text {n}" for n in range(70)])
    assert len(vectors) == 70 and vectors[0] == [1.0, 2.0, 3.0] and embedder.dim == 3
    assert embedder.model_id.startswith("text-embed-1@") and "example" not in embedder.model_id
    assert HttpEmbedder("https://other.example.test/v1", "text-embed-1", None).model_id != embedder.model_id
    assert [len(json.loads(r.content)["input"]) for r in seen] == [64, 6]
    assert all(r.headers["authorization"] == "Bearer sk-very-secret" for r in seen)
    for model in ("boom", "junk", "short"):
        with pytest.raises(EmbedError) as info:
            HttpEmbedder(URL, model, "sk-very-secret", transport).embed(["a", "b"])
        assert "sk-very-secret" not in str(info.value) and info.value.__cause__ is None
    with pytest.raises(EmbedError, match="500"):
        HttpEmbedder(URL, "boom", None, transport).embed(["a"])


def test_embedder_from_settings_prefers_the_configured_endpoint():
    assert isinstance(embedder_from_settings(LibrarianSettings(embed_dim=16)), HashEmbedder)
    assert embedder_from_settings(LibrarianSettings(embed_dim=16)).dim == 16
    http = embedder_from_settings(LibrarianSettings(embed_url="https://e.example.test/v1", embed_model="m"))
    assert isinstance(http, HttpEmbedder) and http.model_id.startswith("m@")
    with pytest.raises(ValueError):
        LibrarianSettings(embed_url="http://e.example.test/v1", embed_model="m")  # https only, like the IdP URLs
    with pytest.raises(ValueError, match="KB_EMBED_MODEL is required"):
        LibrarianSettings(embed_url="https://e.example.test/v1")  # an endpoint without a model fails at the endpoint


def test_rrf_fuses_two_orders_and_the_retriever_searches_with_allowed_paths(tmp_path: Path):
    assert rrf(["a", "b", "c"], ["c", "d"]) == ["c", "a", "b", "d"]
    assert rrf([], ["x", "x", "y"]) == ["x", "y"] and rrf([], []) == []
    embedder = HashEmbedder(dim=32)
    index = VectorIndex(tmp_path / "e.sqlite")
    chunks = chunk_document(_doc("a.md", "# Keys\nobtaining credentials for the gateway"))
    index.upsert(chunks, embedder.embed([c.text for c in chunks]), embedder.model_id)
    retriever = Retriever(index, embedder)
    assert [h.path for h in retriever.search("gateway credentials", 8, {"a.md"})] == ["a.md"]
    assert retriever.search("gateway credentials", 8, set()) == [] and retriever.search("   ", 8, {"a.md"}) == []
