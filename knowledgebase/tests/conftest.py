"""Shared fixtures: a copy of the small fixture knowledge base per test."""

import shutil
from datetime import date
from pathlib import Path

import pytest

from kb_librarian.catalog.catalog import load_catalog
from kb_librarian.kbconfig import load_kb_config

FIXTURE_KB = Path(__file__).parent / "fixtures" / "kb"
TODAY = date(2026, 9, 15)


@pytest.fixture
def kb_root(tmp_path: Path) -> Path:
    """A writable copy of the fixture knowledge base."""
    dest = tmp_path / "kb"
    shutil.copytree(FIXTURE_KB, dest)
    return dest


@pytest.fixture
def kb_config(kb_root: Path):
    return load_kb_config(kb_root / "kb.config.yaml")


@pytest.fixture
def catalog(kb_root: Path, kb_config):
    return load_catalog(kb_root, kb_config)
