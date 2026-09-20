from pathlib import Path

from kb_librarian.catalog.catalog import load_catalog, render_index


def test_catalog_loads_every_markdown_file(catalog):
    paths = sorted(d.rel_path for d in catalog.documents)
    assert paths == [
        "governance/README.md",
        "index.md",
        "onboarding/README.md",
        "onboarding/stale.md",
    ]


def test_document_section_resolution(catalog):
    by_path = {d.rel_path: d for d in catalog.documents}
    assert by_path["onboarding/stale.md"].section_id == "onboarding"
    assert by_path["index.md"].section_id is None


def test_document_links_are_extracted(catalog):
    doc = catalog.get("onboarding/stale.md")
    assert doc is not None
    assert [link.target for link in doc.links] == ["does-not-exist.md"]


def test_search_is_case_insensitive(catalog):
    hits = catalog.search("FAKE KEY")
    assert [d.rel_path for d in hits] == ["onboarding/stale.md"]


def test_render_index_lists_sections_and_docs(catalog, kb_config):
    text = render_index(catalog, kb_config)
    assert "## Onboarding" in text
    assert "[Stale page](onboarding/stale.md)" in text
    assert "## Governance" in text
    assert text.startswith("---\ntitle: Knowledge base index\nowner: enablement\n")


def test_load_catalog_ignores_non_markdown(kb_root: Path, kb_config):
    (kb_root / "docs" / "onboarding" / "notes.txt").write_text("ignored")
    catalog = load_catalog(kb_root, kb_config)
    assert catalog.get("onboarding/notes.txt") is None
