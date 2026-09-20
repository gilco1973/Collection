# The walkthrough video

A step-by-step walkthrough of the Collection for the first AI champions meeting: the hub, the knowledge base and
the components, from real screenshots of the running products. Built with the `walkthrough-video` skill in
`components/skills/`; rebuilt from `slides.py` whenever the products change, never re-recorded.

| File | What it is |
| --- | --- |
| `slides.py` | The fifteen slides with their narration (the authoritative script) |
| `capture_shots.cjs` | Drives the hub (`pnpm preview`) and the knowledge-base console (`deploy/serve.py`) with Playwright and screenshots each step; renders the terminal outputs |
| `build.sh` | The whole pipeline: terminal outputs, shots, deck, frames, narration, video |
| `out/collection-walkthrough.mp4` | The result (not committed): about five minutes, captions burned in, plus `.en.vtt` and a no-captions copy |

## Rebuild

```
cd hub && pnpm install && pnpm build && pnpm preview &                       # :4173
cd knowledgebase && poetry install && (cd web && npm ci && npm run build) && \
  KB_API_KEY=<any-placeholder-key> KB_ROOT=$PWD poetry run python deploy/serve.py &   # :8765
python3 -m pip install --user imageio-ffmpeg                                   # an ffmpeg if none is installed
cd demo && CHROMIUM_PATH=/path/to/chromium NODE_PATH=../hub/node_modules ./build.sh
```

`NARRATION=elevenlabs ./build.sh` with `ELEVENLABS_API_KEY` set produces the voiced version; the default is silent
with captions timed at 2.6 words per second. Pass slide numbers to `build_narration.py` to regenerate only the
slides you changed.

## The steps the video walks through

1. The shape: three parts, one repository, one catalog tool.
2. The hub: Discover's Tools tab, a listing page built from a README, search, Learn.
3. The knowledge base: the components section, a practice page, the skills catalog.
4. The components: a component running in a terminal, the tests, the catalog tool.
5. The programme: the champions page, the initiative brief, the first hour.
