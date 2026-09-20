# Security review sheet: Catalog

| | |
| --- | --- |
| Module id | `catalog` |
| Kind | backend |
| Code | `kb_librarian/catalog/` (`catalog.py`, `frontmatter.py`, `links.py`) |
| Tests | `tests/test_catalog.py`, `tests/test_frontmatter.py` |
| Depends on | PyYAML |

## Purpose

Loads every Markdown page under `docs/` into `Document` objects (frontmatter, body, title,
section, raw text), resolves internal links, renders `docs/index.md`, and provides the
search used by the API and the agent's read tools. Translation copies under `docs/i18n/`
are excluded from the English catalog (`_is_translation`).

## Entry points

`load_catalog(root, config)`, `Catalog.get/in_section/search`, `render_index`,
`parse_frontmatter`, `render_frontmatter`, link extraction helpers.

## Trust boundaries

Page content is **untrusted data**: pages are written by many authors and are the main
channel through which prompt injection could reach the agent. This module only parses;
the labelled data envelope is applied where content reaches the model (`tools/context.py`).

## Data handled

Internal-tier documentation. Frontmatter is parsed with `yaml.safe_load`. Symlinks are
skipped; only files under `docs_root` are read.

## Secrets

None.

## External calls

None (filesystem read under the docs root only).

## Mutations

`render_index` returns text; writing is done by the `index --write` command or the
`regenerate_index` tool through the action log — this module never writes.

## Controls in place

- `yaml.safe_load`; a frontmatter parse error is recorded on the document
  (`frontmatter_error`), never raised into a request.
- Paths are docs-relative and normalised; `Catalog.get` is a dictionary lookup, not a path join.
- Symlinked pages are ignored so a link out of the tree cannot be catalogued.
- Search is case-insensitive substring matching over titles and bodies — no regex from input.

## Residual risks and reviewer attention points

- A very large docs tree is loaded fully into memory on each reload (API caches by mtime/size
  stamp; tools reload after every write). Acceptable for documentation-scale trees.
- Search is linear; query length is capped by the API (200 chars).
- The catalog holds withheld pages too; withholding is decided at the API layer from the
  latest completed report, not here.

## Reviewer checklist

- [ ] No file read outside `docs_root`; symlink skip still present.
- [ ] `yaml.safe_load` is the only YAML loader used.
- [ ] Translation exclusion keeps `docs/i18n/**` out of the English catalog.

## Sign-off

Submit with `kb-librarian security submit catalog`; the reviewer records the decision with
`kb-librarian security sign catalog …`, which appends a row here and to `security/signoffs/catalog.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
