"""A translated view of the catalog: how every read endpoint serves a `?lang=` request."""

from pathlib import Path

from kb_librarian.catalog.catalog import Catalog, Document
from kb_librarian.catalog.frontmatter import split_frontmatter
from kb_librarian.catalog.links import extract_links


def _translated_document(doc: Document, translation_path: Path) -> Document | None:
    """``doc`` with its title/body swapped for ``translation_path``'s, or ``None`` where that file
    doesn't exist or has no usable title. Section, path identity and the English ``raw`` (which
    governs the sensitive-content check) are all kept, so withhold status never depends on language."""
    if not translation_path.is_file() or translation_path.is_symlink():
        return None
    meta, body, offset = split_frontmatter(translation_path.read_text(encoding="utf-8"))
    title = meta.get("title")
    if not (isinstance(title, str) and title.strip()):
        return None
    return Document(
        rel_path=doc.rel_path,
        path=doc.path,
        meta={**doc.meta, "title": title},
        body=body,
        section_id=doc.section_id,
        body_offset=offset,
        raw=doc.raw,
        links=extract_links(body, offset),
    )


def localize(catalog: Catalog, docs_root: Path, lang: str) -> tuple[Catalog, set[str]]:
    """A view of ``catalog`` with every page's title/body swapped for its ``docs/i18n/<lang>/...``
    translation, where one exists; a page with no translation yet keeps its English text unchanged.

    Every read endpoint (sections, listings, search, single page) can run against this the same way
    it runs against the English catalog, so translated search, listings and titles all fall out of
    this one function. Returns the swapped ``rel_path``s too, so a caller can tell what changed.
    """
    documents: list[Document] = []
    translated: set[str] = set()
    for doc in catalog.documents:
        replacement = _translated_document(doc, docs_root / "i18n" / lang / doc.rel_path)
        if replacement is not None:
            documents.append(replacement)
            translated.add(doc.rel_path)
        else:
            documents.append(doc)
    return Catalog(root=catalog.root, docs_root=catalog.docs_root, documents=documents), translated
