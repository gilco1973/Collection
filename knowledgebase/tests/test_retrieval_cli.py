"""``kb-librarian index --embeddings`` and the doctor's ``embeddings`` check (hash embedder only, no network)."""

import io
from pathlib import Path

import pytest

from kb_librarian import cli
from kb_librarian.cli_doctor_probes import embeddings_check
from kb_librarian.config import LibrarianSettings
from kb_librarian.kbconfig import load_kb_config
from kb_librarian.retrieval.build import build_index, index_path
from kb_librarian.retrieval.embedder import HashEmbedder
from tests.doctor_helpers import ENV_KEYS, FAKE_CREDENTIAL, WithRetention, run_doctor

NO_INDEX = "WARN embeddings — no embedding index: run kb-librarian index --embeddings"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_CREDENTIAL)


def _run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    code = cli.main(list(argv), out=out)
    return code, out.getvalue()


def test_index_embeddings_builds_the_vector_index_and_prints_the_counts(kb_root: Path):
    assert not index_path(kb_root).exists()
    code, out = _run("--root", str(kb_root), "index", "--embeddings")
    assert code == 0 and out.strip() == "embeddings: 4 embedded, 0 unchanged, 0 removed, 4 pages"
    assert index_path(kb_root).is_file() and "## Onboarding" not in out  # the vector index, not docs/index.md
    code, out = _run("--root", str(kb_root), "index", "--embeddings")
    assert code == 0 and out.strip() == "embeddings: 0 embedded, 4 unchanged, 0 removed, 4 pages"
    code, out = _run("--root", str(kb_root), "index")  # without the flag: unchanged behaviour
    assert code == 0 and "## Onboarding" in out and "embeddings:" not in out
    assert cli.build_parser().parse_args(["index"]).embeddings is False


def test_doctor_reports_the_embedding_index_states(kb_root: Path):
    code, lines = run_doctor(WithRetention(), kb_root, index=False)
    assert code == 1 and NO_INDEX in lines
    build_index(kb_root, load_kb_config(kb_root / "kb.config.yaml"), HashEmbedder(256))
    code, lines = run_doctor(WithRetention(), kb_root)
    assert code == 0 and "OK embeddings — 4 chunks over 4 pages (model hash-256)" in lines
    code, lines = run_doctor(WithRetention(embed_dim=64), kb_root)
    assert code == 1 and any(
        line.startswith("WARN embeddings — index built with model 'hash-256' but the configured embedder is 'hash-64'")
        for line in lines
    )
    remote = LibrarianSettings(embed_url="https://embed.example.test/v1", embed_model="m1", embed_api_key="k-secret")
    check = embeddings_check(remote, kb_root)
    assert check.status == "WARN" and "'m1@" in check.detail and "k-secret" not in check.detail
    assert "example" not in check.detail  # the endpoint is a tag, never a host name
    index_path(kb_root).write_bytes(b"not a database at all")
    check = embeddings_check(WithRetention(), kb_root)
    assert check.status == "FAIL" and check.detail.startswith("index unreadable (DatabaseError)")
