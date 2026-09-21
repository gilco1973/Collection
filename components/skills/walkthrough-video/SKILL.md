---
name: walkthrough-video
description: Produce a narrated, captioned walkthrough video of a product from real screenshots, a slide plan, text-to-speech and ffmpeg, rebuildable from one file whenever the product changes.
title: Walkthrough video skill
owner: ai-platform-enablement
status: active
reviewed: '2026-09-20'
tags: [skill, video, onboarding]
audience: [engineer, product]
---
# Walkthrough video skill

## When to use
A product needs a four-to-six-minute guided tour for people who will never read the manual: an on-call team, a
leadership review, an onboarding page. The screenshots must be the product's own output, so the video is rebuilt
rather than re-recorded when the product changes.

## Inputs
- A running instance of the product in a fake or sandbox mode, and a script that drives it through one scenario and
  screenshots each step (`capture_shots.cjs` in the origin; write yours per product).
- A slide plan in the shape of `example_slides.py`: id, kicker, title, bullets, shot file, narration.
- The scripts in `components/skills/walkthrough-video/`: `deck.py`, `build_frames.cjs`, `build_narration.py`,
  `build_video.py`. Node with `playwright-core` and a Chromium; Python 3.11; ffmpeg (or `imageio-ffmpeg`).
- Optional: an ElevenLabs key or Edge speech for a voice. Without either, `--provider captions` makes a silent,
  captioned video timed at 2.6 words per second.

## Steps
1. Capture the shots from the real product into `shots/` (one PNG per step; names referenced by the plan).
2. Write the plan: one tuple per slide; the narration is the authoritative text, captions derive from it. Fifteen
   slides is about five minutes.
3. `python3 deck.py plan.py` writes `deck.html`, `narration/slideNN.txt` and `slides.json`.
4. `node build_frames.cjs` renders each slide to `frames/slide-NN.png` at 2560×1440.
5. `python3 build_narration.py [--provider elevenlabs|edge|captions] [slide numbers]` writes one audio file per slide
   and `narration/durations.json`; pass slide numbers to regenerate only the changed ones.
6. `python3 build_video.py` holds each frame for its narration, burns the captions, writes the MP4, a `.en.vtt` and
   a no-captions copy under `out/`.
7. Watch it once end to end before sharing; check every shot is the current build's.

## Tools
| Tool | Mutating | Notes |
| --- | --- | --- |
| The capture script | Runs the product in fake mode | Never against production |
| Text-to-speech | Sends narration text to a provider | Narration is authored text, never product data |
| ffmpeg | Writes under `out/` and `build/` | Both are ignored by git |

## Checks before finishing
- [ ] Every shot in the plan exists and comes from the current build.
- [ ] Names in shots and narration are the fake directory's, not real people.
- [ ] The narration file count equals the slide count; `durations.json` covers every slide.
- [ ] The `.vtt` cues match the narration sentences.

## Output format
`out/<name>.mp4`, `out/<name>.en.vtt`, `out/<name>.nocaptions.mp4`; `slides.json` for anything that wants the script.

## Evaluation
A reviewer who has not used the product can name the five steps after watching once.
