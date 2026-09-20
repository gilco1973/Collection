# Sources

Where each part of this repository came from, so a change at the origin can be brought in deliberately. The
knowledge base's pages are organisation-neutral by its own gate, so the origin repositories are named here and not
inside `knowledgebase/`.

| Part | Origin | Branch / package | Brought in | Notes |
| --- | --- | --- | --- | --- |
| `hub/` | `Olorin-ai-git/olorin`, folder `crossriver-ai-hub` | handover zip of 2026-09-19 | 2026-09-20 | As is, plus the generated `src/api/mock/collection.ts`, the first-responder listing, the Learn section, `VITE_KB_URL` |
| `knowledgebase/` | `Olorin-ai-git/olorin`, folder `KnowledgeBase` | `claude/vibrant-tesla-u7ccr3`, handover v5 (`KnowledgeBase-handover-v5.zip`, 2026-09-19) | 2026-09-20 | As is, plus the `components` section, the generated pages, and the practice, use-case and programme pages listed in `git log` |
| `components/python/*`, `components/skills/*` | `Olorin-ai-git/First-responder` (Meg, the first responder), folder `meg/` | `claude/meg-first-responder`, tip snapshot of 2026-09-19 and the handover of 2026-09-19 | 2026-09-20 | Each component's README names its source file and what changed during extraction |
| `components/typescript/*`, `components/skills/pixel-parity-screenshots` | the hub above | | 2026-09-20 | |

The three origin repositories could not be attached to the session that built this repository (a different GitHub
owner), so the handover packages were the source. When the origins move, refresh a component from its named path,
re-run its tests, and update `source.snapshot` in its manifest.
