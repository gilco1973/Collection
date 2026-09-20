"""Structure: sections have landing pages, the index is current, every page is reachable."""

from kb_librarian.catalog.catalog import Catalog, render_index_body
from kb_librarian.checks.base import Finding
from kb_librarian.kbconfig import KbConfig

CHECK = "structure"


def _inbound(catalog: Catalog) -> dict[str, set[str]]:
    """target rel_path -> set of source rel_paths (internal links only, directories → README)."""
    inbound: dict[str, set[str]] = {}
    docs_root = catalog.docs_root.resolve()
    for doc in catalog.documents:
        for link in doc.links:
            if link.is_external:
                continue
            resolved = (doc.path.parent / link.target.split("#", 1)[0]).resolve()
            if resolved.is_dir():
                resolved = resolved / "README.md"
            try:
                inbound.setdefault(resolved.relative_to(docs_root).as_posix(), set()).add(doc.rel_path)
            except ValueError:
                continue
    return inbound


def _section_readme_links(doc, sources: set[str], config: KbConfig) -> bool:
    section = config.section_by_id(doc.section_id) if doc.section_id else None
    if section is None:
        return bool(sources)
    prefix = section.path + "/"
    return any(src.startswith(prefix) and src.endswith("README.md") for src in sources)


def check_structure(catalog: Catalog, config: KbConfig) -> list[Finding]:
    findings: list[Finding] = []
    for section in config.sections:
        readme = f"{section.path}/README.md"
        if catalog.get(readme) is None:
            findings.append(
                Finding(
                    check=CHECK,
                    severity="error",
                    path=readme,
                    message=f"section '{section.id}' has no README.md at {readme}",
                    fix_hint="create the section landing page",
                )
            )
    index = catalog.get("index.md")
    if index is None:
        findings.append(
            Finding(
                check=CHECK,
                severity="error",
                path="index.md",
                message="docs/index.md is missing",
                fix_hint="run `kb-librarian index --write`",
                auto_fixable=True,
            )
        )
    elif index.body != render_index_body(catalog, config):
        findings.append(
            Finding(
                check=CHECK,
                severity="error",
                path="index.md",
                message="docs/index.md is out of date with the catalog",
                fix_hint="run `kb-librarian index --write`",
                auto_fixable=True,
            )
        )
    inbound = _inbound(catalog)
    for doc in catalog.documents:
        if doc.rel_path == "index.md":
            continue
        sources = inbound.get(doc.rel_path, set())
        if not sources:
            findings.append(
                Finding(
                    check=CHECK,
                    severity="warning",
                    path=doc.rel_path,
                    message="orphan page: nothing links to it",
                    fix_hint="link it from its section README.md",
                )
            )
        elif (
            config.structure.require_section_readme_link
            and not doc.is_readme
            and not _section_readme_links(doc, sources, config)
        ):
            findings.append(
                Finding(
                    check=CHECK,
                    severity="warning",
                    path=doc.rel_path,
                    message="not linked from any README.md in its section",
                    fix_hint="add it to the section landing page so readers can find it",
                )
            )
    return findings
