# Sources

Where each part of this repository came from, and where the standalone products live. The first responder and the
knowledge base are products in their own repositories: the Collection lifts pieces out of them and publishes pages
into the knowledge base; it contains neither. Knowledge-base pages are organisation-neutral by the product's own
gate, so origin repositories are named here only.

| Part | Origin | Branch / package | Brought in | Notes |
| --- | --- | --- | --- | --- |
| `hub/` | `Olorin-ai-git/olorin`, folder `crossriver-ai-hub` | handover zip of 2026-09-19 | 2026-09-20 | As is, plus the generated `src/api/mock/collection.ts`, the first-responder listing, the Learn section, `VITE_KB_URL` |
| the knowledge base (not in this repository) | `Olorin-ai-git/olorin`, folder `KnowledgeBase` | `claude/vibrant-tesla-u7ccr3`, handover v5 (2026-09-19) | receives pages | `python3 tools/publish_kb.py <checkout>` delivers `exports/knowledgebase/` and `content/knowledgebase/`; the product's librarian then checks them. The taxonomy its contract allows is mirrored in `tools/kb-taxonomy.json` |
| `components/python/*`, `components/skills/*` | `Olorin-ai-git/First-responder` (Meg, the first responder, not in this repository), folder `meg/` | `claude/meg-first-responder`, tip snapshot of 2026-09-19 and the handover of 2026-09-19 | 2026-09-20 | Each component's README names its source file and what changed during extraction |
| `components/typescript/*`, `components/skills/pixel-parity-screenshots` | the hub above | | 2026-09-20 | |

The three origin repositories could not be attached to the session that built this repository (a different GitHub
owner), so the handover packages were the source. When the origins move, refresh a component from its named path,
re-run its tests, and update `source.snapshot` in its manifest.
