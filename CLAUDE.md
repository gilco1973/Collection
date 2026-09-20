# Collection

Three parts in one repository: `hub/` (the employee AI hub front end), `knowledgebase/` (the knowledge base and its
librarian) and `components/` (reusable AI components with manifests, READMEs and tests). `tools/catalog.py`
publishes the components to the other two. `README.md` explains how they fit; `SOURCES.md` where they came from.

## Working here

- `hub/` and `knowledgebase/` each have their own `CLAUDE.md`, `README.md` and gates; follow them inside those
  directories. The knowledge base is organisation-neutral by its own check: no product names, no origin repository
  names, pages under 200 lines.
- Components: read `CONTRIBUTING.md` first; it is the contract `tools/catalog.py --check` enforces. Python components
  are standard library only unless `requires` says otherwise; a component imports nothing outside its directory;
  shared files are vendored and declared.
- After any change under `components/`: `python3 tools/catalog.py --write && python3 tools/catalog.py --check`, then
  `cd knowledgebase && poetry run kb-librarian index --write && poetry run kb-librarian check`. The generated files
  (`CATALOG.md`, `hub/src/api/mock/collection.ts`, `knowledgebase/docs/components/`, the collection rows in
  `knowledgebase/docs/skills/README.md`) are never edited by hand.
- Component tags must come from the knowledge base's taxonomy (`knowledgebase/kb.config.yaml`).
- Run tests with `python3 tools/catalog.py --test` (`--only python|typescript|skills`), `cd hub && pnpm verify`, and
  the knowledge base's four commands in its `CLAUDE.md`.
- Never put a secret, a real tenant id, a real group id or a real URL anywhere. Placeholders must look like
  placeholders. The knowledge base's sensitive-content check is the backstop, not the rule.
- Keep READMEs in the template's shape; the "five-minute start" must actually run.
- Commit messages: what changed and why; one part or one component per commit where practical.
