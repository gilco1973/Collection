# The walkthrough video

A step-by-step walkthrough of the Collection for the first AI champions meeting: the hub, the knowledge base and
the components, from real screenshots of the running products. Built with the `walkthrough-video` skill in
`components/skills/`; rebuilt from `slides.py` whenever the products change, never re-recorded.

| File | What it is |
| --- | --- |
| `slides.py` | The nineteen slides with their narration (the authoritative script) |
| `capture_shots.cjs` | Drives the hub (`pnpm preview`) and the knowledge-base console (the product's `deploy/serve.py`, run from its own checkout) with Playwright and screenshots each step; renders the terminal outputs |
| `build.sh` | The whole pipeline: terminal outputs, shots, deck, frames, narration, video |
| `out/collection-walkthrough.mp4` | The result (not committed): about eight minutes, captions burned in, plus `.en.vtt` and a no-captions copy |

## Rebuild

```
cd hub && pnpm install && pnpm build && pnpm preview &                       # :4173
python3 tools/publish_kb.py ../knowledge-base                                  # a checkout of the product, with the Collection's pages applied
cd ../knowledge-base && poetry install && (cd web && npm ci && npm run build) && \
  KB_API_KEY=<any-placeholder-key> KB_ROOT=$PWD poetry run python deploy/serve.py &   # :8765
python3 -m pip install --user imageio-ffmpeg                                   # an ffmpeg if none is installed
cd demo && CHROMIUM_PATH=/path/to/chromium NODE_PATH=../hub/node_modules ./build.sh
```

`NARRATION=elevenlabs ./build.sh` with `ELEVENLABS_API_KEY` set produces the voiced version; the default is silent
with captions timed at 2.6 words per second. Pass slide numbers to `build_narration.py` to regenerate only the
slides you changed.

## The steps the video walks through

1. The shape: four parts, one repository, drawn on the architecture diagram.
2. The shelf: six categories and who each is for; the shelf tool's listing.
3. The hub: Discover's Agents tab, the agent's listing with its template, tools and harness, and the sign-off card; the guide, open on that listing for a leader.
4. Under the hood: one call through the loop (the harness diagram), then the agent's first read in a terminal, and the same agent over MCP.
5. Governance: how a component earns its sign-offs, the queue and form, the onboarding tracker.
6. The assistant: how an answer is produced and where it stops.
7. The knowledge base: the components section and the onboarding pages.
8. Inside the bank: configuration that fails closed, one verify script for every runner, the offline bundle.
9. The programme and your first hour.

The diagrams are the same drawings the PDFs use (`docs/pdf/diagrams.py`), rendered to SVG and screenshotted, so a
change to a diagram reaches both.
