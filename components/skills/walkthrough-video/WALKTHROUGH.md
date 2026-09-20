# Walkthrough: walkthrough-video

## 1. Run the live example

```
cd components/skills/walkthrough-video && python3 deck.py example_slides.py
```

A five-slide deck HTML, one narration file per slide, and `slides.json`, from one plan file.

## 2. Capture real screenshots

Write a capture script for your product (Playwright against a fake or sandbox instance; `demo/capture_shots.cjs` in the repository is one) that screenshots each step into `shots/`.

## 3. Write the plan

Copy `example_slides.py`; one tuple per slide: id, kicker, title, bullets, shot file, narration. The narration is the script; captions derive from it. Fifteen slides is about five minutes.

## 4. Build the four stages

```
python3 deck.py plan.py
node build_frames.cjs                       # needs playwright-core and a Chromium (CHROMIUM_PATH)
python3 build_narration.py --provider captions   # or elevenlabs / edge with a key
python3 build_video.py                       # out/walkthrough.mp4, .en.vtt, .nocaptions.mp4
```

## 5. Watch it once, end to end

Every shot must be the current build's; names in shots and narration are the fake directory's. Regenerate only changed slides' audio by passing their numbers.

## 6. Rebuild, never re-record

When the product changes, re-capture, rebuild. The plan file is the only thing you edit by hand.
