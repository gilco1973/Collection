# walkthrough-video

A narrated, captioned walkthrough video built from the product's own screenshots, a slide plan, text-to-speech and ffmpeg. Rebuilt from one file when the product changes, never re-recorded.

## Five-minute start

```
cd components/skills/walkthrough-video
python3 deck.py example_slides.py            # deck.html, narration/*.txt, slides.json
node build_frames.cjs                        # frames/slide-NN.png (needs playwright-core and a Chromium)
python3 build_narration.py --provider captions
python3 build_video.py                        # out/walkthrough.mp4 + .en.vtt
```

Read `SKILL.md` for the procedure; it is the same page the knowledge base publishes in its skills catalog.

## What is inside

| File | What it is |
| --- | --- |
| `SKILL.md` | The procedure |
| `deck.py` | Plan to deck HTML, narration files and slides.json |
| `build_frames.cjs` | Deck to PNG frames with Playwright |
| `build_narration.py` | ElevenLabs, Edge speech or silent captions; selective regeneration |
| `build_video.py` | Frames and narration to MP4 with burned captions and a WebVTT track |
| `example_slides.py` | A five-slide plan |

## How to reuse it

Copy the directory, or just `SKILL.md` and the template, into your project. Nothing here depends on the rest of the
collection.

## Where it came from

The first responder's walkthrough pipeline (15 slides, five minutes), with the slide plan moved to a file.
