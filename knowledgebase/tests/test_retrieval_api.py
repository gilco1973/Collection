"""``GET /api/search?mode=`` over the embedding index (a synonym-aware test double, no network, no LLM)."""

import os
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kb_librarian.api import service
from kb_librarian.api.app import create_app
from kb_librarian.api.deps import build_state
from kb_librarian.config import LibrarianSettings
from kb_librarian.models import AuditReport, Finding
from kb_librarian.reports import ReportStore
from kb_librarian.retrieval import state as retrieval_state
from kb_librarian.retrieval.build import build_index, index_path
from kb_librarian.retrieval.embedder import HashEmbedder
from kb_librarian.retrieval.index import Hit
from kb_librarian.retrieval.retriever import Retriever
from kb_librarian.retrieval.state import SEMANTIC_PER_WINDOW, SemanticThrottle

SYNONYMS = {"key": "credential", "credentials": "credential", "login": "signin", "sign-in": "signin"}
QUESTION = "how do I get an api key"
GATEWAY = (
    "---\ntitle: Gateway access\nowner: enablement\nstatus: active\nreviewed: 2026-09-01\n"
    "tags: [onboarding]\naudience: [engineer]\n---\n# Gateway access\n\n## Obtaining credentials\n"
    "Ask the platform team; they are issued per project and rotated yearly.\n"
)


class SynonymEmbedder(HashEmbedder):
    """The hash embedder behind a small synonym table: the one thing token overlap cannot do, so a test
    can show what a real embedder adds without any provider."""

    def __init__(self, dim: int = 1024):  # wide enough that the fixture's tokens share no bucket
        super().__init__(dim)
        self.model_id = f"synonym-{dim}"

    def _vector(self, text: str) -> list[float]:
        words = [SYNONYMS.get(word, word) for word in re.findall(r"[\w-]+", text.lower())]
        return super()._vector(" ".join(words))


@pytest.fixture
def client(kb_root: Path, monkeypatch):
    monkeypatch.setattr(retrieval_state, "embedder_from_settings", lambda settings: SynonymEmbedder())
    monkeypatch.setattr(retrieval_state, "_throttle", SemanticThrottle())  # the ceiling is per process
    (kb_root / "docs/onboarding/gateway.md").write_text(GATEWAY, encoding="utf-8")
    return TestClient(create_app(kb_root, LibrarianSettings(), cors_origins=[]))


def _paths(result: dict) -> list[str]:
    return [item["path"] for item in result["items"]]


def test_without_an_index_every_mode_is_keyword_and_says_so(client):
    for params in ({}, {"mode": "keyword"}, {"mode": "semantic"}, {"mode": "hybrid"}):
        result = client.get("/api/search", params={"q": "Healthy page", **params}).json()
        assert result["mode"] == "keyword" and _paths(result) == ["onboarding/README.md"]
        assert result["items"][0]["excerpt"] is None
    assert client.get("/api/search", params={"q": QUESTION}).json()["total"] == 0
    assert client.get("/api/search", params={"q": "x", "mode": "fuzzy"}).status_code == 422


def test_hybrid_search_finds_a_page_by_meaning_and_echoes_the_effective_mode(client, kb_root: Path, kb_config):
    build_index(kb_root, kb_config, SynonymEmbedder())
    found = client.get("/api/search", params={"q": QUESTION}).json()  # hybrid by default
    assert found["mode"] == "hybrid" and _paths(found)[0] == "onboarding/gateway.md"
    gateway = found["items"][0]
    assert gateway["excerpt"].startswith("## Obtaining credentials Ask the platform team")
    assert gateway["title"] == "Gateway access" and "snippet" in gateway and found["facets"]["section"]
    keyword = client.get("/api/search", params={"q": QUESTION, "mode": "keyword"}).json()
    assert keyword["mode"] == "keyword" and keyword["total"] == 0  # no page contains those words
    semantic = client.get("/api/search", params={"q": QUESTION, "mode": "semantic"}).json()
    assert semantic["mode"] == "semantic" and _paths(semantic)[0] == "onboarding/gateway.md"
    exact = client.get("/api/search", params={"q": "althy pa"}).json()  # a substring: keyword only
    assert exact["mode"] == "hybrid" and _paths(exact) == ["onboarding/README.md"]
    assert exact["items"][0]["excerpt"] is None
    assert client.get("/api/search", params={"q": "althy pa", "mode": "semantic"}).json()["total"] == 0
    both = client.get("/api/search", params={"q": "Healthy page"}).json()  # in both orders: fused, excerpt kept
    assert _paths(both)[0] == "onboarding/README.md" and both["items"][0]["excerpt"].startswith("# Onboarding")
    listing = client.get("/api/search", params={"q": ""}).json()  # a blank query is a listing: keyword
    assert listing["mode"] == "keyword" and listing["total"] >= 4
    filtered = client.get("/api/search", params={"q": QUESTION, "audience": "new-hire"}).json()
    assert "onboarding/gateway.md" not in _paths(filtered)  # filters still narrow the fused list


