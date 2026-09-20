# Walkthrough: pixel-parity-screenshots

## 1. Run the live example

```
cd components/skills/pixel-parity-screenshots && python3 example.py
```

Two renders that differ in one 20 by 10 region, diffed by `diff.py`: 200 pixels, the bounding box, exit code 2, the way the gate fails. Needs Pillow (`python3 -m pip install pillow`).

## 2. Copy the two scripts and the screens file

```
cp shoot.cjs diff.py screens.example.json /path/to/your-app/tools/
mv /path/to/your-app/tools/screens.example.json /path/to/your-app/tools/screens.json
```

## 3. Describe your screens

One entry per artboard: name, route, artboard file, viewport height, and the selector that marks the page as loaded.

## 4. Render both sides in one browser

```
APP_BASE=http://localhost:4173 ARTBOARDS=./artboards FONTS=./fonts node shoot.cjs
```

Serve the built app first. A local font cache keeps both renders identical without the network; an init script can seed a mock sign-in.

## 5. Diff and document exceptions

```
python3 diff.py
```

Zero differing pixels is the gate. A difference the artboards themselves disagree on goes into `compare/expected.json` as a box with a reason; it is reported but not counted.

## 6. Put it in CI after the build

Steps 4 and 5 as one job; the diff images are the evidence when it fails.
