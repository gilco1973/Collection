"""Mirror configured sections of the knowledge base into a Confluence space."""

from dataclasses import dataclass

from kb_librarian.atlassian.confluence import ConfluenceClient
from kb_librarian.atlassian.markdown import markdown_to_storage
from kb_librarian.catalog.catalog import Catalog, Document
from kb_librarian.kbconfig import KbConfig


@dataclass(frozen=True)
class SyncResult:
    path: str
    title: str
    action: str  # created | updated | would-publish | skipped
    detail: str = ""


def page_title(doc: Document, config: KbConfig) -> str:
    section = config.section_by_id(doc.section_id) if doc.section_id else None
    prefix = f"[{section.title}] " if section else ""
    return f"{prefix}{doc.title}"


def _footer(doc: Document) -> str:
    return (
        "\n\n---\n"
        f"Mirrored from the AI knowledge base page `{doc.rel_path}` by kb-librarian. "
        "Edit the source page, not this copy."
    )


def sync_sections(
    catalog: Catalog,
    config: KbConfig,
    confluence: ConfluenceClient,
    sections: list[str] | None = None,
) -> list[SyncResult]:
    wanted = sections or config.atlassian.mirror_sections
    results: list[SyncResult] = []
    for section_id in wanted:
        for doc in catalog.in_section(section_id):
            if doc.meta.get("status") != "active":
                results.append(SyncResult(doc.rel_path, doc.title, "skipped", "status is not active"))
                continue
            title = page_title(doc, config)
            body = markdown_to_storage(doc.body + _footer(doc))
            if not confluence.writes_enabled:
                results.append(SyncResult(doc.rel_path, title, "would-publish", "writes gated"))
                continue
            outcome = confluence.publish(config.atlassian.confluence_space_key, title, body)
            results.append(SyncResult(doc.rel_path, title, outcome["action"], str(outcome.get("id", ""))))
    return results
