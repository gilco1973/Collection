# pixel-parity-screenshots

Prove a front end matches its design artboards: render the artboard and the app route under identical conditions in one browser session, diff the pixels, document intentional exceptions, gate CI on zero.

## Five-minute start

```
cd components/skills/pixel-parity-screenshots
APP_BASE=http://localhost:4173 ARTBOARDS=./artboards node shoot.cjs && python3 diff.py
```

Read `SKILL.md` for the procedure; it is the same page the knowledge base publishes in its skills catalog.

## What is inside

| File | What it is |
| --- | --- |
| `SKILL.md` | The procedure |
| `shoot.cjs` | Reference and candidate screenshots from screens.json |
| `diff.py` | Differing pixels per screen, red-over-faded diff images, results.json, exit 2 on any difference |
| `screens.example.json` | The screens file shape |

## How to reuse it

Copy the directory, or just `SKILL.md` and the template, into your project. Nothing here depends on the rest of the
collection.

## Where it came from

The AI Hub's verify:shoot and verify:diff tooling, with the screen list moved to a file.

## Known limits

**Replacement test** (the platform specification's §14.3 rule for an interim): The UI modules' toolchain gate; a module reaches GA only after the usability pass, with this diff as the pixel evidence.
