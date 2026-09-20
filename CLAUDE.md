# Collection

Reusable AI components (tools, integrations, skills, patterns) for the company's AI Champions programme. One
directory per component under `components/`, each with a `component.json` manifest, a README and tests.
`practices/` holds the short best-practice notes the components implement; `program/` holds the champions
programme itself (charter, meeting formats, templates).

## Working here

- Read `CONTRIBUTING.md` before adding or changing a component: it is the contract the catalog tool enforces.
- After any change under `components/`: `python3 tools/catalog.py --write && python3 tools/catalog.py --check`.
- Run a component's tests from its directory with the `test` command in its manifest, or all at once with
  `python3 tools/catalog.py --test` (`--only python` or `--only typescript` to narrow).
- Python components are standard library only unless `requires` says otherwise. Do not add a dependency to get
  around that; write the small thing.
- Never put a secret, a real tenant id, a real group id or a real URL in the repository. Placeholders must look like
  placeholders.
- A component imports nothing outside its own directory. Shared files are vendored and declared in `vendored`.
- Keep READMEs in the template's shape; the "five-minute start" must actually run.
- Commit messages: what changed and why, one component per commit where practical.
