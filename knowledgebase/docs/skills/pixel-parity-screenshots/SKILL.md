---
name: pixel-parity-screenshots
description: Prove a front end matches its design artboards pixel for pixel by rendering both under identical conditions and diffing them, with documented exceptions, as a CI gate.
title: Pixel parity skill
owner: ai-platform-engineering
status: active
reviewed: '2026-09-20'
tags: [skill, evaluation]
audience: [engineer]
---
# Pixel parity skill

## When to use
A front end is built from published design artboards and the team promised it is identical at its default state.
Run it on every change to the styles or the screens; the number of differing pixels is the acceptance criterion.
Not for pages that have no artboard (test those by behaviour instead).

## Inputs
- The artboards as self-contained HTML files, one per screen.
- The app running locally in mock mode (a static preview server is enough).
- `screens.json`: name, route, artboard file, viewport height, an optional selector that marks the page as loaded.
- The scripts in `components/skills/pixel-parity-screenshots/`: `shoot.cjs` (Node, `playwright-core`, a Chromium)
  and `diff.py` (Python, Pillow). Optional: a local font cache so both renders load the same fonts offline, and an
  init script that seeds a mock sign-in before the app boots.

## Steps
1. Build and serve the app (`vite preview` or equivalent); note the base URL.
2. Write `screens.json` from `screens.example.json`; the height is the artboard's.
3. `APP_BASE=http://localhost:4173 ARTBOARDS=./artboards FONTS=./fonts node shoot.cjs` renders each pair to
   `compare/<name>.ref.png` and `compare/<name>.app.png` in one browser session; page errors fail the run.
4. `python3 diff.py` prints differing pixels per screen, writes `compare/<name>.diff.png` (differences in red over a
   faded reference) and `compare/results.json`, and exits 2 on any difference.
5. For a difference that is intentional (state the artboards disagree on among themselves), add a box to
   `compare/expected.json` under the screen's name with a reason; pixels inside it are reported but not counted.
6. Wire steps 3 and 4 into CI after the build.

## Tools
| Tool | Mutating | Notes |
| --- | --- | --- |
| `shoot.cjs` | Writes PNGs under `compare/` | Ignored by git |
| `diff.py` | Writes diff PNGs and `results.json` | Exit 2 is the gate |

## Checks before finishing
- [ ] Every screen in `screens.json` has an artboard file that renders without page errors.
- [ ] Fonts load identically for reference and candidate (no network dependency).
- [ ] Every `expected.json` box has a reason a reviewer accepts.
- [ ] The worst screen reports 0.000% outside documented boxes.

## Output format
`compare/*.ref.png`, `*.app.png`, `*.diff.png`, `results.json`; the console summary with the worst screen.

## Evaluation
The gate itself: zero differing pixels outside documented regions on every screen.
