# Collection

The company's shared toolbox for building with AI: the **components** engineers copy, the **hub** that lists them,
and the pages the Collection publishes into the **knowledge base**, a standalone product in its own repository (as
is the first responder the components came from). Built for the AI champions programme: one engineer per team,
meeting every two weeks, each carrying one initiative built from what is here and bringing the result back.

| Part | What it is | Run it |
| --- | --- | --- |
| `hub/` | The employee AI hub: Discover (the catalog, including every component here), My workspace, Build (the intake brief), Learn. React, pixel-identical to its design artboards, runs against an in-browser API | `cd hub && pnpm install && pnpm dev` |
| `content/knowledgebase/` | The pages the Collection authors for the knowledge base: the practices behind the components, the first responder as use case 002, the AI champions programme and the initiative brief | `python3 tools/publish_kb.py <checkout>` |
| `components/` | 29 self-contained AI components in six categories: an agent (template, tools, harness), the harnesses (the action loop and an MCP server in front of it), tools (including a read-only MCP server over the shelf for coding assistants), integrations (Jira, Azure DevOps, Teams, Bedrock, AWS SigV4, OIDC, and the gateway for an external MCP server), patterns, and skills anyone can follow. Lifted from products in production: Python (standard library only), TypeScript, and markdown with templates and scripts. Each has a version, two sign-offs (owner and AI security engineer) bound to that version, a five-minute README, a step-by-step walkthrough, a live example, a manifest and tests | `python3 tools/shelf.py --test && python3 tools/shelf.py --examples` |
| `services/hub-api/` | The hub's API behind the bank's identity provider, on the standard library: every path of the contract plus sign-offs, the built hub served from the same process, a SQLite record | `cd services/hub-api && python3 -m unittest discover -s tests -t .` |
| `services/agent-runtime/` | One agent of the collection over MCP and a run API, wired to the bank's identity provider, KMS, Bedrock, Jira and Azure DevOps by configuration; fakes in the sandbox, refused in production | `cd services/agent-runtime && python3 -m unittest discover -s tests -t .` |
| `config/`, `CONFIGURATION.md` | Every system the collection touches, named once; settings that fail closed | `python3 -m hubapi check-config` |
| `scripts/` | `verify.sh` (every gate, any runner) and `bundle.sh` (an offline release with the hub prebuilt) | `scripts/verify.sh python` |
| `deploy/`, `services/*/deploy/` | Compose for the sandbox; Dockerfiles, fail-closed entrypoints, ECS task definitions and task roles with placeholders | `docker compose -f deploy/compose.yaml up` |
| `docs/pdf/` | The user manual (non-technical), the technical guide and the leadership brief as PDFs, built by `docs/pdf/build.py` | `python3 docs/pdf/build.py` |
| `tools/shelf.py` | Validates every manifest, checks vendored copies, runs the tests, and generates the hub's listings and the knowledge-base pages under `exports/` | `python3 tools/shelf.py --check` |
| `tools/publish_kb.py` | Applies `exports/knowledgebase/` and `content/knowledgebase/` to a checkout of the knowledge base, idempotently | `python3 tools/publish_kb.py <checkout>` |

`SHELF.md` is the generated index of the components. `CONTRIBUTING.md` is the component contract. `SOURCES.md`
names where each part came from and where the standalone products live.

## How the three fit

- A component lives in `components/<group>/<name>/` with `component.json`, `README.md` and tests.
- `python3 tools/shelf.py --write` turns every component into a listing on the hub's Discover page (under the
  Tools and Knowledge tabs and in search, with a listing page built from the README) and into a knowledge-base page
  under `exports/knowledgebase/` (`docs/components/<name>.md`, or `docs/skills/<name>/SKILL.md` for a skill).
- `python3 tools/publish_kb.py <checkout>` copies those pages and the authored ones in `content/knowledgebase/` into
  a checkout of the knowledge base, gives each section README the links it needs, and adds the `components` section
  to its contract. The product's librarian then audits them for freshness, links and sensitive content like any
  other page. Run it whenever the Collection changes; it changes nothing the second time.
- The first responder and the knowledge base stay standalone products. The Collection takes pieces out of them
  (see each component's "Where it came from") and puts pages into one of them; it never contains either.

## Start here

- **A champion's first hour:** read `content/knowledgebase/docs/onboarding/ai-champions.md` (or the same page in
  the knowledge base), then `cd components/python/governed-action-loop && python3 example.py`.
- **Presenting the programme:** the first-meeting outline is in that same page; open the hub (`pnpm dev`), sign in
  as a persona, and show Discover's Tools tab and the Learn page.
- **Adding a component:** `python3 tools/new_component.py python my-tool --category tool --summary "..."`, then
  `python3 tools/shelf.py --write`.

## Gates

CI runs the shelf check, every component's tests and live examples, and the hub's typecheck, lint, tests and build. The knowledge
base's own checks run in its repository after `publish_kb.py`. Locally:

```
python3 tools/shelf.py --check && python3 tools/shelf.py --test
cd hub && pnpm verify
python3 tools/publish_kb.py ../knowledge-base && (cd ../knowledge-base && poetry run kb-librarian index --write && poetry run kb-librarian check)
```