def test_a_withheld_page_is_absent_in_every_mode(client, kb_root: Path, kb_config):
    build_index(kb_root, kb_config, SynonymEmbedder())
    for mode in ("keyword", "semantic", "hybrid"):  # stale.md says "fake key" but carries a credential
        result = client.get("/api/search", params={"q": "fake key", "mode": mode}).json()
        assert result["mode"] == mode and "onboarding/stale.md" not in _paths(result), mode
        assert "AKIA" not in str(result)
    store = ReportStore(kb_root / ".librarian/reports")  # withheld by the latest audit's finding, not by its text
    report = AuditReport(audit_type="offline")
    report.findings.append(Finding(check="sensitive", severity="critical", path="onboarding/gateway.md", message="x"))
    report.finish("completed")
    store.save(report)
    for mode in ("semantic", "hybrid"):
        result = client.get("/api/search", params={"q": QUESTION, "mode": mode}).json()
        assert result["mode"] == mode and "onboarding/gateway.md" not in _paths(result)


def test_service_search_drops_a_withheld_or_unknown_semantic_hit_and_fuses_the_orders(catalog, kb_config):
    hits = [
        Hit("onboarding/stale.md#stale-page", "onboarding/stale.md", "Stale page", "fake key", 0.9),
        Hit("gone.md#x", "gone.md", "Gone", "no longer in the catalog", 0.8),
        Hit("governance/README.md#governance", "governance/README.md", "Governance", "No frontmatter", 0.5),
    ]
    fused = service.search(catalog, kb_config, "zzz", {}, {"onboarding/stale.md"}, semantic=hits, mode="hybrid")
    assert _paths(fused) == ["governance/README.md"] and fused["items"][0]["excerpt"] == "No frontmatter"
    assert fused["mode"] == "hybrid" and fused["total"] == 1
    hit = Hit("onboarding/README.md#onboarding", "onboarding/README.md", "Onboarding", "Healthy", 0.7)
    hybrid = service.search(catalog, kb_config, "e", {}, set(), semantic=[hit], mode="hybrid")  # "e": every page
    assert _paths(hybrid)[:2] == ["onboarding/README.md", "governance/README.md"]  # both orders beat catalog order
    assert [item["excerpt"] for item in hybrid["items"]][:2] == ["Healthy", None]
    assert service.search(catalog, kb_config, "page", {}, set(), semantic=None, mode="hybrid")["mode"] == "keyword"


def test_app_state_builds_the_retriever_lazily_and_follows_the_index_file(kb_root: Path, kb_config):
    state = build_state(kb_root, LibrarianSettings())
    assert state.retriever() is None
    build_index(kb_root, kb_config, HashEmbedder())
    first = state.retriever()
    assert isinstance(first, Retriever) and state.retriever() is first
    stamp = index_path(kb_root).stat().st_mtime_ns + 5_000_000_000
    os.utime(index_path(kb_root), ns=(stamp, stamp))
    second = state.retriever()
    assert second is not first and isinstance(second, Retriever)
    index_path(kb_root).unlink()
    assert state.retriever() is None


def test_semantic_search_is_throttled_per_client_and_degrades_to_keyword(client, kb_root: Path, kb_config):
    build_index(kb_root, kb_config, SynonymEmbedder())
    modes = [client.get("/api/search", params={"q": QUESTION}).json()["mode"] for _ in range(SEMANTIC_PER_WINDOW + 1)]
    assert modes[:SEMANTIC_PER_WINDOW] == ["hybrid"] * SEMANTIC_PER_WINDOW and modes[-1] == "keyword"
    assert client.get("/api/search", params={"q": "Healthy page", "mode": "keyword"}).json()["total"] == 1


def test_a_damaged_index_degrades_search_to_keyword(client, kb_root: Path, kb_config):
    build_index(kb_root, kb_config, SynonymEmbedder())
    assert client.get("/api/search", params={"q": QUESTION}).json()["mode"] == "hybrid"
    index_path(kb_root).write_bytes(b"not a database at all")
    degraded = client.get("/api/search", params={"q": "Healthy page"}).json()
    assert degraded["mode"] == "keyword" and _paths(degraded) == ["onboarding/README.md"]
