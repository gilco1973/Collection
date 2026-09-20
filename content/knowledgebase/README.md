# Content the Collection publishes into the knowledge base

The knowledge base is a standalone product in its own repository. The Collection does not contain it; it publishes
pages into a checkout of it with `python3 tools/publish_kb.py <path-to-knowledge-base>`.

| Here | What it is |
| --- | --- |
| `docs/best-practices/*.md` | The practices behind the components, authored here |
| `docs/paved-roads/use-case-002-first-responder.md` | The first responder as a paved-road use case |
| `docs/onboarding/ai-champions*.md` | The AI champions programme and the initiative brief |
| `sections/<section>.md` | The block each section's README gains (table rows or a paragraph) so every page is linked from its section, as the librarian requires; placed between `<!-- collection:start -->` and `<!-- collection:end -->` markers |
| `kb.config.section.yaml` | The `components` section the knowledge base's contract gains |

Generated pages (one per component, one SKILL.md per skill, the components index, the skills rows) are written by
`python3 tools/catalog.py --write` into `exports/knowledgebase/` and published by the same script.

Rules these pages follow, because the product's own checks enforce them: frontmatter with owner, status, reviewed,
tags from the taxonomy (`tools/kb-taxonomy.json`) and audience; under 200 lines; organisation-neutral, so no
product or repository names; internal links only inside `docs/`; list items on one line.
