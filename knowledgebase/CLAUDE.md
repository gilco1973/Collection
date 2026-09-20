# CLAUDE.md — KnowledgeBase

Rules for anyone (person or agent) changing this project. It is self-contained and
organisation-neutral: do not introduce references to other products, internal
platforms, or proprietary packages.

## Content

- Every page under `docs/` has frontmatter: `title`, `owner`, `status`
  (`draft|active|deprecated`), `reviewed` (ISO date), `tags` (from `taxonomy.tags` in
  `kb.config.yaml`), `audience` (from `frontmatter.audience_values`).
- Pages are Internal tier: no credentials, personal data, customer data, hostnames of
  real systems. `kb-librarian check` fails on sensitive content.
- Every page is linked from its section `README.md`; regenerate `docs/index.md` with
  `kb-librarian index --write` after adding pages.
- Keep pages under 200 lines. Deprecate rather than delete.
- Only a page owner bumps `reviewed`. The librarian never does.

## Code (`kb_librarian/`)

- Python 3.11, Poetry only. No `pip install`, no `requirements.txt`.
- Files stay under 200 lines. Split by concern.
- Coverage gate 87% (`pytest` enforces it). New behaviour ships with a test seen failing first.
- The permission gate (`agent/gate.py`) is the only place tool execution is decided.
  Mutating tools are listed in `tools/server.py::MUTATING_TOOLS`; add a tool that
  changes anything to that set in the same commit.
- Every mutating tool takes a `reason`, records a `LibrarianAction` with before/after
  state, and does nothing to disk in dry-run.
- `KB_ALLOW_LIVE` and `KB_ATLASSIAN_ALLOW_WRITE` are server-side gates. Never add a
  code path that lets a caller bypass them.
- Built-in Claude Code tools stay in `DISALLOWED_BUILTINS`. The knowledge base is edited
  only through the audited kb tools.
- Findings and reports never echo a sensitive value.
- Secrets come from the environment (secret manager). Never read a `.env` you did not
  generate; never commit one.
- Every source file belongs to a module in `security/registry.yaml` with a review sheet under
  `security/modules/` (a test enforces this). New code goes into an existing module's globs or
  gets a new entry and sheet in the same commit; never edit a sign-off row by hand.

## Handover packages

A handover zip is always **versioned** and always ships with the **handover document**:
`HANDOVER.md` (kept under 200 lines, updated for the state being handed over, with a row for
the new version in its history table), then `scripts/handover.sh <version> [out-dir]` builds
`KnowledgeBase-handover-v<version>.zip` from the tracked files at HEAD plus the document and a
manifest (commit, build time, file count). Never hand over an unversioned zip or a zip without
the document; the script refuses a dirty tree or a version the document does not list.

## Before you say "done"

```bash
poetry run ruff check . && poetry run ruff format --check .
poetry run pytest
scripts/verify-layout.sh
poetry run kb-librarian check
```
