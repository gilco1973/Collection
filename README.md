# Collection

The company's AI enablement in one repository: the **hub** people open, the **knowledge base** that holds what they
read, and the **components** engineers copy. Built for the AI champions programme: one engineer per team, meeting
every two weeks, each carrying one initiative built from what is here and bringing the result back.

| Part | What it is | Run it |
| --- | --- | --- |
| `hub/` | The employee AI hub: Discover (the catalog, including every component here), My workspace, Build (the intake brief), Learn. React, pixel-identical to its design artboards, runs against an in-browser API | `cd hub && pnpm install && pnpm dev` |
| `knowledgebase/` | The knowledge base (onboarding, paved roads, best practices, skills, tutorials, governance, components) and the librarian agent that keeps it healthy, with its API and console | `cd knowledgebase && poetry install && poetry run kb-librarian check` |
| `components/` | 23 self-contained components lifted from products in production: Python tools and integrations (standard library only), TypeScript pieces, and skills with templates and scripts. Each has a five-minute README, a manifest and tests | `python3 tools/catalog.py --test` |
| `tools/catalog.py` | Validates every manifest, checks vendored copies, runs the tests, and publishes the components to the hub's Discover page and to the knowledge base | `python3 tools/catalog.py --check` |

`CATALOG.md` is the generated index of the components. `CONTRIBUTING.md` is the component contract. `SOURCES.md`
names where each part came from.

## How the three fit

- A component lives in `components/<group>/<name>/` with `component.json`, `README.md` and tests.
- `python3 tools/catalog.py --write` turns every component into a listing on the hub's Discover page (under the
  Tools and Knowledge tabs and in search, with a listing page built from the README) and into a knowledge-base page
  (`docs/components/<name>.md`, or `docs/skills/<name>/SKILL.md` for a skill) that the librarian audits for
  freshness, links and sensitive content.
- The practices the components implement are knowledge-base pages under `best-practices/`; the programme itself is
  under `onboarding/`; the two products the components came from are paved-road use cases 001 and 002.

## Start here

- **A champion's first hour:** read `knowledgebase/docs/onboarding/ai-champions.md`, then
  `cd components/python/governed-action-loop && python3 example.py`.
- **Presenting the programme:** the first-meeting outline is in that same page; open the hub (`pnpm dev`), sign in
  as a persona, and show Discover's Tools tab and the Learn page.
- **Adding a component:** `python3 tools/new_component.py python my-tool --kind tool --summary "..."`, then
  `python3 tools/catalog.py --write`.

## Gates

CI runs the catalog check, every component's tests, the hub's typecheck, lint, tests and build, and the knowledge
base's lint, tests, layout and content checks. Locally:

```
python3 tools/catalog.py --check && python3 tools/catalog.py --test
cd hub && pnpm verify
cd knowledgebase && poetry run ruff check . && poetry run pytest && scripts/verify-layout.sh && poetry run kb-librarian check
```
