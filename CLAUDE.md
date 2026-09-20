# Collection

`components/` (reusable AI components with manifests, READMEs and tests), `hub/` (the employee AI hub front end
that lists them) and `content/knowledgebase/` (pages the Collection authors for the knowledge base). The knowledge
base and the first responder are standalone products in their own repositories: the Collection lifts pieces out of
them and publishes pages into the knowledge base; it never contains either. `README.md` explains how the parts fit;
`SOURCES.md` where they came from.

## Working here

- `hub/` has its own `CLAUDE.md`, `README.md` and gates; follow them inside it.
- Pages under `content/knowledgebase/` and everything exported to the knowledge base obey the product's checks:
  frontmatter (owner, status, reviewed, tags from `tools/kb-taxonomy.json`, audience), under 200 lines,
  organisation-neutral (no product or repository names), links only inside `docs/`, list items on one line.
- Components: read `CONTRIBUTING.md` first; it is the contract `tools/catalog.py --check` enforces. Python components
  are standard library only unless `requires` says otherwise; a component imports nothing outside its directory;
  shared files are vendored and declared.
- After any change under `components/`: `python3 tools/catalog.py --write && python3 tools/catalog.py --check`. The
  generated files (`CATALOG.md`, `hub/src/api/mock/collection.ts`, `exports/knowledgebase/`) are never edited by hand.
- To deliver pages to the knowledge base: `python3 tools/publish_kb.py <checkout>`, then run that product's
  `kb-librarian index --write` and `kb-librarian check` in the checkout. The publisher is idempotent.
- Component tags must come from the knowledge base's taxonomy, mirrored in `tools/kb-taxonomy.json`; refresh the
  mirror when the product changes its contract.
- Run tests with `python3 tools/catalog.py --test` (`--only python|typescript|skills`) and `cd hub && pnpm verify`.
- Never put a secret, a real tenant id, a real group id or a real URL anywhere. Placeholders must look like
  placeholders.
- Keep READMEs in the template's shape; the "five-minute start" must actually run.
- Commit messages: what changed and why; one part or one component per commit where practical.
